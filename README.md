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
| **Arcade ROM & Core Checker** | Find orphan MAME ZIPs and arcade cores, report missing references, and optionally check required ROM CRCs. | [find_orphan_mame_zips_and_rbfs_v53.py](find_orphan_mame_zips_and_rbfs_v53.py) | `python3 find_orphan_mame_zips_and_rbfs_v53.py` |
| **Cheat Collection Checker** | Compare games with installed cheats using cartridge CRCs, titles, PSX disc IDs, and each console's cheat-location rules. | [check_mister_cheats_v20.py](check_mister_cheats_v20.py) | `python3 check_mister_cheats_v20.py --all` |
| **Recent Arcade Files** | List MRA and RBF files by filesystem change time, filtered to a recent date range. | [newest_arcade_mras_rbfs_v6_ctime.py](newest_arcade_mras_rbfs_v6_ctime.py) | `python3 newest_arcade_mras_rbfs_v6_ctime.py --days 14` |
| **RTC & Time Manager** | Synchronize system time over NTP, inspect hardware RTC status, and save system time to the RTC when available. | [rtc_manager_v1.py](rtc_manager_v1.py) | `python3 rtc_manager_v1.py` |
| **Timezone Manager** | Search installed timezones offline or preview an automatic suggestion, then save the selected zone. | [timezone_manager_v1.py](timezone_manager_v1.py) | `python3 timezone_manager_v1.py` |

The **RTC & Time Manager** and **Timezone Manager** are Python replacements for
MiSTer's stock `rtc.sh` and `timezone.sh`:

- **RTC & Time Manager:** shows system time and any detected hardware clock.
  It can set the correct time from an Internet time server (NTP), then optionally
  save it to the hardware RTC. Internet time sync works without an RTC module;
  writing the hardware clock requires one. The default server is `0.pool.ntp.org`.
- **Timezone Manager:** searches MiSTer's installed timezones by city or region,
  such as `America/Chicago`. Manual selection works offline. Optional automatic
  detection uses your public IP address and asks before applying its suggestion.
  The selected zone is saved to `/media/fat/linux/timezone` and changes how local
  time is displayed.

Run either script to open its menu. Changes require confirmation and root access.
Both show results on screen without creating report logs. They do not install a
background time-sync service. Add `--status` to inspect the current setup without
changing anything:

```sh
python3 rtc_manager_v1.py --status
python3 timezone_manager_v1.py --status
```

Interactive NTP synchronization and offline timezone selection have been tested
on MiSTer.

