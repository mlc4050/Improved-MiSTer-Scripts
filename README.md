# Improved MiSTer Scripts

Ten standalone utilities to keep your MiSTer connected, organized, and ready to play. Manage networking and controllers, clean up arcade files, find cheats, and see what's new in your collection.

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

The cheat checker writes `cheat_rom_comparison_report.log` under `/media/fat/Scripts/logs`. It also accepts
`--log-dir` and the `CHEATS_ROOT`, `GAMES_ROOT`, and `LOG_DIR` environment variables.
Each run replaces its previous text report. Console colors follow the other report
utilities and are omitted from saved logs.

Games and cheats must be in system subdirectories. The checker scans both trees
recursively and compares within each system, with aliases for common folder names.
By default it presents a numbered console menu built from the immediate folders
present in both roots, recognizing aliases and excluding other unsupported CD/arcade
systems. Select a console, comma-separated numbers, A for all listed consoles,
or Q to quit. Only selected console directories are traversed. Use `--system SNES`
(repeatable) or `--all` to skip the menu. Explicit `--system` can also check a
console that has games but no cheat folder. Quitting leaves existing reports intact.
The report highlights games
without matching cheats first and omits cheats that have no game. A game without
cheats is a normal report entry, not a scan error. The text report includes games without cheats. Use `--system` to limit the scan.
`CRC_MATCH` confirms the raw ROM CRC agrees with the
cheat filename's `[12345678]` tag. Exact filename comparisons ignore these CRC tags.
A name match with a different
CRC is flagged because the cheat may target another ROM revision. Region and
revision tags are preserved when suggesting title matches.

Matches are chosen per game in this order: raw CRC, headerless NES/SNES CRC, then exact filename stem
(case-insensitive, excluding the file extension and bracketed CRC tags). Similar titles do not count as
matches. Either a CRC
match or an exact name match is sufficient. An exact name match with a different
CRC is noted because compatibility is unverified. Games with neither match appear
under games without matching cheats.

The default console and text output lists only unmatched games, with up to
three similar title suggestions per game (85% minimum similarity, within the same
console). Suggestions ignore CRC tags and punctuation, but remain **unmatched**:
they have neither the required CRC nor exact name match. The text report includes
a per-console tally of checked, matched, unmatched, and unmatched games with
suggestions. Each game is counted once even when several cheat files match it.
Use `--deep` to include every confirmed match in the text output as well as
verify ZIP contents. Cheats without games are not listed.
Text details are grouped by the actual console folder, then by recursive game
subfolder. ZIP members appear under their archive's virtual subfolders.

ZIP comparisons use the ROM members, not the archive's checksum. Normally ZIP
member CRCs come from archive metadata; `--deep` reads all supported ROM members
and tests cheat archives for corruption. NES and SNES members are always read to
also report possible headerless CRC matches. NES/SNES headerless CRC matches count as confirmed CRC matches, following
MiSTer loader behavior. N64 ROMs are normalized to byte-swapped order for cheat CRC lookup; SMD
interleaving is not converted. MegaCD/SegaCD, TGFX16-CD/PCE-CD, and PSX/PlayStation support name-only
matching for `.cue`, `.chd`, `.iso`, `.m3u`, `.ccd`, `.pbp`, and `.img` games. Image CRCs and game IDs are
not checked, even with `--deep`. Playlist-referenced images are not counted twice;
BIN/audio tracks are ignored. Other CD/game-ID systems (such as Saturn) and
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

Reports include `config_cleanup_report.log`, `arcade_cleanup_report.log`. Cleanup deletion logs describe the current run; previous deletion logs can be removed at the start of a later run.

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

Wi-Fi diagnostics v27 and newest arcade files v6 display results on screen only;
they do not create diagnostic/report log files. Existing old logs are untouched.

Cheat checker v7 excludes bracketed eight-digit CRC tags from exact title matching.
Region, revision, and hack tags remain significant; name-only matches do not verify compatibility.

Cheat checker v8 adds MegaCD and TGFX16-CD name matching and excludes SNES
MSU-1/MSU1 folders, tagged filenames, and `.msu`/`.pcm` assets from scans.

Cheat checker v9 also includes PSX name matching, Jaguar `.j64`/`.jag`/`.abs`/`.cof`
files, and AtariLynx/Lynx aliases. All 15 cheat folders shown in the collection can
appear in the console menu when their corresponding game folders exist:
AtariLynx, GAMEBOY, GBA, Jaguar, MegaCD, MegaDrive, N64, NES, PSX, SGB, SMS,
SNES, TGFX16, TGFX16-CD, and VirtualBoy. SGB stays separate from GAMEBOY.

Cheat checker v10 ignores CD media labels `(CD)`, `(SCD)`, and `(CD, SCD)`
when comparing CD game names. It normalizes tag spacing and region abbreviations
such as `(Jpn)`/`(Japan)` and `(Euro)`/`(Europe)`. Different regions, revisions,
and hack tags remain distinct. These are name matches, not CRC verification.
Specific TGFX16-CD aliases also recognize Rondo's `(Japan) (FABT, FACT)` naming
and `Fantastic Night Dreams - Cotton (USA)` versus
`Cotton - Fantastic Night Dreams (USA)`. These do not establish compatibility
for other tagged variants.

Cheat checker v11 ignores parenthesized CD collection labels containing only
`FACT`, `FADT`, or `FABT`, in any comma-separated order, across all CD titles.
This covers Gate of Thunder and Rondo without individual title exceptions.
Unknown labels, regions, revisions, and hack tags are preserved. Similar-title
suggestions use the same normalization as name matching.
