#!/usr/bin/env python3
"""MiSTer Wi-Fi Setup & Diagnostics v26. Single-file Python Wi-Fi manager.

Connection changes are saved safely to wpa_supplicant.conf and take effect
when MiSTer is restarted. No wifi.sh dependency. Password entry is visible by user request.
"""
import os
import re
import sys
import time
import shutil
import socket
import tempfile
import stat
import subprocess
import threading
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
LOG_DIR = Path(os.environ.get('LOG_DIR', '/media/fat/Scripts/logs'))
REPORT_PATH = LOG_DIR / 'wifi_diagnostics.log'
WPA_CONF = Path(os.environ.get('WPA_CONF', '/media/fat/linux/wpa_supplicant.conf'))


def command(args, timeout=12):
    try:
        p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True, errors='replace', timeout=timeout, check=False)
        return p.stdout.strip(), p.stderr.strip(), p.returncode
    except (OSError, subprocess.TimeoutExpired) as exc:
        return '', str(exc), 1


def wireless_interface():
    out, _, _ = command(['iw', 'dev'])
    m = re.search(r'^\s*Interface\s+(\S+)', out, re.M)
    if m:
        return m.group(1)
    if Path('/sys/class/net/wlan0').exists():
        return 'wlan0'
    return None


def wifi_link(iface):
    out, err, _ = command(['iw', 'dev', iface, 'link'])
    return out or '(unavailable: {})'.format(err)


def extract(pattern, text, default='unknown', flags=0):
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else default


def gateway(iface):
    out, _, _ = command(['ip', '-4', 'route', 'show', 'default'])
    for line in out.splitlines():
        parts = line.split()
        if 'via' in parts and 'dev' in parts and parts[parts.index('dev')+1] == iface:
            return parts[parts.index('via')+1]
    return None


def ip_address(iface):
    out, _, _ = command(['ip', '-4', '-o', 'addr', 'show', 'dev', iface])
    return extract(r'\binet\s+([0-9]+(?:\.[0-9]+){3})(?:/\d+)?', out)


def signal_quality(dbm):
    if dbm >= -55:
        return 'excellent'
    if dbm >= -65:
        return 'good'
    if dbm >= -70:
        return 'fair'
    return 'weak'


def saved_priorities():
    """Show human-readable SSIDs even when stored in hexadecimal."""
    try:
        return [(ssid, network_priority(data))
                for _, _, data, ssid in parse_config_networks(read_wifi_config())]
    except (OSError, ValueError):
        return []


def ping_gateway(address, count=20):
    if not address:
        return ['No Wi-Fi default gateway found; ping test skipped.'], None
    if not re.fullmatch(r'[0-9.]+', address):
        return ['Gateway value unexpectedly formatted; ping skipped.'], None
    # BusyBox ping on MiSTer supports -c; cap run time using subprocess timeout.
    out, err, rc = command(['ping', '-c', str(count), address], timeout=(32 if count == 20 else 10))
    lines = ['Gateway: {}'.format(address)]
    summary = re.search(r'(\d+)\s+packets transmitted,\s*(\d+)\s+(?:packets )?received[^\n]*', out)
    if summary:
        sent, received = map(int, summary.groups())
        lines.append('Packets: {} sent, {} received ({}% lost)'.format(
            sent, received, round(100 * (sent - received) / sent) if sent else '?'))
    rtt = re.search(r'(?:rtt|round-trip)\s+min/avg/max(?:/mdev|/stddev)?\s*=\s*([\d.]+)/([\d.]+)/([\d.]+)', out)
    metrics = None
    if rtt:
        minimum, average, maximum = map(float, rtt.groups())
        metrics = dict(minimum=minimum, average=average, maximum=maximum)
        lines.append('Ping min/avg/max: {:.1f} / {:.1f} / {:.1f} ms'.format(minimum, average, maximum))
    if not summary and not rtt:
        lines.append('Ping results unavailable: {}'.format((err or out or 'unknown error')[-300:]))
    return lines, metrics


def quality_label(value, thresholds, higher_is_better=True):
    """Return a four-tier rating for a numeric Wi-Fi measurement."""
    if value is None:
        return 'UNKNOWN'
    if higher_is_better:
        return ('EXCELLENT' if value >= thresholds[0] else
                'GOOD' if value >= thresholds[1] else
                'OK' if value >= thresholds[2] else 'POOR')
    return ('EXCELLENT' if value <= thresholds[0] else
            'GOOD' if value <= thresholds[1] else
            'OK' if value <= thresholds[2] else 'POOR')


def rated(label, rating):
    """Colorize a rating for interactive terminals, leaving logs plain text."""
    codes = {'EXCELLENT': '1;32', 'GOOD': '32', 'OK': '1;33',
             'POOR': '1;31', 'UNKNOWN': '37'}
    return '{} [{}]'.format(label, rating)


