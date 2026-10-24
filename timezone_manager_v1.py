#!/usr/bin/env python3
"""MiSTer Timezone Manager v1.

Based on timezone.sh by Alessandro "Locutus73" Miele (2019), from
MiSTer-devel/Scripts_MiSTer. SPDX-License-Identifier: GPL-3.0-or-later
"""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
import time
import urllib.request

VERSION = 'v1'
ZONE_ROOT = Path('/usr/share/zoneinfo')
DESTINATION = Path('/media/fat/linux/timezone')


def available_zones(root=ZONE_ROOT):
    zones = {}
    for path in root.rglob('*'):
        rel = path.relative_to(root)
        if any(part in ('posix', 'right') for part in rel.parts):
            continue
        if not path.is_file():
            continue
        try:
            with path.open('rb') as source:
                if source.read(4) == b'TZif':
                    zones[rel.as_posix()] = path
        except OSError:
            continue
    return zones


def matching_zones(query, zones):
    query = query.strip().casefold().replace(' ', '_')
    return sorted(name for name in zones if query in name.casefold())


def saved_zone(zones, destination=DESTINATION):
    try:
        data = destination.read_bytes()
    except OSError:
        return 'UNAVAILABLE'
    matches = []
    for name, path in zones.items():
        try:
            if path.read_bytes() == data:
                matches.append(name)
        except OSError:
            pass
    if not matches:
        return 'Custom zone file (no installed match)'
    # Identical aliases cannot uniquely identify the zone originally selected.
    preferred = sorted(matches, key=lambda name: ('/' not in name, name.startswith(('US/', 'Canada/', 'Etc/')), name))
    return preferred[0] + (' (equivalent aliases also exist)' if len(matches) > 1 else '')


def write_zone(name, zones, destination=DESTINATION):
    # Resolve via the enumerated names, never a user-provided filesystem path.
    if name not in zones:
        raise ValueError('Timezone is not in the installed timezone database.')
    data = zones[name].read_bytes()
    if not data.startswith(b'TZif'):
        raise ValueError('Selected timezone file is invalid.')
    if destination.exists() and destination.read_bytes() == data:
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=str(destination.parent), prefix='.timezone-', delete=False) as output:
            temp = output.name
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temp, 0o644)
        os.replace(temp, str(destination))
        temp = None
    finally:
        if temp and os.path.exists(temp):
            os.unlink(temp)
    if hasattr(time, 'tzset'):
        time.tzset()
    return True


def detect_zone():
    request = urllib.request.Request('https://ipwho.is/?fields=success,message,timezone.id',
                                     headers={'User-Agent': 'MiSTer-Timezone-Manager/1'})
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = response.read(65537)
    if len(payload) > 65536:
        raise ValueError('Timezone service returned an oversized response.')
    data = json.loads(payload)
    if not isinstance(data, dict) or data.get('success') is not True:
        raise ValueError('Timezone service could not determine your timezone.')
    details = data.get('timezone')
    if not isinstance(details, dict):
        raise ValueError('Timezone service returned invalid timezone details.')
    zone = details.get('id')
    if not isinstance(zone, str) or not zone:
        raise ValueError('Timezone service returned no timezone.')
    return zone


def choose_zone(zones):
    while True:
        query = input('Enter a timezone or city (e.g. America/Chicago, London, UTC; blank cancels): ').strip()
        if not query:
            return None
        exact = next((name for name in zones if name.casefold() == query.casefold()), None)
        if exact:
            return exact
        matches = matching_zones(query, zones)
        if not matches:
            print('No matches. Try a region, city, or exact timezone.')
            continue
        if len(matches) > 30:
            print('{} matches; enter a more specific city or region.'.format(len(matches)))
            continue
        for index, name in enumerate(matches, 1):
            print('  {:2}. {}'.format(index, name))
        choice = input('Select a number (blank searches again): ').strip()
        if choice.isdigit() and 1 <= int(choice) <= len(matches):
            return matches[int(choice) - 1]


def show_status(zones):
    print('  Local time: ' + datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z (%z)'))
    print('  Saved zone: ' + saved_zone(zones))
    print('  Zone file:  ' + str(DESTINATION))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--status', action='store_true', help='Show status and exit without saving')
    args = parser.parse_args(argv)
    zones = available_zones()
    if not zones:
        print('No installed timezone database found in ' + str(ZONE_ROOT))
        return 1
    if args.status:
        show_status(zones)
        return 0
    if not Path('/media/fat/MiSTer').exists():
        print('Run this utility on your MiSTer.')
        return 1
    try:
        while True:
            print('\n+' + '-' * 64 + '+')
            print('|{:^64}|'.format('MiSTer Timezone Manager ' + VERSION))
            print('+' + '-' * 64 + '+')
            show_status(zones)
            print('\n  [1] Search or enter timezone (offline)')
            print('  [2] Detect timezone from public IP (online)')
            print('  [3] Refresh status\n  [Q] Exit')
            choice = input('\nSelect: ').strip().lower()
            if choice in ('q', 'quit'):
                return 0
            if choice == '3':
                continue
            if choice not in ('1', '2'):
                print('Choose a listed option.')
                continue
            try:
                if choice == '1':
                    name = choose_zone(zones)
                else:
                    print('Automatic detection contacts ipwho.is using your public IP. VPNs may affect the result.')
                    if input('Look up timezone? [y/N]: ').strip().lower() not in ('y', 'yes'):
                        continue
                    name = detect_zone()
                if not name:
                    continue
                if name not in zones:
                    raise ValueError('Detected timezone is not installed: ' + name)
                print('Selected: ' + name)
                if input('Save this timezone? [y/N]: ').strip().lower() not in ('y', 'yes'):
                    continue
                if os.geteuid() != 0:
                    raise PermissionError('Run as root to save the timezone.')
                changed = write_zone(name, zones)
                print('Timezone saved.' if changed else 'Timezone is already set; no changes needed.')
                print('Existing applications may need restarting to show the new timezone.')
            except (OSError, ValueError, RuntimeError) as exc:
                print('Action failed: ' + str(exc))
            input('\nPress Enter to return to the menu...')
    except (EOFError, KeyboardInterrupt):
        print('\nCancelled.')
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
