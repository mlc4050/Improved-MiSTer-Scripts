# Improved MiSTer Scripts

Twelve standalone utilities to keep your MiSTer connected, organized, and ready to play. Manage networking and controllers, clean up arcade files, find cheats, and see what's new in your collection.

Created by [mlc4050](https://github.com/mlc4050). Written in Python 3 with no additional Python packages required.

## Scripts

Run the examples from `/media/fat/Scripts` on your MiSTer. Most tools open an interactive menu; cleanup tools ask before deleting files.

| Name | Description | File | Example usage |
| --- | --- | --- | --- |
| **Wi-Fi Setup & Diagnostics** | Manage saved networks and priorities, scan nearby Wi-Fi, and check signal quality and gateway latency. | [wifi_setup_diagnostics_v27.py](wifi_setup_diagnostics_v27.py) | `python3 wifi_setup_diagnostics_v27.py` |
| **Bluetooth Manager** | Pair controllers and other devices, manage connections, and diagnose Bluetooth adapters. | [bluetooth_manager_v16.py](bluetooth_manager_v16.py) | `python3 bluetooth_manager_v16.py` |
| **Fast USB Polling Manager** | View and change USB polling settings. Reboot to apply changes. | [fast_usb_polling_manager_v10.py](fast_usb_polling_manager_v10.py) | `python3 fast_usb_polling_manager_v10.py` |
| **FTP & SSH Manager** | Start or stop remote-access services, choose whether they start at boot, and manage related firewall rules. | [ftp_ssh_manager_v2.py](ftp_ssh_manager_v2.py) | `python3 ftp_ssh_manager_v2.py` |
| **Ethernet MAC Address Manager** | Generate and save a locally administered Ethernet MAC address. Reboot to apply it. | [mac_address_manager_v1.py](mac_address_manager_v1.py) | `python3 mac_address_manager_v1.py` |
| **SSH Terminal Customizer** | Restore a colored prompt, handy file-listing aliases, and the Scripts startup folder. Replaces `/root/.profile` after confirmation. | [restore_ssh_customizations_v3.py](restore_ssh_customizations_v3.py) | `python3 restore_ssh_customizations_v3.py` |
| **Orphan Configuration Cleaner** | Find unused arcade settings, input maps, DIP files, and NVRAM, with separate deletion prompts for each category. | [cleanup_orphan_mister_configs_v17.py](cleanup_orphan_mister_configs_v17.py) | `python3 cleanup_orphan_mister_configs_v17.py` |
| **Arcade ROM & Core Checker** | Find orphan MAME ZIPs and arcade cores, report missing references, and optionally check required ROM CRCs. | [find_orphan_mame_zips_and_rbfs_v52.py](find_orphan_mame_zips_and_rbfs_v52.py) | `python3 find_orphan_mame_zips_and_rbfs_v52.py` |
| **Cheat Collection Checker** | Compare games with your cheat collection using cartridge CRCs and game names; report games without matches. CD comparisons use names only. | [check_mister_cheats_v11.py](check_mister_cheats_v11.py) | `python3 check_mister_cheats_v11.py --all` |
| **Recent Arcade Files** | List MRA and RBF files by filesystem change time, filtered to a recent date range. | [newest_arcade_mras_rbfs_v6_ctime.py](newest_arcade_mras_rbfs_v6_ctime.py) | `python3 newest_arcade_mras_rbfs_v6_ctime.py --days 14` |
| **RTC & Time Manager** | Synchronize system time over NTP, inspect hardware RTC status, and save system time to the RTC when available. | [rtc_manager_v1.py](rtc_manager_v1.py) | `python3 rtc_manager_v1.py` |
| **Timezone Manager** | Search installed timezones offline or preview an automatic suggestion, then save the selected zone. | [timezone_manager_v1.py](timezone_manager_v1.py) | `python3 timezone_manager_v1.py` |

The **RTC & Time Manager** and **Timezone Manager** are Python replacements for
MiSTer's stock `rtc.sh` and `timezone.sh`. NTP system-time sync works without a
hardware RTC. Timezone selection searches MiSTer's installed database, including
its `posix` region directories. Both managers support a read-only status check:

```sh
python3 rtc_manager_v1.py --status
python3 timezone_manager_v1.py --status
```

Interactive NTP synchronization and offline timezone selection have been tested
on MiSTer. Hardware RTC writes require a detected RTC; online timezone detection
is optional. See [Time Utilities documentation](TIME_MANAGERS.md) for all options.

**Getting started?** Follow [installation and usage](#installation-and-usage) below. The [paths and reports](#paths-and-reports) section shows where each tool looks for files.

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
python3 wifi_setup_diagnostics_v27.py
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
python3 newest_arcade_mras_rbfs_v6_ctime.py --days 14

# Compare /media/fat/Cheats with /media/fat/games:
python3 check_mister_cheats_v11.py

# Skip the console menu and scan all common consoles:
python3 check_mister_cheats_v11.py --all

# Limit the scan to SNES and read ZIP contents to verify CRCs:
python3 check_mister_cheats_v11.py --system SNES --deep

# Override paths or map differently named system folders:
python3 check_mister_cheats_v11.py --cheats-root /media/fat/Cheats --games-root /media/usb0/games --map Genesis=MegaDrive
```

## Cheat Collection Checker

Compare the games you own with the cheats in `/media/fat/Cheats`. The checker
writes `/media/fat/Scripts/logs/cheat_rom_comparison_report.log`, replacing the
previous report each run. It does not rename, delete, or modify games or cheats.

### Selecting consoles

Run `python3 check_mister_cheats_v11.py` for a numbered console menu. Select one
or more numbers, **A** for all listed consoles, or **Q** to quit without changing
the report. Use `--all` or repeatable `--system` options to skip the menu.

The menu lists consoles with folders in both the games and cheats trees, using
aliases for common names. Supported collection folders include AtariLynx,
GAMEBOY, GBA, Jaguar, MegaCD, MegaDrive, N64, NES, PSX, SGB, SMS, SNES,
TGFX16, TGFX16-CD, and VirtualBoy. SGB remains separate from GAMEBOY.
Explicit `--system` can check a games folder even when its cheat folder is missing.
Only selected console folders are searched recursively.

### Matching and results

Cartridge matches use raw CRC first, then NES/SNES headerless or N64 byte-swapped
CRC where applicable, then the filename without its extension. Name comparisons
ignore case and bracketed eight-digit CRC tags. A name match counts toward cheat
coverage, but does not establish that the codes work with that ROM revision.
Region, revision, and hack tags remain significant.

The report groups unmatched games by console and subfolder, with a per-console
summary. Similar-title suggestions require at least 85% similarity and remain
unmatched. Cheats without games are omitted. A game without cheats is a normal
result; scan errors and empty-console warnings are reported separately.

Use `--deep` to show matched-game details, read supported cartridge ROMs inside
ZIPs, and test cheat ZIPs for corruption. Normal ZIP checks use member CRCs from
archive metadata; NES, SNES, and N64 members are always read for their additional
CRC handling. ZIP archive checksums are not used as game CRCs. SMD interleaving
is not converted. Jaguar `.j64`, `.jag`, `.abs`, and `.cof`, Virtual Boy `.vb`/`.vboy`,
and Lynx `.lnx`/`.lyx` files are recognized.

### CD games

MegaCD/SegaCD, TGFX16-CD/PCE-CD, and PSX/PlayStation use **name-only matching**
for `.cue`, `.chd`, `.iso`, `.m3u`, `.ccd`, `.pbp`, and `.img` files. Disc CRCs
and game IDs are not verified, including with `--deep`. Playlist-referenced
images are not counted twice, and BIN/audio tracks are ignored. CD game ZIPs
are not scanned. Other CD systems and arcade ROM sets are outside this checker.

CD title comparisons ignore `(CD)`, `(SCD)`, and `(CD, SCD)` labels, normalize
region abbreviations such as `(Jpn)`/`(Japan)` and `(Euro)`/`(Europe)`, and ignore
collection tags containing only `FACT`, `FADT`, or `FABT`. Cotton's two known
title orders are also recognized. Unknown tags, different regions, revisions,
and hacks remain distinct.

**A collection match does not confirm installation in the location the core uses.**
For TGFX16-CD, put the cheat ZIP beside the game's disc image in its game folder,
as described in the [TGFX16 core documentation](https://github.com/MiSTer-devel/TurboGrafx16_MiSTer#cheat-engine).

### Exclusions and custom paths

SNES MSU-1/MSU1 folders and tagged filenames, `.msu`/`.pcm` assets, and `.pal`/`.gbp`
palette files are silently ignored. Other unsupported files appear in the skipped
list. Scan errors can leave coverage incomplete.

Use `--cheats-root`, `--games-root`, and `--log-dir` to change locations, or set
`CHEATS_ROOT`, `GAMES_ROOT`, and `LOG_DIR`. Use `--map Genesis=MegaDrive` to map
differently named system folders. Examples are in [installation and usage](#installation-and-usage).

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

Reports include `config_cleanup_report.log`, `arcade_cleanup_report.log`, and
`cheat_rom_comparison_report.log`. Wi-Fi diagnostics and Recent Arcade Files
show their results on screen without creating report logs. Cleanup deletion logs describe the current run; previous deletion logs can be removed at the start of a later run.

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