def colorize_diagnostic_report(report):
    """Apply terminal colors only when displaying diagnostics, not saving logs."""
    codes = {'EXCELLENT': '1;32', 'GOOD': '32', 'OK': '1;33',
             'POOR': '1;31', 'UNKNOWN': '37'}
    return re.sub(r'\[(EXCELLENT|GOOD|OK|POOR|UNKNOWN)\]',
                  lambda m: '[' + tint(m.group(1), codes[m.group(1)]) + ']',
                  report)


def link_rate_number(rate):
    match = re.search(r'([\d.]+)\s*MBit/s', rate)
    return float(match.group(1)) if match else None


def diagnostics(ping=True, ping_count=20):
    lines = ['MISTER WI-FI DIAGNOSTICS', '=' * 55,
             'Generated: {}'.format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')), '']
    iface = wireless_interface()
    if not iface:
        return '\n'.join(lines + ['No Wi-Fi interface detected.',
                                 'Check USB Wi-Fi dongle, driver, and firmware.']) + '\n'
    link = wifi_link(iface)
    ssid = extract(r'^\s*SSID:\s*(.*)$', link, '(not connected)', re.M)
    freq = extract(r'^\s*freq:\s*(\d+)', link, '', re.M)
    signal = extract(r'^\s*signal:\s*(-?\d+)\s*dBm', link, '', re.M)
    rx = extract(r'^\s*rx bitrate:\s*([^\n]+)', link, '', re.M)
    tx = extract(r'^\s*tx bitrate:\s*([^\n]+)', link, '', re.M)
    bssid = extract(r'^Connected to\s+(\S+)', link, '', re.M)
    band = ('5 GHz' if freq and 4900 <= int(freq) <= 5900 else
            '2.4 GHz' if freq and 2400 <= int(freq) <= 2500 else
            '6 GHz' if freq and 5925 <= int(freq) <= 7125 else 'unknown')
    gw = gateway(iface)
    signal_rating = quality_label(int(signal) if signal else None, (-55, -65, -75))
    rx_rating = quality_label(link_rate_number(rx), (150, 72, 30))
    tx_rating = quality_label(link_rate_number(tx), (150, 72, 30))
    lines.extend(['Interface: {}'.format(iface), 'SSID: {}'.format(ssid),
                  'BSSID (access point): {}'.format(bssid or 'unknown'),
                  'Frequency: {} MHz ({})'.format(freq or 'unknown', band),
                  'Signal: {}{}'.format(('{} dBm'.format(signal) if signal else 'unknown'),
                          ' ({})'.format(signal_quality(int(signal))) if signal else ''),
                  'Receive link rate: {}'.format(rx or 'unknown'),
                  'Transmit link rate: {}'.format(tx or 'unknown'),
                  'IPv4: {}'.format(ip_address(iface)),
                  'Default gateway: {}'.format(gw or 'none'),
                  ''])
    overall_rating = ('POOR' if ssid == '(not connected)' else
                      min((signal_rating, rx_rating, tx_rating),
                          key=lambda rating: {'POOR': 0, 'UNKNOWN': 1, 'OK': 2,
                                              'GOOD': 3, 'EXCELLENT': 4}[rating]))
    lines.extend(['CONNECTION QUALITY', '-' * 55,
                  rated('Overall Wi-Fi status', overall_rating),
                  rated('Signal strength', signal_rating),
                  rated('Receive link rate', rx_rating),
                  rated('Transmit link rate', tx_rating),
                  'Ratings are approximate; link rates are not throughput.', ''])
    pwr, _, _ = command(['iw', 'dev', iface, 'get', 'power_save'])
    lines.extend(['{}'.format(pwr or 'Power save: unavailable'), ''])
    station, _, _ = command(['iw', 'dev', iface, 'station', 'dump'])
    lines.append('WIRELESS STATISTICS')
    lines.append('-' * 55)
    # Cumulative driver counters; some Wi-Fi drivers omit or misreport them.
    # Show denominators explicitly rather than treating raw totals as rates.
    stat_patterns = [
        ('TX packets', r'^\s*tx packets:\s*(\d+)'),
        ('TX retries', r'^\s*tx retries:\s*(\d+)'),
        ('TX failed', r'^\s*tx failed:\s*(\d+)'),
        ('RX packets', r'^\s*rx packets:\s*(\d+)'),
        ('RX dropped (misc)', r'^\s*rx drop misc:\s*(\d+)'),
        ('Beacon loss', r'^\s*beacon loss:\s*(\d+)'),
    ]
    stats = {}
    for label, pattern in stat_patterns:
        match = re.search(pattern, station, re.M)
        stats[label] = int(match.group(1)) if match else None

    def fmt_count(label):
        count = stats[label]
        return str(count) if count is not None else 'not reported'

    def fmt_ratio(count, total):
        if count is None or total is None or total <= 0:
            return 'N/A'
        return '{:.4f}%'.format(100.0 * count / total)

    tx_total = stats['TX packets']
    rx_total = stats['RX packets']
    rx_drops = stats['RX dropped (misc)']
    rx_denominator = (rx_total + rx_drops) if rx_total is not None and rx_drops is not None else None
    for label in ('TX packets', 'TX retries', 'TX failed', 'RX packets', 'RX dropped (misc)', 'Beacon loss'):
        suffix = ''
        if label in ('TX retries', 'TX failed'):
            suffix = '  ({})'.format(fmt_ratio(stats[label], tx_total))
        elif label == 'RX dropped (misc)':
            suffix = '  ({})'.format(fmt_ratio(stats[label], rx_denominator))
        lines.append('{:<19} {}{}'.format(label + ':', fmt_count(label), suffix))
    lines.append('')
    lines.append('')
    lines.extend(['SAVED NETWORKS (no passwords)', '-' * 55])
    entries = saved_priorities()
    if entries:
        for name, priority in entries:
            lines.append('SSID: {} | priority: {}'.format(name, priority))
        lines.append('Higher priority numbers are preferred by wpa_supplicant.')
    else:
        lines.append('No saved networks found or config unavailable.')
    lines.append('')
    metrics = None
    if ping:
        lines.extend(['GATEWAY PING ({} packets)'.format(ping_count), '-' * 55])
        pinglines, metrics = ping_gateway(gw, count=ping_count)
        lines.extend(pinglines)
        lines.append('')
    lines.extend(['ASSESSMENT', '-' * 55])
    warnings = []
    if ssid == '(not connected)':
        warnings.append('Not associated with a Wi-Fi access point.')
    if signal and int(signal) <= -70:
        warnings.append('Weak Wi-Fi signal; consider improving placement or access point selection.')
    for label, raw in [('receive', rx), ('transmit', tx)]:
        m = re.match(r'([\d.]+)\s*MBit/s', raw)
        if m and float(m.group(1)) < 30:
            warnings.append('Low {} link rate: {}.'.format(label, raw))
    if metrics:
        lines.append(rated('Gateway average latency',
                           quality_label(metrics['average'], (5, 15, 35), False)))
    if metrics and metrics['average'] > 25:
        warnings.append('Elevated average router latency: {:.1f} ms.'.format(metrics['average']))
    if metrics and metrics['maximum'] > 80:
        warnings.append('Router ping spikes up to {:.1f} ms.'.format(metrics['maximum']))
    if entries and ssid not in ('(not connected)', ''):
        priorities = [(n, int(p)) for n, p in entries]
        current = [p for n, p in priorities if n == ssid]
        if current and max(p for _, p in priorities) > max(current):
            warnings.append('Current SSID has lower saved priority than another configured network.')
    if 'on' in pwr.lower():
        warnings.append('Wi-Fi power saving is enabled; it can contribute to latency.')
    if not warnings:
        lines.append('No obvious Wi-Fi issues detected. Link rates are not file-transfer speeds.')
    else:
        for msg in warnings:
            lines.append('! ' + msg)
    lines.append('Note: diagnostics are read-only; ping sends network packets.')
    return '\n'.join(lines) + '\n'


def save_report(report):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(re.sub(r'\x1b\[[0-9;]*m', '', report), encoding='utf-8')
    print('Report saved to: {}'.format(REPORT_PATH))


def parse_config_networks(text):
    """Find top-level network blocks, avoiding braces inside quoted strings.

    Refuse to edit malformed configs rather than risk deleting other settings.
    Returns (start, end, contents, ssid) for each network block.
    """
    blocks = []
    matches = list(re.finditer(r'(?m)^\s*network\s*=\s*\{', text))
    occupied_end = 0
    for m in matches:
        if m.start() < occupied_end:
            raise ValueError('Nested network block; refusing to modify configuration.')
        i = m.end()
        quoted = False
        escaped = False
        while i < len(text):
            ch = text[i]
            if escaped:
                escaped = False
            elif quoted and ch == "\\":
                escaped = True
            elif ch == '"':
                quoted = not quoted
            elif not quoted and ch == '}':
                break
            i += 1
        if i >= len(text):
            raise ValueError('Incomplete network block; refusing to modify configuration.')
        contents = text[m.end():i]
        # Keep the terminating newline, if present.
        finish = i + 1
        if finish < len(text) and text[finish] == '\n':
            finish += 1
        ssid_value = extract(r'(?m)^\s*ssid\s*=\s*(\"(?:[^\"\\]|\\.)*\"|[0-9A-Fa-f]+)', contents, '')
        if not ssid_value:
            raise ValueError('Network block without recognizable SSID; refusing edits.')
        if ssid_value.startswith('"'):
            ssid = ssid_value[1:-1]
        else:
            try:
                ssid = bytes.fromhex(ssid_value).decode('utf-8')
            except (ValueError, UnicodeDecodeError):
                ssid = '<hex SSID {}>'.format(ssid_value[:16])
        blocks.append((m.start(), finish, contents, ssid))
        occupied_end = finish
    return blocks


def read_wifi_config():
    if WPA_CONF.exists():
        return WPA_CONF.read_text(encoding='utf-8', errors='replace')
    return 'ctrl_interface=/run/wpa_supplicant\nupdate_config=1\n\n'


def safe_write_config(new_text):
    """Atomically save settings without leaving backup or temporary files."""
    directory = WPA_CONF.parent
    directory.mkdir(parents=True, exist_ok=True)
    descriptor = None
    tmp_path = None
    try:
        descriptor, tmp_path = tempfile.mkstemp(prefix='.wifi_conf_', dir=str(directory))
        os.fchmod(descriptor, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as out:
            descriptor = None
            out.write(new_text)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp_path, str(WPA_CONF))
        tmp_path = None
        print('Saved Wi-Fi settings.')
        print('Saved. Restart Wi-Fi or reboot to apply network-list changes.')
        return True
    except OSError as exc:
        print('Could not save config: {}'.format(exc))
        return False
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def yes(prompt):
    return input(prompt + ' [y/N]: ').strip().lower() == 'y'


def network_priority(contents):
    return extract(r'(?m)^\s*priority\s*=\s*(-?\d+)', contents, '0')


def available_networks():
    iface = wireless_interface()
    if not iface:
        print('No Wi-Fi interface found.')
        return []
    print('Scanning for networks...')
    connected_ssid = extract(r'^\s*SSID:\s*(.*)$', wifi_link(iface), '', re.M)
    out, err, rc = command(['iw', 'dev', iface, 'scan'], timeout=30)
    if rc:
        print('Scan failed: {}'.format(err or out[-200:]))
        return []
    networks = parse_scan(out)
    seen = set()
    names = []
    for item in networks:
        if item['ssid'] and item['ssid'] not in seen:
            names.append(item['ssid'])
            seen.add(item['ssid'])
    if names:
        for idx, name in enumerate(names, 1):
            active = name == connected_ssid
            line = '  {:>2}. {}{}'.format(idx, name, '  * (connected)' if active else '')
            print(tint(line, '1;32') if active else line)
    else:
        print('No networks found. You can still enter an SSID manually.')
    return names


def choose_ssid(names):
    raw = input('SSID number, or enter exact network name: ').strip()
    if raw.isdigit() and 1 <= int(raw) <= len(names):
        return names[int(raw) - 1]
    return raw


def wpa_quoted(value):
    """Escape characters for a quoted wpa_supplicant string."""
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def readable_ssid(value):
    """Readable ASCII SSIDs; uncommon/binary names retain byte-exact hex."""
    return (wpa_quoted(value) if all(32 <= ord(c) <= 126 for c in value)
            else value.encode('utf-8').hex())


def normalize_saved_ssids():
    """Convert ordinary hex-encoded SSIDs to quoted text; preserve PSKs."""
    try:
        content = read_wifi_config()
        blocks = parse_config_networks(content)
    except (OSError, ValueError) as exc:
        print('Cannot read saved networks: {}'.format(exc))
        return
    replacements = []
    for start, end, data, ssid in blocks:
        if ssid.startswith('<hex SSID ') or not all(32 <= ord(c) <= 126 for c in ssid):
            continue
        match = re.search(r'(?m)^(\s*ssid\s*=\s*)([0-9A-Fa-f]{2,64})([ \t]*(?:#.*)?)$', data)
        if match:
            original = match.group(2)
            try:
                if bytes.fromhex(original).decode('utf-8') != ssid:
                    continue
            except (ValueError, UnicodeDecodeError):
                continue
            replacements.append((start, end, data, match, ssid))
    if not replacements:
        print('Saved network names are already readable (or are not safe to convert).')
        return
    print('\n{} saved network name(s) can be made readable.'.format(len(replacements)))
    if not yes('Convert names to ssid="Name"? (password keys stay unchanged)'):
        return
    for start, end, data, match, ssid in reversed(replacements):
        changed = data[:match.start(2)] + wpa_quoted(ssid) + data[match.end(2):]
        full = content[start:end]
        prefix = full[:full.index('{') + 1]
        suffix = full[len(prefix) + len(data):]
        content = content[:start] + prefix + changed + suffix + content[end:]
    safe_write_config(content)


def add_network():
    names = available_networks()
    ssid = choose_ssid(names)
    if not ssid or len(ssid.encode('utf-8')) > 32:
        print('Invalid SSID (must be 1-32 bytes).')
        return
    try:
        content = read_wifi_config()
        blocks = parse_config_networks(content)
    except (OSError, ValueError) as exc:
        print('Cannot safely edit config: {}'.format(exc))
        return
    if any(block[3] == ssid for block in blocks):
        print('That SSID is already saved. Use priority management or remove it first.')
        return
    print('Password characters will be visible as you type.')
    try:
        password = input('Enter Wi-Fi password: ')
    except (EOFError, KeyboardInterrupt):
        print('\nCancelled.')
        return
    if password and not 8 <= len(password.encode('utf-8')) <= 63:
        print('WPA2 passphrase must be 8-63 bytes.')
        return
    if not password and not yes('Configure this as an OPEN (unencrypted) network?'):
        print('Cancelled.')
        return
    # Quote ordinary SSIDs for human-readable configuration files.
    # Hex is reserved for names that require byte-exact encoding.
    ssid_value = readable_ssid(ssid)
    if blocks:
        # Do not silently displace the existing preferred network.
        prefer = yes('Make this new network the HIGHEST priority?')
    else:
        prefer = True
        print('This will be your first saved network.')
    priority = 3 if prefer else -1
    auth = ('    psk={}\n'.format(wpa_quoted(password))
            if password else '    key_mgmt=NONE\n')
    new_block = '\nnetwork={{\n    ssid={}\n{}    priority={}\n}}\n'.format(ssid_value, auth, priority)
    if prefer and blocks:
        try:
            content = preferred_priority_config(content, blocks, None)
        except ValueError as exc:
            print('Could not safely change priorities: {}'.format(exc))
            return
    print('Add {} with priority {}.'.format(ssid, priority))
    if yes('Confirm save'):
        safe_write_config(content.rstrip() + '\n' + new_block)


def show_saved_networks(blocks):
    if not blocks:
        print('No saved networks.')
    for idx, (_, _, data, name) in enumerate(blocks, 1):
        print('  {:>2}. {:<30} priority {}'.format(idx, name[:30], network_priority(data)))


def manage_networks(action):
    try:
        content = read_wifi_config()
        blocks = parse_config_networks(content)
    except (OSError, ValueError) as exc:
        print('Cannot safely read Wi-Fi config: {}'.format(exc))
        return
    show_saved_networks(blocks)
    if not blocks:
        return
    raw = input('Select saved network number (blank cancels): ').strip()
    if not raw.isdigit() or not 1 <= int(raw) <= len(blocks):
        print('Cancelled.')
        return
    start, end, data, ssid = blocks[int(raw) - 1]
    if action == 'remove':
        if yes('Remove saved network {}?'.format(ssid)):
            safe_write_config(content[:start] + content[end:])
        return


def replace_priority_in_block(original, new_priority):
    """Replace one network priority while preserving all other block settings."""
    open_brace = original.find('{')
    close_brace = original.rfind('}')
    if open_brace < 0 or close_brace < open_brace:
        raise ValueError('Malformed network block')
    inner = original[open_brace + 1:close_brace]
    found = list(re.finditer(r'(?m)^[ \t]*priority[ \t]*=[ \t]*-?\d+[ \t]*(?:\#[^\n]*)?$', inner))
    if len(found) > 1:
        raise ValueError('Duplicate priority lines in a network; refusing to edit.')
    if found:
        match = found[0]
        old_line = match.group(0)
        new_line = re.sub(r'(priority[ \t]*=[ \t]*)-?\d+',
                          lambda m: m.group(1) + str(new_priority), old_line, count=1)
        inner = inner[:match.start()] + new_line + inner[match.end():]
    else:
        inner = inner.rstrip() + '\n    priority={}\n'.format(new_priority)
    return original[:open_brace + 1] + inner + original[close_brace:]


def preferred_priority_config(content, blocks, selected):
    """Keep exactly one preferred network (3); all others have priority -1."""
    updated = content
    # Back-to-front replacements preserve offsets from the original file.
    for index in range(len(blocks) - 1, -1, -1):
        start, end, _, _ = blocks[index]
        priority = 3 if index == selected else -1
        updated = (updated[:start]
                   + replace_priority_in_block(content[start:end], priority)
                   + updated[end:])
    return updated


def set_preferred():
    try:
        content = read_wifi_config()
        blocks = parse_config_networks(content)
    except (OSError, ValueError) as exc:
        print('Cannot safely read Wi-Fi config: {}'.format(exc))
        return
    show_saved_networks(blocks)
    if not blocks:
        return
    if len(blocks) == 1:
        print('Only one saved Wi-Fi network; it is already the only preference.')
        return
    raw = input('Network number to prefer (blank cancels): ').strip()
    if not raw.isdigit() or not 1 <= int(raw) <= len(blocks):
        return
    selected = int(raw) - 1
    try:
        updated = preferred_priority_config(content, blocks, selected)
    except ValueError as exc:
        print('Could not safely change priorities: {}'.format(exc))
        return
    ssid = blocks[selected][3]
    if yes('Set {} to priority 3 and all others to -1?'.format(ssid)):
        if updated == content:
            print('Already set that way.')
        else:
            safe_write_config(updated)


def change_password():
    try:
        content = read_wifi_config()
        blocks = parse_config_networks(content)
    except (OSError, ValueError) as exc:
        print('Cannot safely read Wi-Fi config: {}'.format(exc))
        return
    show_saved_networks(blocks)
    if not blocks:
        return
    raw = input('Network number to update (blank cancels): ').strip()
    if not raw.isdigit() or not 1 <= int(raw) <= len(blocks):
        return
    start, end, data, ssid = blocks[int(raw) - 1]
    try:
        password = input('New WPA2 password (visible, 8-63 bytes): ')
    except (EOFError, KeyboardInterrupt):
        print('\nCancelled.')
        return
    if not 8 <= len(password.encode('utf-8')) <= 63:
        print('Invalid password length.')
        return
    psk = wpa_quoted(password)
    # Change only the authentication fields of the selected saved network.
    data = re.sub(r'(?m)^\s*(?:psk|key_mgmt)\s*=.*(?:\n|$)', '', data)
    changed = data.rstrip() + '\n    psk={}\n'.format(psk)
    original = content[start:end]
    prefix = original[:original.index('{') + 1]
    suffix = original[len(prefix) + len(blocks[int(raw) - 1][2]):]
    if yes('Save new password for {}?'.format(ssid)):
        safe_write_config(content[:start] + prefix + changed + suffix + content[end:])


def change_country():
    try:
        content = read_wifi_config()
        blocks = parse_config_networks(content)
    except (OSError, ValueError) as exc:
        print('Cannot safely read config: {}'.format(exc))
        return
    current = extract(r'(?m)^country\s*=\s*([A-Za-z]{2})', content, 'not set')
    print('Current configured country: {}'.format(current))
    country = input('Enter ISO 2-letter country code (e.g. US; blank cancels): ').strip().upper()
    if not country:
        return
    if not re.fullmatch(r'[A-Z]{2}', country):
        print('Country must be two letters.')
        return
    if yes('Save country={} (takes effect on reboot)?'.format(country)):
        # Only modify a top-level country line, never network block fields.
        country_lines = list(re.finditer(r'(?m)^country\s*=\s*[^\n]*\n?', content))
        if len(country_lines) > 1:
            print('Multiple country headers found; refusing automatic edit.')
            return
        if country_lines and all(not (b[0] <= country_lines[0].start() < b[1]) for b in blocks):
            m = country_lines[0]
            new = content[:m.start()] + 'country={}\n'.format(country) + content[m.end():]
        else:
            new = 'country={}\n'.format(country) + content
        safe_write_config(new)


def switch_saved_network():
    """Select a saved Wi-Fi network without changing saved priorities."""
    iface = wireless_interface()
    if not iface:
        print('No Wi-Fi adapter found.')
        return
    if not shutil.which('wpa_cli'):
        print('Wi-Fi switching is unavailable on this MiSTer.')
        return

    cli_path = None
    for path in ('/run/wpa_supplicant', '/var/run/wpa_supplicant'):
        out, _, rc = command(['wpa_cli', '-p', path, '-i', iface, 'ping'], timeout=5)
        if rc == 0 and out.strip() == 'PONG':
            cli_path = path
            break
    if cli_path is None:
        print('Wi-Fi switching is unavailable: wpa_cli cannot connect.')
        print('Check that Wi-Fi has restarted since ctrl_interface was enabled.')
        return

    out, err, rc = command(['wpa_cli', '-p', cli_path, '-i', iface, 'list_networks'], timeout=6)
    if rc or 'network id' not in out.lower():
        print('Could not list connected Wi-Fi networks: {}'.format((err or out)[:200]))
        return
    entries = []
    for line in out.splitlines()[1:]:
        parts = line.split('\t')
        if len(parts) >= 2 and parts[0].strip().isdigit():
            entries.append((parts[0].strip(), parts[1].strip(), parts[3].strip() if len(parts) > 3 else ''))
    if not entries:
        print('No saved networks are loaded yet. Restart MiSTer if you just added one.')
        return
    if len(entries) == 1:
        print('Only one Wi-Fi network is loaded; there is nothing to switch to.')
        return
    # Use the config's decoded SSID values for display if wpa_cli ever
    # returns an encoded form. Network *IDs* remain untouched for switching.
    known = {name.encode('utf-8').hex().lower(): name
             for _, _, _, name in parse_config_networks(read_wifi_config())
             if not name.startswith('<hex SSID ')}
    entries = [(ident, known.get(name.lower(), name), flags)
               for ident, name, flags in entries]
    print('\nAVAILABLE SAVED NETWORKS')
    for ix, (_ident, name, flags) in enumerate(entries, 1):
        current = ' (connected)' if 'CURRENT' in flags else ''
        print('  [{}] {}{}'.format(ix, name, current))
    response = input('Network number (Enter cancels): ').strip()
    if not response.isdigit() or not 1 <= int(response) <= len(entries):
        print('Cancelled.')
        return
    ident, name, flags = entries[int(response) - 1]
    if 'CURRENT' in flags:
        print('Already connected to {}.'.format(name))
        return
    print('Switching Wi-Fi may disconnect SSH/WinSCP. Saved priorities will not change.')
    if not yes('Switch to {} now?'.format(name)):
        print('Cancelled.')
        return
    out, err, rc = command(['wpa_cli', '-p', cli_path, '-i', iface, 'select_network', ident], timeout=6)
    if rc or out.strip() != 'OK':
        print('Switch failed: {}'.format((err or out)[:200]))
    else:
        print('Switch requested. Reconnect SSH if needed.')


def clear_screen():
    """Clear an interactive terminal without affecting redirected output."""
    if sys.stdout.isatty() and os.environ.get("TERM", "") not in ("", "dumb"):
        print("\033[2J\033[H", end="", flush=True)


def setup_wifi():
    while True:
        clear_screen()
        print('\n' + '=' * 58)
        print('            WI-FI SETUP / SAVED NETWORKS')
        print('=' * 58)
        print('  [1] Scan and add a Wi-Fi network')
        print('  [2] View saved Wi-Fi networks and priorities')
        print('  [3] Choose preferred saved network')
        print('  [4] Remove a saved Wi-Fi network')
        print('  [5] Change saved Wi-Fi password')
        print('  [6] Switch to another saved network')
        print('  [7] Return to main menu')
        print('  Saved changes may need Wi-Fi restart. Switching may disconnect SSH.')
        try:
            choice = input('\n  Choose [1-7]: ').strip()
            if choice != '7':
                clear_screen()
            if choice == '1':
                add_network()
            elif choice == '2':
                try:
                    show_saved_networks(parse_config_networks(read_wifi_config()))
                except (OSError, ValueError) as exc:
                    print('Unable to list networks: {}'.format(exc))
            elif choice == '3':
                set_preferred()
            elif choice == '4':
                manage_networks('remove')
            elif choice == '5':
                change_password()
            elif choice == '6':
                switch_saved_network()
            elif choice == '7':
                return
            else:
                print('Choose 1 through 7.')
            if choice != '7':
                input('\n  Press Enter to return to Wi-Fi setup...')
        except (EOFError, KeyboardInterrupt):
            print('\nReturning to main menu.')
            return

def parse_scan(scan_text):
    """One row per access point (BSSID), even when SSIDs repeat."""
    networks = []
    current = None
    for line in scan_text.splitlines() + ['BSS END']:
        m = re.match(r'^BSS\s+([0-9a-fA-F:]{17})(?:\(on\s+[^)]*\))?', line)
        if m or line == 'BSS END':
            if current and current['ssid'] and current['frequency']:
                networks.append(current)
            current = {'bssid': m.group(1).lower(), 'ssid': '',
                       'frequency': '', 'signal': None} if m else None
            continue
        if current is None:
            continue
        m = re.match(r'^\s*freq:\s*(\d+)', line)
        if m:
            current['frequency'] = int(m.group(1))
        m = re.match(r'^\s*signal:\s*(-?[\d.]+)', line)
        if m:
            current['signal'] = float(m.group(1))
        m = re.match(r'^\s*SSID:\s*(.*)', line)
        if m:
            current['ssid'] = m.group(1).strip()
    return sorted(networks, key=lambda n: n['signal'] if n['signal'] is not None else -999,
                  reverse=True)


def scan_networks():
    iface = wireless_interface()
    if not iface:
        print('No Wi-Fi interface found.')
        return
    link = wifi_link(iface)
    connected_bssid = extract(r'^Connected to\s+([0-9a-fA-F:]{17})', link, '', re.M).lower()
    print('\nScanning nearby Wi-Fi access points (read-only)...')
    out, err, rc = command(['iw', 'dev', iface, 'scan'], timeout=25)
    if rc:
        print('Scan unavailable: {}'.format(err or out[-300:]))
        return
    networks = parse_scan(out)
    if not networks:
        print('No visible SSIDs found.')
        return
    print('\n* = currently connected access point')
    print('{:<2} {:<22} {:<6} {:>10} {:<17}'.format('', 'SSID', 'Band', 'Signal', 'BSSID'))
    print('-' * 75)
    for net in networks[:50]:
        freq = net['frequency']
        band = '2.4GHz' if 2400 <= freq <= 2500 else '5GHz' if 4900 <= freq < 5925 else '6GHz' if 5925 <= freq <= 7125 else '?'
        sig = '{:.0f} dBm'.format(net['signal']) if net['signal'] is not None else 'unknown'
        active = bool(connected_bssid and net['bssid'] == connected_bssid)
        row = '{:<2} {:<22} {:<6} {:>10} {:<17}'.format(
            '*' if active else '', net['ssid'][:22], band, sig, net['bssid'])
        print(tint(row, '1;32') if active else row)
    if connected_bssid and not any(net['bssid'] == connected_bssid for net in networks):
        print('\nConnected BSSID {} was not returned by this scan.'.format(connected_bssid))
    print('Repeated SSIDs indicate different access points; stronger signal alone does not guarantee faster speed.')


# ANSI colors are optional: plain ASCII remains readable through SSH and serial.
COLOR = sys.stdout.isatty() and not os.environ.get('NO_COLOR') and os.environ.get('TERM', '') != 'dumb'


def tint(text, code):
    return '\033[{}m{}\033[0m'.format(code, text) if COLOR else text


def panel_line(text='', width=62):
    # Truncate variable-width content so unusual SSIDs cannot break the border.
    if len(text) > width - 4:
        text = text[:width - 7] + '...'
    return '  | ' + text.ljust(width - 4) + ' |'


def show_menu(iface, link):
    ssid = extract(r'^\s*SSID:\s*(.*)$', link, 'Not connected', re.M)
    if not iface:
        ssid = 'No wireless adapter detected'
    freq = extract(r'^\s*freq:\s*(\d+)', link, '', re.M)
    signal = extract(r'^\s*signal:\s*(-?\d+)\s*dBm', link, '', re.M)
    rx = extract(r'^\s*rx bitrate:\s*([\d.]+\s*MBit/s)', link, '', re.M)
    tx = extract(r'^\s*tx bitrate:\s*([\d.]+\s*MBit/s)', link, '', re.M)
    band = ('5 GHz' if freq and 4900 <= int(freq) < 5925 else
            '2.4 GHz' if freq and 2400 <= int(freq) < 2500 else
            '6 GHz' if freq and 5925 <= int(freq) <= 7125 else 'Unknown')
    width = 62
    print('\n' + tint('  +' + '-' * (width - 2) + '+', '36'))
    print(tint(panel_line('        MiSTer Wi-Fi Setup & Diagnostics  v26', width), '1;36'))
    print(tint('  +' + '-' * (width - 2) + '+', '36'))
    print(panel_line('NETWORK STATUS', width))
    print(panel_line('  SSID:   {}'.format(ssid), width))
    print(panel_line('  IPv4:   {}'.format(ip_address(iface) if iface else 'N/A'), width))
    print(panel_line('  Band:   {}    Signal: {}'.format(band, '{} dBm'.format(signal) if signal else 'N/A'), width))
    print(panel_line('  Link:   RX {}  /  TX {}'.format(rx or 'N/A', tx or 'N/A'), width))
    priorities = saved_priorities()
    if priorities and ssid not in ('Not connected', 'No wireless adapter detected'):
        preferred = max(priorities, key=lambda item: int(item[1]))[0]
        if ssid != preferred:
            print(panel_line('  Preferred: {} (currently on {})'.format(preferred, ssid), width))
    print(tint('  +' + '-' * (width - 2) + '+', '36'))
    print(panel_line('DIAGNOSTICS', width))
    print(panel_line('  [1] Full Wi-Fi health check + router ping', width))
    print(panel_line('  [2] Quick connection status', width))
    print(panel_line('  [3] Scan nearby access points (with BSSID)', width))
    print(panel_line('', width))
    print(panel_line('WI-FI SETUP', width))
    print(panel_line('  [4] Connect / manage saved networks (built-in)', width))
    print(panel_line('', width))
    print(panel_line('  [5] Exit', width))
    print(tint('  +' + '-' * (width - 2) + '+', '36'))
    print('  Setup changes are saved for reboot; diagnostics are read-only.')


def run_diagnostics_with_spinner(count, ping=True):
    """Animate progress while diagnostics run (gateway ping optional)."""
    finished = threading.Event()
    result = {}

    def worker():
        try:
            result['report'] = diagnostics(ping=ping, ping_count=count)
        except BaseException as exc:
            result['error'] = exc
        finally:
            finished.set()

    task = threading.Thread(target=worker, daemon=True)
    task.start()
    frames = ('|', '/', '-', "\\")
    index = 0
    interactive = sys.stdout.isatty()
    if interactive:
        while not finished.wait(0.12):
            sys.stdout.write('\r  {} {}  '.format('Testing Wi-Fi and gateway' if ping else 'Checking Wi-Fi status', frames[index % len(frames)]))
            sys.stdout.flush()
            index += 1
        sys.stdout.write('\r' + ' ' * 45 + '\r')
        sys.stdout.flush()
    else:
        finished.wait()
    task.join()
    if 'error' in result:
        raise result['error']
    return result['report']


def main():
    if sys.version_info < (3, 6):
        print('Python 3.6 or newer required.')
        return 1
    while True:
        clear_screen()
        iface = wireless_interface()
        link = wifi_link(iface) if iface else ''
        show_menu(iface, link)
        try:
            choice = input('\n  Choose an option [1-5]: ').strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if choice in ('1', '2'):
            clear_screen()
            ping = choice == '1'
            count = 20
            print('MiSTer Wi-Fi Diagnostics v26')
            print('=' * 55)
            print('TEST IN PROGRESS - {} connection check'.format(
                'quick' if choice == '2' else 'full'))
            print('Checking wireless connection{}...'.format(' and gateway' if ping else ''))
            if ping:
                print('Running {}-packet router ping; please wait...'.format(count), flush=True)
            else:
                print('Reading Wi-Fi status; no router ping.', flush=True)
            report = run_diagnostics_with_spinner(count, ping=ping)
            print('\n' + colorize_diagnostic_report(report))
            if choice == '1':
                try:
                    save_report(report)
                except OSError as exc:
                    print('Could not save report: {}'.format(exc))
        elif choice == '3':
            clear_screen()
            scan_networks()
        elif choice == '4':
            setup_wifi()
        elif choice == '5':
            print('Goodbye.')
            return 0
        else:
            print('Please choose 1 through 5.')
        # Pause only after results that users may want time to read.
        # Returning from Wi-Fi Setup or an invalid choice should be immediate.
        if choice in ('1', '2', '3'):
            try:
                input('\n  Press Enter to return to the menu...')
            except (EOFError, KeyboardInterrupt):
                print()
                return 0


if __name__ == '__main__':
    sys.exit(main())
