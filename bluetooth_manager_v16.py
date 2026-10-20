#!/usr/bin/env python3
"""MiSTer Bluetooth Manager v16. Uses MiSTer's btctl for pairing."""
import os
import pty
import select
import signal
import time
import tty
import re
import shutil
import subprocess
import sys

MAC_RE = re.compile(r"\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b")


def run(args, timeout=12):
    try:
        return subprocess.run(args, text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None


def command(name, fallback=None):
    return shutil.which(name) or (fallback if fallback and os.path.isfile(fallback) else None)


def adapter():
    hci = command('hcitool')
    if hci:
        out = run([hci, 'dev'])
        if out and out.returncode == 0:
            found = re.findall(r'^\s*(hci\d+)\s+('+MAC_RE.pattern+r')', out.stdout, re.M)
            if found:
                return ', '.join('{} ({})'.format(n, m.upper()) for n, m in found)
            return 'NOT DETECTED'
    hciconfig = command('hciconfig')
    if hciconfig:
        out = run([hciconfig])
        if out and out.stdout.strip():
            matches = re.findall(r'^(hci\d+):', out.stdout, re.M)
            if matches:
                return ', '.join(matches) + ' (hcitool unavailable)'
    return 'UNKNOWN (hcitool unavailable or failed)'


def bluetoothctl():
    return command('bluetoothctl')


def paired_devices():
    ctl = bluetoothctl()
    if not ctl:
        return None, 'bluetoothctl is not installed; device management unavailable.'
    for cmd in ('paired-devices', 'devices Paired'):
        out = run([ctl] + cmd.split())
        if not out or out.returncode != 0:
            continue
        devices = []
        for line in out.stdout.splitlines():
            m = re.match(r'^Device\s+('+MAC_RE.pattern+r')(?:\s+(.*))?$', line.strip())
            if m:
                devices.append({'mac': m.group(1).upper(), 'name': (m.group(2) or 'Unknown device').strip()})
        # The older 'paired-devices' query is the safest fallback when the new
        # filter syntax isn't supported by the installed bluetoothctl.
        if 'Invalid' in out.stdout or 'Unknown command' in out.stdout:
            continue
        return devices, None
    return None, 'Unable to list paired devices using bluetoothctl.'


def device_info(mac):
    out = run([bluetoothctl(), 'info', mac]) if bluetoothctl() else None
    if not out or out.returncode != 0 or not out.stdout.strip():
        return {'connected': 'UNKNOWN', 'trusted': 'UNKNOWN', 'name': None, 'paired': None}
    info = out.stdout
    def val(key):
        m = re.search(r'^\s*'+key+r':\s*(.+)$', info, re.M | re.I)
        return m.group(1).strip() if m else None
    state = val('Connected')
    return {'connected': ('YES' if state.lower() == 'yes' else 'NO') if state else 'UNKNOWN',
            'trusted': val('Trusted') or 'UNKNOWN',
            'name': val('Name') or val('Alias'),
            'paired': val('Paired')}



def dongle_diagnostics():
    """Show a compact adapter health summary; no radio-noise claims."""
    print(' Dongle')
    print('-' * 65)
    exe = command('hciconfig')
    if not exe:
        print(' Status: UNKNOWN (hciconfig unavailable)')
        return
    result = run([exe, '-a'])
    if result is None or result.returncode != 0:
        print(' Status: UNKNOWN (unable to read adapter)')
        return
    sections = re.split(r'(?=^hci\d+:)', result.stdout, flags=re.M)
    sections = [x for x in sections if re.match(r'^hci\d+:', x)]
    if not sections:
        print(' Status: NOT DETECTED')
        return
    for section in sections:
        hci = re.search(r'^(hci\d+):', section).group(1)
        manufacturer = re.search(r'^\s*Manufacturer:\s*(.+)', section, re.M)
        version = re.search(r'^\s*HCI Version:\s*(\S+)', section, re.M)
        state = re.search(r'^\s*(UP|DOWN)(?:\s+RUNNING)?[^\n]*', section, re.M)
        error_counts = re.findall(r'^\s*(RX|TX) bytes:[^\n]*?errors:(\d+)', section, re.M)
        counts = {kind: int(count) for kind, count in error_counts}
        ready = bool(state and re.search(r'\bUP\b', state.group(0)) and
                     re.search(r'\bRUNNING\b', state.group(0)))
        if not ready:
            status = 'NOT READY' if state else 'UNKNOWN'
        elif 'RX' not in counts or 'TX' not in counts:
            status = 'RUNNING (errors unavailable)'
        elif counts['RX'] or counts['TX']:
            status = 'RUNNING (reported errors)'
        else:
            status = 'GOOD'
        vendor = manufacturer.group(1).split(' Semiconductor')[0] if manufacturer else 'Unknown'
        print(' {}: {} | Bluetooth {} | {}'.format(hci, vendor,
              version.group(1) if version else 'Unknown', status))
        if 'RX' in counts and 'TX' in counts:
            print(' Adapter errors: RX {} / TX {}'.format(counts['RX'], counts['TX']))


def connected_color(status):
    if not sys.stdout.isatty():
        return status
    if status == 'YES':
        return '\033[32mYES\033[0m'
    if status == 'NO':
        return '\033[31mNO\033[0m'
    return status


def inventory():
    print('\n' + '=' * 65)
    print(' MiSTer Bluetooth Manager v16')
    print('=' * 65)
    print(' Adapter: {}'.format(adapter()))
    links = connected_macs()
    devices, error = paired_devices()
    if error:
        print(' Paired:  UNKNOWN ({})'.format(error))
    elif not devices:
        print(' Paired:  0 devices')
    else:
        count = 0
        rows = []
        for d in devices:
            details = device_info(d['mac'])
            # BlueZ can temporarily leave an unpaired device in paired-devices.
            # Never show that stale entry as a paired UNKNOWN device.
            if (details['paired'] or '').lower() == 'no':
                continue
            status = ('YES' if d['mac'].upper() in links else 'NO') if links is not None else details['connected']
            details['connected'] = status
            if status == 'YES':
                count += 1
            if details['name']:
                d['name'] = details['name']
            d.update({key: val for key, val in details.items() if key != 'name'})
            rows.append(d)
        print(' Paired:  {}    Connected: {}'.format(len(rows), count))
        print('-' * 65)
        for idx, d in enumerate(rows, 1):
            print(' {:>2}. {} | {}'.format(idx, d['name'], d['mac']))
            print('     Connected: {}   Trusted: {}'.format(connected_color(d['connected']), d['trusted']))
        devices = rows
    print('=' * 65)
    return devices


def stop_pair_process(proc):
    """Stop only our pairing subprocess, never unrelated Bluetooth services."""
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()


def pair():
    btctl = command('btctl', '/usr/sbin/btctl')
    if not btctl:
        print('\nMiSTer pairing utility is unavailable.')
        return
    current_adapter = adapter()
    if not re.match(r'^hci\d+\b', current_adapter):
        print('\nBluetooth adapter unavailable ({}).'.format(current_adapter))
        print('Plug in your dongle and try again. Pairing was not started.')
        return
    print('\nPut your controller into pairing mode.')
    print('Searching for up to 60 seconds. Ctrl+C to cancel.\n')

    # MiSTer's btctl pair chooses compatible input devices automatically.
    # A pseudo-terminal lets us see progress as it happens, instead of waiting
    # for btctl to exit after its full scan timeout.
    master = slave = None
    proc = None
    success = False
    found_name = None
    found_mac = None
    pending = b''

    def handle_line(raw):
        nonlocal success, found_name, found_mac
        line = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', raw).strip()
        if not line or 'AdvertisementMonitor path registered' in line:
            return
        if line.startswith('NAME:'):
            found_name = line.partition(':')[2].strip()
            print('Found: {}'.format(found_name))
        elif line.startswith('MAC:'):
            found_mac = line.partition(':')[2].strip()
            print('Address: {}'.format(found_mac))
        elif line.startswith('Skipping:'):
            print('Not a controller; continuing search.\n')
            found_name = found_mac = None
        elif line == 'Done.':
            success = True
            print('\nPaired successfully{}.'.format(' with ' + found_name if found_name else ''))
        elif line in ('Pairing...', 'Trusting...', 'Connecting...'):
            print(line)
        elif 'Traceback' in line or 'Bluetooth adapter not found' in line:
            print('Bluetooth pairing failed. Check that the dongle is connected.')
        elif line.startswith('Exception:'):
            print('Pairing error: {}'.format(line.partition(':')[2].strip()))
        elif line.startswith('Failed') or line.startswith('Error'):
            print(line)

    try:
        master, slave = pty.openpty()
        tty.setraw(slave)
        proc = subprocess.Popen([btctl, 'pair'], stdin=subprocess.DEVNULL,
                                stdout=slave, stderr=slave, start_new_session=True,
                                close_fds=True)
        os.close(slave)
        slave = None
        deadline = time.monotonic() + 65
        while time.monotonic() < deadline and not success:
            readable, _, _ = select.select([master], [], [], 0.25)
            if readable:
                try:
                    data = os.read(master, 4096)
                except OSError:
                    data = b''
                if not data:
                    break
                pending += data.replace(b'\r', b'\n')
                while b'\n' in pending:
                    part, pending = pending.split(b'\n', 1)
                    handle_line(part.decode('utf-8', 'replace'))
                    if success:
                        break
            if proc.poll() is not None and not readable:
                break
        if not success and pending.strip():
            handle_line(pending.decode('utf-8', 'replace'))
        if not success:
            print('\nNo successful pairing detected. Try again if needed.')
    except KeyboardInterrupt:
        print('\nPairing cancelled.')
    except OSError as exc:
        print('Unable to start pairing: {}'.format(exc))
    finally:
        if proc is not None:
            stop_pair_process(proc)
        if slave is not None:
            os.close(slave)
        if master is not None:
            os.close(master)


def choose(devices):
    if devices is None:
        print('\nCannot manage devices because the paired list is unavailable.')
        return None
    if not devices:
        print('\nNo paired devices.')
        return None
    print('\nPaired Bluetooth Devices')
    print('-' * 65)
    for idx, d in enumerate(devices, 1):
        print(' {:>2}. {} | {}'.format(idx, d['name'], d['mac']))
        print('     Connected: {}   Trusted: {}'.format(
            connected_color(d['connected']), d['trusted']))
    raw = input('\nEnter device number to remove (Enter to cancel): ').strip()
    if not raw:
        return None
    if not raw.isdigit() or not 1 <= int(raw) <= len(devices):
        print('Invalid device number.')
        return None
    return devices[int(raw)-1]


def action(devices, kind):
    d = choose(devices)
    if not d:
        return
    if kind == 'remove':
        print('\nRemove pairing for {} ({})?'.format(d['name'], d['mac']))
        answer = input('Type REMOVE to confirm: ').strip()
        if answer != 'REMOVE':
            print('Cancelled.')
            return
        verb = 'remove'
    else:
        verb = kind
    current_adapter = adapter()
    if not re.match(r'^hci\d+\b', current_adapter):
        print('\nBluetooth adapter unavailable ({}).'.format(current_adapter))
        print('Device was not removed. Plug in your dongle and try again.')
        return
    ctl = bluetoothctl()
    if not ctl:
        print('Bluetooth control utility unavailable; no changes made.')
        return
    result = run([ctl, verb, d['mac']], timeout=25)
    if result is None:
        print('Unable to remove pairing (command failed or timed out).')
        return
    # bluetoothctl may include unrelated BlueZ chatter in its output; verify
    # the removal by checking the saved pairing list instead of echoing it.
    # The bluetoothctl cache may lag after a successful remove. Wait briefly
    # for the saved list to settle instead of showing a phantom UNKNOWN entry.
    for attempt in range(8):
        updated, error = paired_devices()
        if error:
            print('Removal requested, but unable to verify it: {}.'.format(error))
            return
        still_listed = any(item['mac'] == d['mac'] for item in updated)
        info = device_info(d['mac']) if still_listed else None
        if not still_listed or (info['paired'] or '').lower() == 'no':
            print('Pairing removed: {} ({})'.format(d['name'], d['mac']))
            return
        if attempt < 7:
            time.sleep(0.3)
    print('Removal has not yet been confirmed for {}. Try Refresh status.'.format(d['name']))



def connected_macs():
    """Read actual controller links, independently from the paired-device list."""
    hci = command('hcitool')
    if not hci:
        return None
    result = run([hci, 'con'])
    if not result or result.returncode != 0:
        return None
    return {m.upper() for m in MAC_RE.findall(result.stdout)}


def signal_reading(subcommand, mac):
    """Return integer HCI reading, or None when unavailable."""
    hci = command('hcitool')
    if not hci:
        return None
    result = run([hci, subcommand, mac], timeout=8)
    if result is None or result.returncode != 0:
        return None
    output = (result.stdout + ' ' + result.stderr).strip()
    pattern = r'RSSI return value:\s*(-?\d+)' if subcommand == 'rssi' else r'Link quality:\s*(\d+)'
    match = re.search(pattern, output, re.I)
    return int(match.group(1)) if match else None


def signal_status(rssi):
    """Rough convenience bands, not calibrated dBm measurements."""
    if rssi is None:
        return 'UNKNOWN', ''
    if rssi >= -40:
        return 'GOOD', '\033[32m'
    if rssi >= -70:
        return 'FAIR', '\033[33m'
    return 'WEAK', '\033[31m'


def bluetooth_ping(mac, count=3):
    """Measure L2CAP echo round-trip times (not controller input latency)."""
    exe = command('l2ping')
    if not exe:
        return None, 'l2ping unavailable'
    result = run([exe, '-c', str(count), mac], timeout=max(12, count * 4))
    if result is None:
        return None, 'test timed out or could not start'
    output = (result.stdout or '') + '\n' + (result.stderr or '')
    values = [float(v) for v in re.findall(r'\btime\s+([0-9]+(?:\.[0-9]+)?)\s*ms\b', output, re.I)]
    if not values:
        return None, 'no response (echo may be unsupported)'
    # Use observed replies, rather than assuming that a nonzero process exit
    # status means the successfully received replies should be discarded.
    return {'sent': count, 'received': len(values),
            'minimum': min(values), 'average': sum(values) / len(values),
            'maximum': max(values)}, None


def diagnostics(devices):
    print('\nBluetooth Diagnostics')
    print('=' * 65)
    dongle_diagnostics()
    print('\n Controller Signals')
    print('-' * 65)
    links = connected_macs()
    if links is None:
        print(' Unable to check active connections (hcitool unavailable or failed).')
        return
    if not links:
        print(' No connected controllers.')
        return
    by_mac = {d['mac'].upper(): d for d in (devices or [])}
    for mac in sorted(links):
        d = by_mac.get(mac, {})
        rssi = signal_reading('rssi', mac)
        rating, color = signal_status(rssi)
        if not sys.stdout.isatty():
            color = ''
        reset = '\033[0m' if color else ''
        print(' {} ({})'.format(d['name'] if d else 'Unknown device', mac))
        print('   Signal Strength: {}{}{}  |  Raw Signal (RSSI): {}'.format(
            color, rating, reset, rssi if rssi is not None else 'Unavailable'))
        result, error = bluetooth_ping(mac, 3)
        if result:
            missed = max(0, result['sent'] - result['received'])
            print('   Bluetooth ping: min {:.2f} / avg {:.2f} / max {:.2f} ms'.format(
                result['minimum'], result['average'], result['maximum']))
            print('   Replies: {}/{}   Lost: {}'.format(
                result['received'], result['sent'], missed))
        else:
            print('   Bluetooth ping: {}'.format(error))
            print('   Connection: UNRESPONSIVE (no ping replies; may be unsupported)')
    # Check the adapter again after diagnostics. A powered-off controller
    # can remain in the HCI connection list until Bluetooth times out.
    refreshed = connected_macs()
    if refreshed is not None and refreshed != links:
        print('\n Connection status updated; main menu will show the latest state.')


def clear_screen():
    """Clear interactive terminals without invoking external shell commands."""
    if sys.stdout.isatty():
        sys.stdout.write('\033[2J\033[H')
        sys.stdout.flush()


def return_to_menu():
    """Keep results visible until the user is finished reading them."""
    if sys.stdin.isatty():
        input('\nPress Enter to return to menu...')


def main():
    if not os.path.isfile('/media/fat/MiSTer'):
        print('This utility must be run on a MiSTer system.')
        return 1
    while True:
        clear_screen()
        devices = inventory()
        print(' [1] Pair new Bluetooth device')
        print(' [2] Remove paired device')
        print(' [3] Bluetooth diagnostics')
        print(' [4] Refresh status')
        print(' [5] Exit')
        choice = input('\n Choose [1-5]: ').strip()
        if choice == '1':
            clear_screen()
            pair()
            return_to_menu()
        elif choice == '2':
            clear_screen()
            action(devices, 'remove')
            return_to_menu()
        elif choice == '3':
            clear_screen()
            diagnostics(devices)
            return_to_menu()
        elif choice == '4':
            continue
        elif choice == '5':
            return 0
        else:
            print('Invalid selection.')
            return_to_menu()


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (EOFError, KeyboardInterrupt):
        print('\nExited.')
        sys.exit(0)
