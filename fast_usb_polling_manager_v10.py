#!/usr/bin/env python3
"""MiSTer Fast USB Polling Manager — simple interactive setup and status.

Based on the MiSTer-devel/Scripts_MiSTer fast_USB_polling_on.sh and
fast_USB_polling_off.sh (GPL-3.0-or-later).
Changes to /media/fat/linux/u-boot.txt take effect on the next boot.
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path

CONFIG = Path(os.environ.get('MISTER_UBOOT_PATH', '/media/fat/linux/u-boot.txt'))
CMDLINE = Path(os.environ.get('MISTER_CMDLINE_PATH', '/proc/cmdline'))
PARAM_RE = re.compile(r'(?<![\w.])(?:v=)?(usbhid\.jspoll|xpad\.cpoll)\s*=\s*([^\s#]+)')
STRIP_RE = re.compile(r'(?<![\w.])(?:usbhid\.jspoll|xpad\.cpoll)\s*=\s*[^\s#]+')


def values(text):
    found = {'usbhid.jspoll': [], 'xpad.cpoll': []}
    for line in text.splitlines():
        if line.lstrip().startswith('#'):
            continue
        for match in PARAM_RE.finditer(line.split('#', 1)[0]):
            found[match.group(1)].append(match.group(2))
    return found


def describe(found):
    hid, xpad = found['usbhid.jspoll'], found['xpad.cpoll']
    if not hid and not xpad:
        return 'DEFAULT (no forced polling specified)', None
    if len(hid) == len(xpad) == 1 and hid[0] == xpad[0] == '1':
        return 'ON (1 ms / 1000 Hz requested)', True
    if len(hid) == len(xpad) == 1 and hid[0] == xpad[0] == '0':
        return 'OFF (fast polling disabled)', False
    return 'CUSTOM / MIXED (see settings)', None


def read_text(path):
    if not path.exists():
        return ''
    return path.read_text(encoding='utf-8', errors='replace')


def updated_config(text, enabled):
    """Normalize polling options onto the sole v= line, preserving other options."""
    bit = int(enabled)
    newline = '\r\n' if '\r\n' in text else '\n'
    lines = []
    v_pos = None
    for original in text.splitlines():
        if original.lstrip().startswith('#'):
            lines.append(original)
            continue
        line = original
        # Repair exactly the malformed concatenation seen in the user's file.
        line = re.sub(r'(loglevel=\d+)(?=(?:usbhid\.jspoll|xpad\.cpoll)=)',
                      r'\1 ', line)
        is_v = bool(re.match(r'^\s*v=', line))
        if is_v:
            if v_pos is not None:
                raise ValueError('Multiple v= lines; refusing to change boot options.')
            v_pos = len(lines)
        # Strip recognized polling tokens without joining neighboring tokens.
        clean = STRIP_RE.sub(' ', line)
        clean = re.sub(r' {2,}', ' ', clean).rstrip()
        # Remove polling-only lines, not unrelated settings or comments.
        if clean.strip():
            lines.append(clean)
    options = 'usbhid.jspoll={} xpad.cpoll={}'.format(bit, bit)
    if v_pos is None:
        lines.append('v=loglevel=4 ' + options)
    else:
        current = lines[v_pos].rstrip()
        if not re.search(r'(?<!\S)loglevel=\d+(?=\s|$)|^\s*v=loglevel=\d+(?=\s|$)', current):
            current = re.sub(r'^(\s*v=)', r'\1loglevel=4 ', current).rstrip()
        lines[v_pos] = current + ' ' + options
    return newline.join(lines) + (newline if lines else '')


def write_safely(content):
    """Atomic config replacement; temporary file is removed automatically."""
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.usb-poll-', dir=str(CONFIG.parent))
    try:
        if CONFIG.exists():
            os.fchmod(fd, CONFIG.stat().st_mode & 0o777)
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, CONFIG)
        subprocess.run(['sync'], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def status(config, running):
    saved_label, saved_state = describe(values(config))
    if running is None:
        return saved_label, saved_state, 'UNKNOWN (cannot read kernel)', None, False

    running_label, running_state = describe(values(running))
    # Display ACTIVE only when both options are actually present and set to 1.
    if running_state is True:
        active = 'YES (1 ms polling requested at boot)'
    elif running_state is False:
        active = 'NO (explicitly disabled at boot)'
    elif 'loglevel=' in running and re.search(
            r'loglevel=\d+(?:usbhid\.jspoll|xpad\.cpoll)=', running):
        active = 'NO (malformed kernel boot parameters)'
    elif running_state is None and values(running) == values(''):
        active = 'NO (polling not specified at boot)'
    else:
        active = 'NO / CUSTOM (check detailed settings)'
    pending = values(config) != values(running)
    return saved_label, saved_state, active, running_state, pending


def box_line(s, width=60):
    return '| ' + s[:width - 4].ljust(width - 4) + ' |'


def pause():
    try:
        input('\nPress Enter to return...')
    except (EOFError, KeyboardInterrupt):
        pass


def main():
    while True:
        try:
            saved = read_text(CONFIG)
            running = read_text(CMDLINE) if CMDLINE.exists() else None
            config_label, _, active_label, _, pending = status(saved, running)
        except OSError as exc:
            print('Unable to read USB polling settings: {}'.format(exc))
            return 1

        print('\n+' + '-' * 58 + '+')
        print(box_line('MiSTer Fast USB Polling Manager v10'))
        print('+' + '-' * 58 + '+')
        print(box_line('CURRENT STATUS'))
        print(box_line('  ACTIVE: {}'.format(active_label)))
        print(box_line('  SAVED:  {}'.format(config_label)))
        if pending:
            print(box_line('  REBOOT REQUIRED to apply saved settings.'))
        print('+' + '-' * 58 + '+')
        for item in ('[1] Enable fast polling (1 ms / 1000 Hz)',
                     '[2] Disable fast polling',
                     '[3] View detailed settings',
                     '[4] Reboot MiSTer',
                     '[5] Exit'):
            print(box_line('  ' + item))
        print('+' + '-' * 58 + '+')
        try:
            choice = input('  Choose [1-5]: ').strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if choice == '5':
            return 0
        if choice == '3':
            print('\nSaved boot settings ({})'.format(CONFIG))
            lines = [line for line in saved.splitlines() if 'jspoll' in line or 'cpoll' in line]
            print('\n'.join('  ' + s for s in lines) if lines else '  (none)')
            print('\nRunning kernel command line ({})'.format(CMDLINE))
            if running is None:
                print('  Unavailable')
            else:
                matched = PARAM_RE.findall(running)
                print('  ' + ('  '.join('{}={}'.format(k, v) for k, v in matched) if matched else '(no explicit polling parameters)'))
            pause()
            continue
        if choice == '4':
            if input('Reboot MiSTer now? [y/N]: ').strip().lower() == 'y':
                try:
                    subprocess.run(['reboot'], check=True)
                except (OSError, subprocess.CalledProcessError) as exc:
                    print('Reboot failed: {}'.format(exc))
                    pause()
            continue
        if choice not in ('1', '2'):
            print('Invalid choice.')
            continue
        enabled = choice == '1'
        # Normalize layout even when polling values already match.
        try:
            new_text = updated_config(saved, enabled)
        except ValueError as exc:
            print('Cannot update: {}'.format(exc))
            continue
        if new_text == saved:
            print('Already saved that way. Nothing changed.')
            if pending:
                print('REBOOT REQUIRED: running settings do not match saved settings.')
            continue
        word = 'ENABLE' if enabled else 'DISABLE'
        if input('{} fast USB polling? [y/N]: '.format(word)).strip().lower() != 'y':
            continue
        try:
            write_safely(new_text)
        except OSError as exc:
            print('Save failed: {}'.format(exc))
            pause()
            continue
        print('Saved. Changes take effect after reboot.')
        if enabled:
            print('Note: Some controllers may not work well with 1000 Hz polling.')
        if input('Reboot now? [y/N]: ').strip().lower() == 'y':
            try:
                subprocess.run(['reboot'], check=True)
            except (OSError, subprocess.CalledProcessError) as exc:
                print('Reboot failed: {}'.format(exc))
                pause()


if __name__ == '__main__':
    raise SystemExit(main())
