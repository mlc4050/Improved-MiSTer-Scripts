#!/usr/bin/env python3
"""MiSTer Ethernet MAC Address Manager v1.

Based on the MiSTer mac_address_change.sh concept (GPL-3.0-or-later).
Changes only ethaddr in /media/fat/linux/u-boot.txt; reboot to apply.
"""
import os
import re
import secrets
import stat
import subprocess
import tempfile
from pathlib import Path

CONFIG = Path(os.environ.get('MISTER_UBOOT_PATH', '/media/fat/linux/u-boot.txt'))
ETH0 = Path(os.environ.get('MISTER_ETH0_ADDRESS_PATH', '/sys/class/net/eth0/address'))
# Match only an ethaddr assignment at the beginning of a line; retain other lines verbatim.
ETHADDR = re.compile(r'^(\s*ethaddr\s*=\s*)([^\s#]*)(.*)$', re.IGNORECASE)


def new_mac():
    octets = bytearray(secrets.token_bytes(6))
    octets[0] = (octets[0] | 0x02) & 0xFE  # locally administered, unicast
    return ':'.join('{:02X}'.format(o) for o in octets)


def saved_macs(content):
    result = []
    for line in content.splitlines():
        if line.lstrip().startswith('#'):
            continue
        match = ETHADDR.match(line)
        if match:
            result.append(match.group(2))
    return result


def modify(content, mac):
    """Change just ethaddr, preserving other lines, line endings and options."""
    lines = content.splitlines(keepends=True)
    output = []
    replaced = False
    for line in lines:
        body = line.rstrip('\r\n')
        ending = line[len(body):]
        match = ETHADDR.match(body) if not body.lstrip().startswith('#') else None
        if match:
            if not replaced:
                output.append(match.group(1) + mac + match.group(3) + ending)
                replaced = True
            # Remove duplicate active ethaddr assignments, retaining all unrelated lines.
        else:
            output.append(line)
    if not replaced:
        ending = '\r\n' if '\r\n' in content else '\n'
        if content and not content.endswith(('\n', '\r')):
            output.append(ending)
        output.append('ethaddr=' + mac + ending)
    return ''.join(output)


def atomic_write(content):
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.mac-address-', dir=str(CONFIG.parent))
    try:
        if CONFIG.exists():
            os.fchmod(fd, stat.S_IMODE(CONFIG.stat().st_mode))
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, CONFIG)
        subprocess.run(['sync'], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main():
    if not Path('/media/fat/MiSTer').exists() and 'MISTER_UBOOT_PATH' not in os.environ:
        print('This script must be run on a MiSTer system.')
        return 1
    try:
        if CONFIG.exists():
            content = CONFIG.read_bytes().decode('utf-8')
        else:
            content = ''
        running = ETH0.read_text().strip().upper() if ETH0.exists() else 'UNAVAILABLE'
    except (OSError, UnicodeError) as exc:
        print('Unable to read MAC settings: {}'.format(exc))
        return 1

    while True:
        saved = saved_macs(content)
        saved_label = ', '.join(saved) if saved else 'NOT SET'
        print('\n+----------------------------------------------------------+')
        print('|              MiSTer MAC Address Manager v1               |')
        print('+----------------------------------------------------------+')
        print('  Ethernet (eth0): {}'.format(running))
        print('  Saved (next boot): {}'.format(saved_label))
        print('\n  [1] Generate and save a new Ethernet MAC')
        print('  [2] Exit')
        try:
            choice = input('\nSelect: ').strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if choice == '2' or choice.lower() in ('q', 'quit'):
            return 0
        if choice != '1':
            continue
        mac = new_mac()
        while mac == running or mac in [v.upper() for v in saved]:
            mac = new_mac()
        print('\nGenerated MAC: {}'.format(mac))
        try:
            confirm = input('Save this MAC? [y/N]: ').strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if confirm not in ('y', 'yes'):
            continue
        updated = modify(content, mac)
        if updated == content:
            print('Already saved; no changes needed.')
            continue
        try:
            atomic_write(updated)
        except OSError as exc:
            print('Unable to save MAC: {}'.format(exc))
            return 1
        content = updated
        print('Saved. Your other u-boot.txt settings were preserved.')
        print('Reboot MiSTer to activate the new Ethernet MAC.')


if __name__ == '__main__':
    raise SystemExit(main())
