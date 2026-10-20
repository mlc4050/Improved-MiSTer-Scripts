#!/usr/bin/env python3
"""MiSTer FTP & SSH Manager v2. Based on the MiSTer Scripts_MiSTer on/off helpers.

Combines service start/stop, boot enabling, and optional MiSTer firewall rules.
No persistent backups; atomic temporary files are deleted automatically.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

VERSION = 'v2'
INIT = Path('/etc/init.d')
RULES = Path('/media/fat/linux/iptables.up.rules')
FIREWALL_HOOK = Path('/etc/network/if-pre-up.d/iptables')
SERVICES = {
    'FTP': {'file': 'S50proftpd', 'port': 21, 'process': 'proftpd'},
    'SSH': {'file': 'S50sshd', 'port': 22, 'process': 'sshd'},
}


def cmd(*args):
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def is_running(name):
    result = cmd('pidof', name)
    if result.returncode == 0 and result.stdout.strip():
        return True
    # /proc fallback (including full-path argv[0] differences)
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if (entry / 'comm').read_text().strip() == name:
                return True
        except OSError:
            pass
    return False


def boot_state(spec):
    enabled = (INIT / spec['file']).exists()
    disabled = (INIT / ('_' + spec['file'])).exists()
    if enabled and not disabled:
        return 'ON'
    if disabled and not enabled:
        return 'OFF'
    if enabled and disabled:
        return 'CONFLICT'
    return 'UNKNOWN'


def firewall_state(port):
    if not RULES.exists():
        return 'NO RULES FILE'
    try:
        lines = RULES.read_text().splitlines()
    except OSError:
        return 'UNKNOWN'
    matched = [line for line in lines if re.search(r'--dport\s+' + str(port) + r'(?!\d)', line)]
    if not matched:
        return 'NO PORT RULE'
    active = [not line.lstrip().startswith('#') for line in matched]
    if all(active):
        return 'ALLOWED'
    if not any(active):
        return 'BLOCKED'
    return 'MIXED'


def status(name):
    spec = SERVICES[name]
    try:
        running = 'RUNNING' if is_running(spec['process']) else 'STOPPED'
    except OSError:
        running = 'UNKNOWN'
    return running, boot_state(spec), firewall_state(spec['port'])


def root_readonly():
    for line in Path('/proc/mounts').read_text().splitlines():
        fields = line.split()
        if len(fields) >= 4 and fields[1] == '/':
            return 'ro' in fields[3].split(',')
    raise RuntimeError('Cannot determine root mount state')


def set_boot(spec, enable):
    src = INIT / (('_' if enable else '') + spec['file'])
    dst = INIT / (('' if enable else '_') + spec['file'])
    if dst.exists() and not src.exists():
        return False
    if src.exists() and dst.exists():
        raise RuntimeError('Both enabled and disabled startup scripts exist; resolve manually.')
    if not src.exists():
        raise RuntimeError('Startup script missing: ' + str(src))
    ro = root_readonly()
    try:
        if ro:
            remount = cmd('mount', '-o', 'remount,rw', '/')
            if remount.returncode:
                raise RuntimeError('Unable to remount root writable: ' + remount.stderr.strip())
        src.rename(dst)
    finally:
        if ro:
            remount = cmd('mount', '-o', 'remount,ro', '/')
            if remount.returncode:
                print('WARNING: Could not restore read-only root filesystem.')
    return True


def update_firewall(port, enable):
    if not RULES.is_file():
        return False
    original = RULES.read_text()
    output = []
    for line in original.splitlines(keepends=True):
        if re.search(r'--dport\s+' + str(port) + r'(?!\d)', line):
            if enable:
                line = re.sub(r'^(\s*)#+', r'\1', line)
            elif not line.lstrip().startswith('#'):
                line = re.sub(r'^(\s*)', r'\1#', line, count=1)
        output.append(line)
    updated = ''.join(output)
    if updated == original:
        return False
    # Atomic replacement avoids partly written rule files; temporary file always cleaned.
    tmpname = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=str(RULES.parent), prefix='.iptables.',
                                         suffix='.tmp', delete=False) as temp:
            tmpname = temp.name
            temp.write(updated)
            temp.flush()
            os.fsync(temp.fileno())
        shutil.copymode(RULES, tmpname)
        os.replace(tmpname, RULES)
        tmpname = None
    finally:
        if tmpname and os.path.exists(tmpname):
            os.unlink(tmpname)
    return True


def change(name, enable):
    spec = SERVICES[name]
    running, boot, firewall = status(name)
    target = 'ON' if enable else 'OFF'
    target_running = 'RUNNING' if enable else 'STOPPED'
    desired_firewall = 'ALLOWED' if enable else 'BLOCKED'
    if boot == target and running == target_running and firewall in (desired_firewall, 'NO RULES FILE', 'NO PORT RULE'):
        print('\nAlready configured. No changes made.')
        return
    if name == 'SSH' and not enable and (os.environ.get('SSH_CONNECTION') or os.environ.get('SSH_CLIENT')):
        print('\nSSH cannot be disabled from an SSH session. Use the MiSTer locally.')
        return
    print('\n{} {}?'.format('Enable' if enable else 'Disable', name))
    print('This changes the service now AND at startup.')
    if name == 'SSH' and not enable:
        print('WARNING: Disabling SSH prevents remote SSH access until re-enabled locally.')
    if input('Type YES to confirm: ').strip() != 'YES':
        print('Cancelled.')
        return
    try:
        if os.geteuid() != 0:
            raise RuntimeError('Run as root on MiSTer.')
        # Stop service first when disabling, as in original scripts.
        if not enable and running == 'RUNNING':
            stop_path = INIT / spec['file']
            if not stop_path.exists():
                raise RuntimeError('Cannot stop service: ' + str(stop_path) + ' missing')
            response = cmd(str(stop_path), 'stop')
            if response.returncode != 0 and is_running(spec['process']):
                raise RuntimeError('Stopping service failed: ' + response.stderr.strip())
        if boot != target:
            set_boot(spec, enable)
        rules_changed = update_firewall(spec['port'], enable)
        if rules_changed and FIREWALL_HOOK.is_file():
            response = cmd(str(FIREWALL_HOOK))
            if response.returncode:
                print('WARNING: Firewall reload failed:', response.stderr.strip())
        if enable and not is_running(spec['process']):
            start_path = INIT / spec['file']
            if not start_path.is_file():
                raise RuntimeError('Cannot start service: ' + str(start_path) + ' missing')
            response = cmd(str(start_path), 'start')
            if response.returncode and not is_running(spec['process']):
                raise RuntimeError('Starting service failed: ' + response.stderr.strip())
        print('\nUpdated. Current status:')
        print_service(name)
    except (OSError, RuntimeError) as error:
        print('\nERROR:', error)
        print('Check status below; some changes may have been applied.')
        print_service(name)


def print_service(name):
    running, boot, firewall = status(name)
    print('  {:3}  {:8}  Startup: {:8}  Firewall: {}'.format(name, running, boot, firewall))


def menu():
    if not Path('/media/fat/MiSTer').exists():
        print('This utility must be run on a MiSTer system.')
        return 1
    while True:
        print('\n' + '+' + '-' * 62 + '+')
        print('|{:^62}|'.format('MiSTer FTP & SSH Manager ' + VERSION))
        print('+' + '-' * 62 + '+')
        print('| {:60} |'.format('CURRENT STATUS'))
        for name in ('FTP', 'SSH'):
            running, boot, firewall = status(name)
            line = '{:3} {:8}   Startup: {:8}   Firewall: {}'.format(name, running, boot, firewall)
            print('| {:60} |'.format(line))
        print('+' + '-' * 62 + '+')
        for item in ('[1] Enable FTP', '[2] Disable FTP', '[3] Enable SSH',
                     '[4] Disable SSH', '[5] Refresh status', '[6] Exit'):
            print('| {:60} |'.format(item))
        print('+' + '-' * 62 + '+')
        if any(firewall_state(SERVICES[name]['port']) in ('NO RULES FILE', 'NO PORT RULE') for name in ('FTP', 'SSH')):
            print('  Firewall status unavailable: no matching custom rule to inspect.')
        try:
            choice = input('Choose [1-6]: ').strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return 0
        if choice == '6':
            return 0
        if choice == '5':
            continue
        actions = {'1': ('FTP', True), '2': ('FTP', False),
                   '3': ('SSH', True), '4': ('SSH', False)}
        if choice in actions:
            change(*actions[choice])
        else:
            print('Invalid choice.')


if __name__ == '__main__':
    sys.exit(menu())