**Getting started?** Follow [installation and usage](#installation-and-usage) below. The [paths and reports](#paths-and-reports) section shows where each tool looks for files.

## Requirements

- A MiSTer Linux installation with Python 3 available. The scripts use only Python's standard library; no pip packages are required.
- Run from a MiSTer terminal or SSH session. These utilities target MiSTer Linux paths and system tools, rather than Windows.
- Use root for system configuration and service changes.
- Bluetooth and Wi-Fi features depend on the corresponding hardware and MiSTer utilities, including `btctl`/`bluetoothctl` and wireless networking tools.

## Installation and usage

Download this repository using GitHub's **Code > Download ZIP**, extract it, and copy the `.py` files to `/media/fat/Scripts/` on your MiSTer.

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
python3 find_orphan_mame_zips_and_rbfs_v53.py

# Check every ROM part against its MRA CRC, including single-ZIP MRAs:
python3 find_orphan_mame_zips_and_rbfs_v53.py --deep

# Report MRA/RBF filesystem changes within the last 14 days (default: 7):
python3 newest_arcade_mras_rbfs_v6_ctime.py --days 14

# Compare /media/fat/Cheats with /media/fat/games:
python3 check_mister_cheats_v20.py

# Skip the console menu and scan all common consoles:
python3 check_mister_cheats_v20.py --all

# Limit the scan to SNES and read ZIP contents to verify CRCs:
python3 check_mister_cheats_v20.py --system SNES --deep

# Override paths or map differently named system folders:
python3 check_mister_cheats_v20.py --cheats-root /media/fat/Cheats --games-root /media/usb0/games --map Genesis=MegaDrive
```

## Cheat Collection Checker

Compare the games you own with the cheats in `/media/fat/Cheats`. The checker
writes `/media/fat/Scripts/logs/cheat_rom_comparison_report.log`, replacing the
previous report each run. It does not rename, delete, or modify games or cheats.

### Selecting consoles

Run `python3 check_mister_cheats_v20.py` for a numbered console menu. Select one
or more numbers, **A** for all listed consoles, or **Q** to quit without changing
the report. Use `--all` or repeatable `--system` options to skip the menu.

The menu lists consoles with folders in both the games and cheats trees, using
aliases for common names. Supported collection folders include AtariLynx,
GAMEBOY, GameGear, GBA, Jaguar, MegaCD, MegaDrive, N64, NES, PSX, SGB, SMS, SNES,
TGFX16, TGFX16-CD, and VirtualBoy. SGB remains separate from GAMEBOY.
Explicit `--system` can check a games folder even when its cheat folder is missing.
Only selected console folders are searched recursively.

### Checking after an update

Run the checker on MiSTer against your installed games and cheats. For example,
check NES, SNES, and Genesis/Mega Drive together:

```sh
python3 check_mister_cheats_v20.py --system NES --system SNES --system MegaDrive
```

Use `--all` to check every listed console. Review the per-console counts,
nonmatching games, close-name candidates, notices, and scan errors in
`/media/fat/Scripts/logs/cheat_rom_comparison_report.log`. Compare those results
with your previous report, allowing for games or cheats you added, removed, or
renamed. Save the previous report elsewhere before running if you want to keep it.

These checks use your real collection and do not change ROMs or cheats. No
separate test runner or test-file configuration is required. Finding a cheat
file does not confirm that its codes work during gameplay.

### Matching and results

Depending on the console, results use these categories:

- **MATCHED:** raw, supported headerless, or N64 byte-swapped CRC matches a cheat target.
- **MATCHED_BY_NAME:** titles match after removing bracketed eight-digit CRC tags,
  even if the ROM and cheat-target checksums differ.
- **MATCHED_BY_GAME_ID:** PSX disc's internal ID matches an installed ID-named ZIP.
- **MATCHED_BY_PSX_FILENAME:** PSX finds an exact disc-basename ZIP locally or centrally.
- **MATCHED_BY_LOCAL_CHEAT:** MegaCD has a valid local ZIP matching the disc name,
  or TGFX16-CD has a valid local cheat ZIP whose name may differ.
- **LOCAL_CHEAT_NAME_MISMATCH:** MegaCD has a local ZIP with a different name;
  this is not a pass.
- **CENTRAL_CHEAT_ONLY:** a corresponding central cheat exists for MegaCD or
  TGFX16-CD, but no suitable local ZIP was found; this is not a pass.
- **PSX_UNVERIFIED:** the disc ID could not be read and no exact filename ZIP was
  found. Coverage is unknown; this is not a confirmed nonmatch.
- **CANDIDATE:** neither CRC nor the CRC-tag-ignored title matches, but a close relevant title
  exists. A filename-matched cheat copy can enable lookup; proposals are not applied.
- **NON_MATCHING:** no CRC match and no close relevant title; skip.
- **EXCLUDED_FROM_PROPOSALS:** translations, Top 100 paths, and explicitly patched
  or hacked builds (including PAL-to-NTSC conversions) receive no filename
  proposals. Exact CRC/title matches still count normally. Translation folder
  names (including `Translations`) are recognized. Translation and hack exclusions
  also cover identical-CRC copies in other folders on the same console.

Game-title comparisons ignore only the extension, case, and bracketed eight-digit
CRC metadata. Region, revision, language, and other release tags stay significant.
For suggestions only, spacing/punctuation, release tags, articles, and known NTSC
patch labels are normalized. Reviewed SNES title aliases include Gun Hazard's
"Series" label, Puzzle Bobble/Bust-A-Move, and Super E.D.F./Earth Defense Force.
Close-spelling suggestions require at least 94% similarity with matching sequel,
year, and Roman-numeral identifiers. Named hack suffixes are preserved; the
checker does not infer compatibility merely from a hack's original base game.
For candidate suggestions, conflicting regions (for example Japan versus USA)
are rejected even when the game title is otherwise identical. Region abbreviations
are recognized, and a multi-region target must overlap the ROM's named regions.
Other release tags remain significant for candidates too: `(BS)` is not `(En)`,
and a different revision or beta label is not treated as a filename-only problem.
Game Boy suggestions recognize `Kaisen Game - Radarmission` / `Radar Mission`.
An installed multi-region cheat name can produce a candidate for an overlapping
ROM region even when the target CRC identifies a different regional build;
this remains an unverified proposal, not evidence that the codes work.

Candidates can include alternative **copy-cheat-ZIP proposals** using the ROM's
exact filename. These are never performed automatically, never rename ROMs, and
never overwrite an existing target name. Multiple source alternatives are choices
to review and test, not instructions to copy all of them onto the same target.
A title match needs no filename proposal in this checker. This report compares
the collection; individual codes are not tested in gameplay.

The report groups results by category, console, and subfolder with per-console
counts. `--json-report PATH` optionally writes inputs and classifications for
independent auditing. A nonmatching game is a normal result; scan errors and
empty-console warnings are reported separately.

SNES startup/BS-X firmware, known calibration/test ROMs, and Game Genie utilities
appear under **EXCLUDED SUPPORT FILES (NOT GAMES)** instead of missing cheats.
NES root `boot.rom`/`boot0.rom` through `boot3.rom`, 240p Test Suite, Nintendo World
Class Service test cartridges, SoundTest 2, and Zap Ruder are also support files.
For Game Boy, root startup `boot*.rom` files (boot/boot0 through boot3) and `.sgb`
border artwork under `Borders/` are support files; actual game ROMs remain eligible.
GBA root `boot.rom` and `Game Boy Advance Video - ...` media cartridges are also
omitted from game coverage. Explicit `modification` labels count as hacked builds
for proposal exclusions; unlicensed/homebrew games stay eligible.
Mega Drive 240p Test Suite and Controller Test - POLYGAMe are diagnostic support
files. WAV audio and `paprium.cue` under `MegaDrive/PAPRIUM/` are support assets;
`Paprium.md` remains a game ROM.
Mega Drive Game Genie programs are utilities. Explicit Enhanced Colors, Pyron
Color, and EverDrive Fixed labels also mark modified builds for proposal exclusions.
N64 root `boot.rom`, `boot1.rom`, and `N64-database.txt` are startup/configuration
support files and are omitted from game coverage.
Atari Lynx root `boot0.rom` is also startup firmware, not a game ROM.
SGB root `Super Game Boy.sfc` and `Super Game Boy 2.sfc` are system firmware;
Game Boy ROMs under the SGB collection remain eligible.
Game Gear remains a separate console in the menu and reports, but uses the
documented shared `Cheats/SMS` folder for CRC, title and candidate lookup. This
mapping does not change Master System game selection or enable other cross-folder
lookups. `--system GameGear` and `--all` include this mapping.
SGB checks only cheats installed in `Cheats/SGB`. Cheats in the Game Boy
folder do not count as SGB matches or candidates.
MegaCD also checks cheat ZIPs beside each disc image. A valid local ZIP
whose name matches the disc filename is a pass, whether or not central has a copy.
Central-only cheats are NOT A PASS and produce a notice. Local ZIPs with different
names are reported as NOT A PASS. For a passing local cheat, a larger corresponding
central ZIP produces a notice; the local match still passes. ZIP sizes are bytes,
and equal sizes do not prove equal contents. Local archives are not used for other
games or consoles or for rename proposals.
TGFX16-CD also checks its game folders: a valid local cheat ZIP passes without
a filename-match requirement. Central-only matches are notices, not passes; a
larger central ZIP is a notice without changing a local pass. ISO/audio tracks
referenced by a TGFX16-CD CUE are support assets rather than additional games.
Pass means an installed cheat was found; it does not certify gameplay behavior.

Actual games in test, prototype, and hack folders remain eligible. An SNES-only
scan also shows the number of distinct nonmatching ROM checksums so duplicate
copies in several collection folders do not look like separate missing games.

Use `--deep` to show matched-game details, read supported cartridge ROMs inside
ZIPs, and test cheat ZIPs for corruption. Normal ZIP checks use member CRCs from
archive metadata; NES, SNES, and N64 members are always read for their additional
CRC handling. ZIP archive checksums are not used as game CRCs. SMD interleaving
is not converted. Jaguar `.j64`, `.jag`, `.abs`, and `.cof`, Virtual Boy `.vb`/`.vboy`,
and Lynx `.lnx`/`.lyx` files are recognized.
SNES Satellaview `.bs` files are also scanned, both loose and inside ZIPs,
including copier-header removal when present. This format is only enabled for
SNES folders; broadcast-game filenames do not need to match when their CRCs do.

### CD games

MegaCD/SegaCD and TGFX16-CD/PCE-CD use **name-only matching**
for `.cue`, `.chd`, `.iso`, `.m3u`, `.ccd`, `.pbp`, and `.img` files. Disc CRCs
and game IDs are not verified for those systems, including with `--deep`. Playlist-referenced
images are not counted twice, and BIN/audio tracks are ignored. CD game ZIPs
are not scanned. Other CD systems and arcade ROM sets are outside this checker.

PSX follows [Main_MiSTer's asset lookup](https://github.com/MiSTer-devel/Main_MiSTer/blob/master/file_io.cpp):
an exact disc-basename ZIP beside the disc, then the exact basename in
`Cheats/PSX`, then `<internal-game-ID>.zip` directly in `Cheats/PSX`.
No CRC tags, region labels, punctuation or letter case are normalized for these
exact paths. Nested central ZIPs do not count. Similar titles and another disc's
ID do not pass and do not generate automatic copy proposals.

For PSX CUE/BIN data tracks (`MODE1/2352` and `MODE2/2352`, first `INDEX 01`
at zero), v20 reads sectors 22–46 and normalizes the serial using
[MiSTer's game-ID scan](https://github.com/MiSTer-devel/Main_MiSTer/blob/master/support/psx/psx.cpp).
Every playlist disc is checked individually. CHD and other image types,
nonzero first-track indexes, and missing/unrecognized IDs are explicitly
`PSX_UNVERIFIED` unless an exact filename ZIP already passes. Missing BIN files
also produce scan errors. Disc CRCs are not needed. A lookup pass does not
confirm that individual cheat codes work during gameplay.

PSX lists all installed ZIP names but opens and validates only exact filename/ID
lookup candidates for the scanned discs. `--deep` tests those candidate archives'
contents; unrelated PSX archives are explicitly recorded as unvalidated and do
not produce integrity errors. This avoids thousands of irrelevant ZIP reads.

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

The RTC and timezone managers are based on Alessandro "Locutus73" Miele's 2019
`rtc.sh` and `timezone.sh` scripts and retain GPL-3.0-or-later notices.

This is an independent collection and is not an official MiSTer-devel release. No ROMs or FPGA core binaries are included.
