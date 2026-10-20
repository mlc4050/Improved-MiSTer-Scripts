# Improved MiSTer Scripts

A collection of nine standalone Python utilities for managing and maintaining a MiSTer FPGA installation, created by [mlc4050](https://github.com/mlc4050).

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
```

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
