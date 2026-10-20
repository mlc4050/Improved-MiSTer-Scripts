#!/usr/bin/env python3
"""MiSTer SSH Terminal Customizations v3.

Restore SSH terminal colors, aliases, and startup folder on MiSTer.

Standalone: no archive or other scripts required.
"""
import os
import tempfile
from pathlib import Path

# Original SSH prompt colors and default GNU ls colors.
PROFILE = ("cd /media/fat/Scripts\n"
           "PS1='\\[\\e[32m\\]\\u@\\h \\[\\e[35m\\]MiSTer \\[\\e[33m\\]\\w\\[\\e[0m\\]\\n\\$ '\n"
           "\n"
           "unset LS_COLORS\n"
           "alias ls='ls --color=auto'\n"
           "alias ll='ls -alF --color=auto'\n")
DESTINATION = Path('/root/.profile')


def main():
    print('MiSTer SSH Terminal Customizations v3')
    if os.geteuid() != 0:
        print('Run this as root on your MiSTer.')
        return 1
    try:
        if DESTINATION.exists() and DESTINATION.read_bytes() == PROFILE.encode('utf-8'):
            print('Your MiSTer SSH terminal settings are already installed. No changes made.')
            return 0
        answer = input('Restore your MiSTer SSH terminal customizations? This replaces /root/.profile. [y/N]: ').strip().lower()
        if answer != 'y':
            print('Cancelled. No changes made.')
            return 0
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=str(DESTINATION.parent), prefix='.profile.', delete=False) as temp:
                temp_path = temp.name
                temp.write(PROFILE)
                temp.flush()
                os.fsync(temp.fileno())
            os.chmod(temp_path, 0o644)
            os.replace(temp_path, DESTINATION)
            temp_path = None
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)
    except (OSError, EOFError, KeyboardInterrupt) as exc:
        print('\nUnable to restore profile: {}'.format(exc))
        return 1
    print('SSH terminal settings installed. Reconnect via SSH to see the changes.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
