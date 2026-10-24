# MiSTer Time Utilities

Python replacements for the stock `rtc.sh` and `timezone.sh`, with interactive
menus and separate status reporting. Each script uses Python's standard library.
Keep the original shell scripts if you want to retain them as alternatives.

| Name | File | Example |
| --- | --- | --- |
| RTC & Time Manager | [rtc_manager_v1.py](rtc_manager_v1.py) | `python3 rtc_manager_v1.py` |
| Timezone Manager | [timezone_manager_v1.py](timezone_manager_v1.py) | `python3 timezone_manager_v1.py` |

Copy the scripts to `/media/fat/Scripts` and run them from a MiSTer terminal or
SSH session. Use root for changes. Add `--status` to either command to inspect
the configuration without changing it. Neither utility creates report logs.

## RTC & Time Manager

Shows local/UTC time, detected RTC devices, a hardware-clock reading when
available, and whether `ntpdate` is installed. Choose to synchronize system time
from NTP, synchronize and then write the RTC, or save the current system time to
the RTC. All clock changes require confirmation.

The default server is `0.pool.ntp.org`; change it in the menu for the current
session. No preliminary ping is required. Failures are displayed instead of
claiming a successful sync. Hardware RTC writes use UTC and `--noadjfile`,
avoiding root remounts and `/etc/adjtime` changes. A successful NTP sync is
reported separately if a subsequent RTC write fails.

An absent hardware RTC does not prevent NTP system-time synchronization.
Updating system time can jump the current clock; this tool does not install a
background sync service or change startup configuration.

## Timezone Manager

Search the installed database by city/region, or enter an exact name such as
`America/Chicago` or `UTC`. No Internet connection is needed for manual selection.
City names with spaces, such as `New York`, match their database spelling.

Optional automatic detection uses the public-IP timezone returned by
[ipwho.is](https://ipwhois.io/documentation) over HTTPS. It runs only when chosen
and confirmed; VPNs and IP-location errors can affect the suggestion. Every
suggestion must match an installed timezone and is shown before saving.

The selected TZif file is atomically copied to `/media/fat/linux/timezone`,
the same persistent file used by the stock script and MiSTer's `/etc/localtime`
link. Unchanged selections do not rewrite the file. Identical zone aliases are
reported as equivalent; the original name cannot always be recovered from the
copied binary. Existing applications may need restarting to refresh their timezone.
Timezone changes affect local-time presentation, not the hardware RTC's UTC value.

## Attribution

Based on the MiSTer-devel/Scripts_MiSTer `rtc.sh` and `timezone.sh` scripts by
Alessandro "Locutus73" Miele (2019). Both Python utilities retain
GPL-3.0-or-later licensing notices in their headers.
