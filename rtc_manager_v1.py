#!/usr/bin/env python3
"""MiSTer RTC & Time Manager v1.

Based on rtc.sh by Alessandro "Locutus73" Miele (2019), from
MiSTer-devel/Scripts_MiSTer. SPDX-License-Identifier: GPL-3.0-or-later
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
from datetime import datetime, timezone

VERSION = 'v1'
DEFAULT_SERVER = '0.pool.ntp.org'


def run(args, timeout=30):
    try:
        result = subprocess.run(args, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(str(exc)) from exc
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip() or
                           '{} exited with {}'.format(args[0], result.returncode))
    return result.stdout.strip()


def rtc_devices():
    return sorted(str(p) for p in Path('/dev').glob('rtc*'))


def show_status():
    print('\n  Local time: ' + datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z (%z)'))
    print('  UTC time:   ' + datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'))
    devices = rtc_devices()
    print('  RTC device: ' + (', '.join(devices) if devices else 'NOT DETECTED'))
    if devices and shutil.which('hwclock'):
        try:
            print('  RTC read:   ' + run(['hwclock', '--show', '--utc'], timeout=8))
        except RuntimeError as exc:
            print('  RTC read unavailable: ' + str(exc))
    print('  NTP utility: ' + (shutil.which('ntpdate') or 'NOT INSTALLED'))


def sync_system(server):
    if not shutil.which('ntpdate'):
        raise RuntimeError('ntpdate is not installed.')
    if not server or server.startswith('-') or any(c.isspace() for c in server):
        raise ValueError('Enter a single NTP hostname or address.')
    print('Syncing system time with {}...'.format(server), flush=True)
    output = run(['ntpdate', '-b', '-u', server], timeout=45)
    if output:
        print(output)
    print('System time synchronized. A hardware RTC is not required for this action.')


def save_rtc():
    if not rtc_devices():
        raise RuntimeError('No RTC device detected. System time can still be synchronized over NTP.')
    if not shutil.which('hwclock'):
        raise RuntimeError('hwclock is not installed.')
    # Avoid updating /etc/adjtime, so a read-only root need not be remounted.
    run(['hwclock', '--systohc', '--utc', '--noadjfile'], timeout=12)
    print('Hardware RTC updated from system time (stored as UTC).')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--status', action='store_true', help='Show status and exit without changing time')
    args = parser.parse_args(argv)
    if args.status:
        show_status()
        return 0
    if not Path('/media/fat/MiSTer').exists():
        print('Run this utility on your MiSTer.')
        return 1
    server = DEFAULT_SERVER
    try:
        while True:
            print('\n+' + '-' * 64 + '+')
            print('|{:^64}|'.format('MiSTer RTC & Time Manager ' + VERSION))
            print('+' + '-' * 64 + '+')
            show_status()
            print('  NTP server: ' + server)
            print('\n  [1] Sync system time from NTP')
            print('  [2] Sync from NTP, then update hardware RTC')
            print('  [3] Save current system time to hardware RTC')
            print('  [4] Change NTP server for this session')
            print('  [5] Refresh status\n  [Q] Exit')
            choice = input('\nSelect: ').strip().lower()
            if choice in ('q', 'quit'):
                return 0
            if choice == '4':
                value = input('NTP hostname (blank keeps current): ').strip()
                if value and not value.startswith('-') and not any(c.isspace() for c in value):
                    server = value
                elif value:
                    print('Invalid server name.')
                continue
            if choice == '5':
                continue
            if choice not in ('1', '2', '3'):
                print('Choose a listed option.')
                continue
            if os.geteuid() != 0:
                print('Root access is required to change system or RTC time.')
                continue
            if choice == '2' and not rtc_devices():
                print('No hardware RTC detected. Use option 1 to sync system time only.')
                continue
            prompt = ('Save the current system clock to the RTC? Verify the time above first.'
                      if choice == '3' else 'Synchronize the system clock now? This may jump the current time.')
            if input(prompt + ' [y/N]: ').strip().lower() not in ('y', 'yes'):
                continue
            try:
                if choice in ('1', '2'):
                    sync_system(server)
                if choice in ('2', '3'):
                    save_rtc()
            except (RuntimeError, ValueError) as exc:
                print('Action failed: ' + str(exc))
            input('\nPress Enter to return to the menu...')
    except (KeyboardInterrupt, EOFError):
        print('\nCancelled.')
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
