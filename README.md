# Improved MiSTer Scripts

A collection of ten standalone Python utilities for managing and maintaining a MiSTer FPGA installation, created by [mlc4050](https://github.com/mlc4050).

## Scripts

| Script | Purpose |
| --- | --- |
| [`wifi_setup_diagnostics_v26.py`](wifi_setup_diagnostics_v26.py) | Scan Wi-Fi networks, manage saved networks and priorities, change country/password settings, and report connection quality and gateway latency. |
| [`bluetooth_manager_v16.py`](bluetooth_manager_v16.py) | Pair devices through MiSTer's `btctl`, manage paired devices, and inspect adapter and connection diagnostics. |
| [`fast_usb_polling_manager_v10.py`](fast_usb_polling_manager_v10.py) | Inspect and enable/disable fast USB polling options in `linux/u-boot.txt`. Reboot to apply changes. |
| [`ftp_ssh_manager_v2.py`](ftp_ssh_manager_v2.py) | Start/stop FTP and SSH, control startup settings, and optionally update MiSTer firewall rules. |
| [`mac_address_manager_v1.py`](mac_address_manager_v1.py) | Generate and save a locally administered Ethernet MAC address in `linux/u-boot.txt`. Reboot to apply it. |
| [`restore_ssh_customizations_v3.py`](restore_ssh_customizations_v3.py) | Restore a colored SSH prompt, `ls`/`ll` aliases, and `/media/fat/Scripts` as the startup directory. Replaces `/root/.profile` after confirmation. |
| [`cleanup_orphan_mister_configs_v17.py`](cleanup_orphan_mister_configs_v17.py) | Identify orphan configuration files, input maps, DIP settings, and NVRAM using installed arcade MRAs, ROM ZIPs, and core files. Offers separate deletion confirmations. |
| [`find_orphan_mame_zips_and_rbfs_v52.py`](find_orphan_mame_zips_and_rbfs_v52.py) | Report orphan MAME ZIPs, arcade RBFs, and missing references, with optional deeper ROM CRC checks and interactive cleanup. |
| [`check_mister_cheats_v3.py`](check_mister_cheats_v3.py) | Compare cheat ZIP names and CRC tags with cartridge ROMs, including ROMs inside ZIPs. Saves text and CSV reports without changing games or cheats. |
| [`newest_arcade_mras_rbfs_v5_ctime.py`](newest_arcade_mras_rbfs_v5_ctime.py) | List recently changed MRA and RBF files, sorted by filesystem `ctime`, and save a report. Does not modify the scanned files. |

## Requirements

- A MiSTer Linux installation with Python 3 available. The scripts use only Python's standard library; no pip packages are required.
- Run from a MiSTer terminal or SSH session. These utilities target MiSTer Linux paths and system tools, rather than Windows.
- Use root for system configuration and service changes.
- Bluetooth and Wi-Fi features depend on the corresponding hardware and MiSTer utilities, including `btctl`/`bluetoothctl` and wireless networking tools.

## Installation and usage

Download this repository using GitHub's **Code → Download ZIP**, extract it, and copy the `.py` files to `/media/fat/Scripts/` on your MiSTer.

Open a terminal on MiSTer or connect over SSH, then run a script explicitly with Python:

```sh
cd /media/fat/Scripts
python3 wifi_setup_diagnostics_v26.py
```

Most utilities present an interactive menu or confirmation prompts. Other examples:

```sh
python3 bluetooth_manager_v16.py
python3 fast_usb_polling_manager_v10.py
python3 ftp_ssh_manager_v2.py
python3 mac_address_manager_v1.py
python3 restore_ssh_customizations_v3.py
python3 cleanup_orphan_mister_configs_v17.py
python3 find_orphan_mame_zips_and_rbfs_v52.py

# Check every ROM part against its MRA CRC, including single-ZIP MRAs:
python3 find_orphan_mame_zips_and_rbfs_v52.py --deep

# Report MRA/RBF filesystem changes within the last 14 days (default: 7):
python3 newest_arcade_mras_rbfs_v5_ctime.py --days 14

# Compare /media/fat/Cheats with /media/fat/games:
python3 check_mister_cheats_v3.py

# Skip the console menu and scan all common consoles:
python3 check_mister_cheats_v3.py --all

# Limit the scan to SNES and read ZIP contents to verify CRCs:
python3 check_mister_cheats_v3.py --system SNES --deep

# Override paths or map differently named system folders:
python3 check_mister_cheats_v3.py --cheats-root /media/fat/Cheats --games-root /media/usb0/games --map Genesis=MegaDrive
```

The cheat checker writes `cheat_rom_comparison_report.log` and
`cheat_rom_comparison_report.csv` under `/media/fat/Scripts/logs`. It also accepts
`--log-dir` and the `CHEATS_ROOT`, `GAMES_ROOT`, and `LOG_DIR` environment variables.
Each run replaces its previous reports. Console colors follow the other report
utilities and are omitted from saved logs.

Games and cheats must be in system subdirectories. The checker scans both trees
recursively and compares within each system, with aliases for common folder names.
By default it presents a numbered console menu built from the immediate folders
present in both roots, recognizing aliases and excluding unsupported CD/arcade
systems. Select a console, comma-separated numbers, A for all listed consoles,
or Q to quit. Only selected console directories are traversed. Use `--system SNES`
(repeatable) or `--all` to skip the menu. Explicit `--system` can also check a
console that has games but no cheat folder. Quitting leaves existing reports intact.
The report highlights games
without matching cheats first and omits cheats that have no game. A game without
cheats is a normal report entry, not a scan error. Both text and CSV reports
include games without cheats. Use `--system` to limit the scan.
`CRC_MATCH` confirms the raw ROM CRC agrees with the
cheat filename's `[12345678]` tag. Exact filename stems are reported separately
from titles that agree only after stripping CRC tags. A name match with a different
CRC is flagged because the cheat may target another ROM revision. Region and
revision tags are preserved when suggesting title matches.

Matches are chosen per game in this order: raw CRC, headerless NES/SNES CRC, then exact filename stem
(case-insensitive, excluding the file extension). Similar titles do not count as
matches, including titles that agree only after removing a CRC tag. Either a CRC
match or an exact name match is sufficient. An exact name match with a different
CRC is noted because compatibility is unverified. Games with neither match appear
under games without matching cheats.

The default console, text, and CSV output lists only unmatched games, with up to
three similar title suggestions per game (85% minimum similarity, within the same
console). Suggestions ignore CRC tags and punctuation, but remain **unmatched**:
they have neither the required CRC nor exact name match. The text report includes
a per-console tally of checked, matched, unmatched, and unmatched games with
suggestions. Each game is counted once even when several cheat files match it.
Use `--deep` to include every confirmed match in the text/CSV output as well as
verify ZIP contents. Cheats without games are not listed.
Text details are grouped by the actual console folder, then by recursive game
subfolder. ZIP members appear under their archive's virtual subfolders. CSV rows
follow the same console/folder ordering, including when `--deep` is used.

ZIP comparisons use the ROM members, not the archive's checksum. Normally ZIP
member CRCs come from archive metadata; `--deep` reads all supported ROM members
and tests cheat archives for corruption. NES and SNES members are always read to
also report possible headerless CRC matches. NES/SNES headerless CRC matches count as confirmed CRC matches, following
MiSTer loader behavior. N64 byte
order and SMD interleaving are not converted. CD/game-ID systems (such as PSX) and
arcade ROM sets are explicitly left unverified. Recursive matches describe files
present on disk; MiSTer's actual lookup of nested cheat folders may vary by version.
Missing matches and scan errors never trigger
deletion or renaming; this script has no cleanup action. See
[MiSTer's cheat documentation](https://mister-devel.github.io/MkDocs_MiSTer/cores/features/cheats/)
for name/CRC lookup behavior.

## Paths and reports

Default locations include:

| Data | Location |
| --- | --- |
| Arcade MRAs | `/media/fat/_Arcade` |
| Arcade RBFs | `/media/fat/_Arcade/cores` |
| MAME ROM ZIPs | `/media/fat/games/mame` |
| MiSTer configuration | `/media/fat/config` |
| Reports and deletion logs | `/media/fat/Scripts/logs` |
| Boot settings | `/media/fat/linux/u-boot.txt` |
| Wi-Fi configuration | `/media/fat/linux/wpa_supplicant.conf` |

Scripts expose selected environment-variable overrides, such as `MRA_ROOT`, `RBF_ROOT`, `MAME_ROOT`, `CONFIG_ROOT`, `MEDIA_ROOT`, `LOG_DIR`, `WPA_CONF`, and `MISTER_UBOOT_PATH`. Check each script's constants for the overrides it supports.

Reports include `wifi_diagnostics.log`, `config_cleanup_report.log`, `arcade_cleanup_report.log`, and `arcade_newest_files.log`. Cleanup deletion logs describe the current run; previous deletion logs can be removed at the start of a later run.

## Before making changes

- Back up configuration, boot settings, and saved data before changing or deleting files. Cleanup confirmations perform actual deletion; NVRAM may contain saved game data.
- Review cleanup reports before confirming deletion. Results depend on the files and references present in your installation.
- Wi-Fi password entry is visible in the terminal. Saved Wi-Fi configuration changes generally apply after restarting MiSTer; the manager also provides a saved-network switching action.
- Changing networking or stopping SSH can interrupt a remote session. Keep local terminal access available when using those functions.
- USB polling and Ethernet MAC changes require a reboot. SSH prompt changes appear after reconnecting.
- On Linux, `ctime` is the last inode status-change time, not a guaranteed creation, download, or upload time.

## Attribution and licensing

Several script headers acknowledge concepts or helpers from [MiSTer-devel/Scripts_MiSTer](https://github.com/MiSTer-devel/Scripts_MiSTer). The USB polling and MAC address scripts identify their upstream basis as GPL-3.0-or-later. Those notices are preserved in the source. No additional blanket license is assigned to the collection here.

This is an independent collection and is not an official MiSTer-devel release. No ROMs or FPGA core binaries are included.

Cheat checker v2 recognizes Virtual Boy `.vb`/`.vboy` and Lynx `.lyx` ROMs,
and explicitly warns when a selected console has zero supported ROMs checked.

Cheat checker v3 counts NES/SNES headerless CRC matches and excludes different
numbered sequels from similar-name suggestions. Raw and headerless CRCs remain
available in deep details and CSV columns.
