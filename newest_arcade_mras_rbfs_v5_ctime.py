#!/usr/bin/env python3
"""Read-only report of the newest MiSTer arcade MRA and RBF files by filesystem ctime."""
import argparse
import os
from datetime import datetime, timedelta

MRA_ROOT = os.environ.get('MRA_ROOT', '/media/fat/_Arcade')
RBF_ROOT = os.environ.get('RBF_ROOT', os.path.join(MRA_ROOT, 'cores'))
LOG_DIR = os.environ.get('LOG_DIR', '/media/fat/Scripts/logs')


def inventory(root, extension):
    found = []
    for folder, _dirs, files in os.walk(root):
        for filename in files:
            if not filename.lower().endswith(extension):
                continue
            path = os.path.join(folder, filename)
            try:
                modified = os.path.getctime(path)
            except OSError as exc:
                print('WARNING: Skipping {}: {}'.format(path, exc))
                continue
            found.append((modified, os.path.relpath(path, root)))
    return sorted(found, key=lambda item: (-item[0], item[1].casefold()))


def section(title, entries, root, cutoff):
    eligible = [entry for entry in entries if cutoff is None or entry[0] >= cutoff]
    lines = [title, '=' * len(title), 'Folder: ' + root,
             'Total files: {}'.format(len(entries)),
             'Matching date filter: {}'.format(len(eligible)),
             'Showing: {}'.format(len(eligible)), '']
    for timestamp, rel in eligible:
        lines.append('{}  {}'.format(datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S'), rel))
    if not eligible:
        lines.append('(none)')
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='List newest arcade MRAs and RBFs (read-only).')
    parser.add_argument('-days', '--days', type=float, default=7, metavar='N', help='Only show files with ctime within the last N days (default: 7).')
    args = parser.parse_args()
    if args.days < 0:
        parser.error('--days must be nonnegative')
    for root in (MRA_ROOT, RBF_ROOT):
        if not os.path.isdir(root):
            parser.error('Folder not found: ' + root)
    cutoff = (datetime.now() - timedelta(days=args.days)).timestamp() if args.days is not None else None
    mras = inventory(MRA_ROOT, '.mra')
    rbfs = inventory(RBF_ROOT, '.rbf')
    header = ['ARCADE FILE TIMESTAMP REPORT', 'Generated: ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
              'Times shown in local timezone.',
              'Timestamps: filesystem ctime (not a guaranteed upload time).', 'Sort: newest filesystem ctime first.',
              'Date filter: last {} day(s)'.format(args.days) if args.days is not None else 'Date filter: none', '']
    report = '\n'.join(header + [section('NEWEST MRA FILES', mras, MRA_ROOT, cutoff), '',
                                 section('NEWEST RBF FILES', rbfs, RBF_ROOT, cutoff), ''])
    print(report)
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        destination = os.path.join(LOG_DIR, 'arcade_newest_files.log')
        with open(destination, 'w', encoding='utf-8') as output:
            output.write(report + '\n')
        print('Report saved to: ' + destination)
    except OSError as exc:
        print('WARNING: Could not save report: {}'.format(exc))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
