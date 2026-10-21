#!/usr/bin/env python3
"""Compare installed cheats with cartridge CRCs and game names. Read-only scan."""

import argparse
import difflib
import os
import re
import sys
import zipfile
import zlib
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

VERSION = "v9"
CHEATS_ROOT = os.environ.get("CHEATS_ROOT", "/media/fat/Cheats")
GAMES_ROOT = os.environ.get("GAMES_ROOT", "/media/fat/games")
LOG_DIR = os.environ.get("LOG_DIR", "/media/fat/Scripts/logs")
CRC_TAG = re.compile(r"\[([0-9a-f]{8})\]", re.I)
RED, GREEN, YELLOW, RESET = "\033[1;31m", "\033[1;32m", "\033[1;33m", "\033[0m"
# These are cartridge/standalone ROM formats, not CD images or MAME ZIP parts.
ROM_EXTENSIONS = set(".nes .fds .sfc .smc .gb .gbc .gba .sgb .gen .md .smd .sms "
                     ".gg .sg .pce .sgx .a26 .a52 .a78 .lnx .col .int .vec .ws "
                     ".wsc .ngp .ngc .n64 .z64 .v64 .vb .vboy .lyx .j64 .jag .abs .cof .rom .bin".split())
ALIASES = {
    "genesis": "megadrive", "md": "megadrive", "gameboy": "gameboy",
    "gb": "gameboy", "gbc": "gameboy", "gameboycolor": "gameboy",
    "gameboyadvance": "gba", "supernes": "snes", "superfamicom": "snes",
    "famicom": "nes", "pcengine": "turbografx16", "pce": "turbografx16",
    "tgfx16": "turbografx16", "tgfx16cd": "turbografx16cd", "turbografx": "turbografx16",
    "sms": "mastersystem", "segamastersystem": "mastersystem",
    "gg": "gamegear", "sega32x": "s32x", "32x": "s32x",
    "segacd": "megacd", "pcecd": "turbografx16cd", "pcenginecd": "turbografx16cd",
    "atarilynx": "lynx", "atarijaguar": "jaguar", "vb": "virtualboy",
    "playstation": "psx", "ps1": "psx",
}
CD_SYSTEMS = {"megacd", "turbografx16cd", "psx"}
CD_GAME_EXTENSIONS = {".cue", ".chd", ".iso", ".m3u", ".ccd", ".pbp", ".img"}
SPECIAL_SYSTEMS = {"saturn", "neogeocd", "mame", "hbmame", "arcade"}


def is_msu1_folder(name):
    return bool(re.search(r"(?<![a-z0-9])msu[\s_-]*1(?![a-z0-9])", name, re.I))


def system_key(name):
    key = re.sub(r"[^a-z0-9]", "", name.casefold())
    return ALIASES.get(key, key)


def title_key(stem):
    # Strip only CRC tags. Region/revision/hack tags must stay distinct.
    return CRC_TAG.sub("", stem).strip().casefold()


def walk_files(root, errors, systems=None):
    def failed(exc):
        errors.append("Scan error: {}".format(exc))
    for directory, dirs, files in os.walk(str(root), followlinks=False, onerror=failed):
        if Path(directory) == root and systems:
            dirs[:] = [name for name in dirs if system_key(name) in systems]
        relative = Path(directory).relative_to(root)
        if relative.parts and system_key(relative.parts[0]) == "snes":
            dirs[:] = [name for name in dirs if not is_msu1_folder(name)]
        dirs.sort(key=str.casefold)
        for name in sorted(files, key=str.casefold):
            path = Path(directory) / name
            if not path.is_symlink():
                yield path


def read_rom(stream, size, extension):
    """Raw CRC plus NES/SNES headerless CRCs."""
    prefix = stream.read(512)
    raw = zlib.crc32(prefix)
    offset = None
    if extension == ".nes" and prefix.startswith(b"NES\x1a"):
        offset = 16
    elif extension in (".sfc", ".smc") and size % 1024 == 512:
        offset = 512
    stripped = zlib.crc32(prefix[offset:]) if offset is not None else 0
    while True:
        block = stream.read(1024 * 1024)
        if not block:
            break
        raw = zlib.crc32(block, raw)
        if offset is not None:
            stripped = zlib.crc32(block, stripped)
    return "{:08X}".format(raw & 0xffffffff), (
        "{:08X}".format(stripped & 0xffffffff) if offset is not None else "")


def read_game(stream, size, extension):
    if extension not in (".z64", ".v64", ".n64"):
        raw, stripped = read_rom(stream, size, extension)
        return raw, stripped, ""
    raw = normalized = 0
    magic = None
    valid = size % 4 == 0
    while True:
        data = stream.read(1024 * 1024)
        if not data:
            break
        if magic is None:
            magic = data[:4]
        raw = zlib.crc32(data, raw)
        if magic == bytes.fromhex("80371240"):
            swapped = bytearray(data)
            swapped[0::2], swapped[1::2] = data[1::2], data[0::2]
        elif magic == bytes.fromhex("37804012"):
            swapped = data
        elif magic == bytes.fromhex("40123780"):
            swapped = bytearray(data)
            swapped[0::4], swapped[1::4] = data[2::4], data[3::4]
            swapped[2::4], swapped[3::4] = data[0::4], data[1::4]
        else:
            valid = False
            swapped = data
        if valid:
            normalized = zlib.crc32(swapped, normalized)
    return "{:08X}".format(raw & 0xffffffff), "", (
        "{:08X}".format(normalized & 0xffffffff) if valid and magic else "")


def inventory_games(root, wanted, errors, skipped, deep=False):
    games = []
    paths = list(walk_files(root, errors, wanted))
    descriptor_stems = {str(p.with_suffix("").resolve()).casefold()
                        for p in paths if p.suffix.casefold() in {".cue", ".ccd"}}
    playlist_members = set()
    for path in paths:
        rel = path.relative_to(root)
        if len(rel.parts) < 2 or system_key(rel.parts[0]) not in CD_SYSTEMS:
            continue
        if path.suffix.casefold() == ".m3u":
            try:
                for line in path.read_text(encoding="utf-8-sig").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        playlist_members.add(str((path.parent / line.replace("\\", "/")).resolve()).casefold())
            except (OSError, UnicodeError) as exc:
                errors.append("Playlist {}: {}".format(rel, exc))
    for path in paths:
        rel = path.relative_to(root)
        # Palette assets are expected support files, not skipped ROM candidates.
        if path.suffix.casefold() == ".pal":
            continue
        if len(rel.parts) < 2:
            skipped.append("Outside a system directory: " + str(rel))
            continue
        system = system_key(rel.parts[0])
        if (wanted and system not in wanted) or system in SPECIAL_SYSTEMS:
            continue
        ext = path.suffix.casefold()
        if system == "snes" and (is_msu1_folder(path.stem) or ext in {".msu", ".pcm"}):
            continue
        if system in CD_SYSTEMS:
            if str(path.resolve()).casefold() in playlist_members:
                continue
            if ext == ".img" and str(path.with_suffix("").resolve()).casefold() in descriptor_stems:
                continue
            if ext in CD_GAME_EXTENSIONS:
                games.append(dict(system=system, path=str(rel), stem=path.stem,
                                  crc="", stripped="", n64_crc=""))
            elif ext not in {".bin", ".wav", ".ogg", ".sub"}:
                skipped.append(str(rel))
            continue
        if ext not in ROM_EXTENSIONS and ext != ".zip":
            skipped.append(str(rel))
            continue
        try:
            if ext == ".zip":
                with zipfile.ZipFile(str(path)) as archive:
                    for info in archive.infolist():
                        member = Path(info.filename)
                        member_ext = member.suffix.casefold()
                        if info.is_dir() or member_ext not in ROM_EXTENSIONS:
                            continue
                        # ZIP CRC is the uncompressed member CRC, never the ZIP's CRC.
                        crc, stripped, n64_crc = "{:08X}".format(info.CRC), "", ""
                        if deep or member_ext in (".nes", ".sfc", ".smc", ".z64", ".v64", ".n64"):
                            with archive.open(info) as stream:
                                crc, stripped, n64_crc = read_game(stream, info.file_size, member_ext)
                        games.append(dict(system=system, path=str(rel) + "::" + info.filename,
                                          stem=member.stem, crc=crc, stripped=stripped, n64_crc=n64_crc))
            else:
                with path.open("rb") as stream:
                    crc, stripped, n64_crc = read_game(stream, path.stat().st_size, ext)
                games.append(dict(system=system, path=str(rel), stem=path.stem,
                                  crc=crc, stripped=stripped, n64_crc=n64_crc))
        except (OSError, ValueError, RuntimeError, NotImplementedError, zipfile.BadZipFile) as exc:
            errors.append("{}: {}".format(rel, exc))
    return games


def inventory_cheats(root, selected, errors, deep=False):
    cheats = []
    for path in walk_files(root, errors, selected):
        if path.suffix.casefold() != ".zip":
            continue
        rel = path.relative_to(root)
        system = system_key(rel.parts[0]) if len(rel.parts) > 1 else ""
        if selected and system not in selected:
            continue
        issue = ""
        try:
            with zipfile.ZipFile(str(path)) as archive:
                members = [i for i in archive.infolist() if not i.is_dir()]
                if not members:
                    issue = "Empty cheat archive"
                if deep:
                    bad = archive.testzip()
                    if bad:
                        issue = "Corrupt member: " + bad
        except (OSError, ValueError, RuntimeError, NotImplementedError, zipfile.BadZipFile) as exc:
            issue = str(exc)
        if issue:
            errors.append("Cheat {}: {}".format(rel, issue))
        tags = CRC_TAG.findall(path.stem)
        cheats.append(dict(system=system, path=str(rel), stem=path.stem,
                           crc=tags[-1].upper() if tags else "", issue=issue,
                           nested=len(rel.parts) > 2))
    return cheats


def compare(cheats, games):
    indexes = {kind: defaultdict(list) for kind in ("crc", "name")}
    for cheat in cheats:
        if cheat["issue"] or not cheat["system"] or cheat["system"] in SPECIAL_SYSTEMS:
            continue
        system = cheat["system"]
        if cheat["crc"]:
            indexes["crc"][system, cheat["crc"]].append(cheat)
        indexes["name"][system, title_key(cheat["stem"])].append(cheat)
    rows, missing = [], []
    for game in games:
        system = game["system"]
        matches = indexes["crc"].get((system, game["crc"]), []) if game["crc"] else []
        status = "CRC_MATCH"
        # NES iNES and SNES copier headers are excluded by MiSTer's loader CRC.
        rom_ext = Path(game["path"].split("::")[-1]).suffix.casefold()
        header_crc = game["stripped"] if rom_ext in (".nes", ".sfc", ".smc") else ""
        if not matches and header_crc:
            matches = indexes["crc"].get((system, header_crc), [])
            status = "HEADERLESS_CRC_MATCH"
        if not matches and game.get("n64_crc"):
            matches = indexes["crc"].get((system, game["n64_crc"]), [])
            status = "N64_BYTE_SWAPPED_CRC_MATCH"
        if not matches:
            matches = indexes["name"].get((system, title_key(game["stem"])), [])
            status = "EXACT_NAME_MATCH"
        if not matches:
            missing.append(game)
            continue
        for cheat in matches:
            crc_match = bool(cheat["crc"] and cheat["crc"] in (game["crc"], header_crc, game.get("n64_crc", "")))
            note = ""
            if status == "N64_BYTE_SWAPPED_CRC_MATCH":
                note = "N64 byte-swapped CRC: " + game["n64_crc"]
            elif status == "HEADERLESS_CRC_MATCH":
                note = "CRC matches ROM data excluding its header (MiSTer loader behavior)."
            elif status != "CRC_MATCH":
                note = "Counted as matched by name; cheat compatibility is not verified."
                if system in CD_SYSTEMS:
                    note += " CD image CRC/game ID is not checked."
                if cheat["crc"] and game["crc"] and not crc_match:
                    note += " Checksums differ."
            rows.append(dict(system=system, status=status, cheat=cheat["path"],
                             cheat_crc=cheat["crc"], game=game["path"],
                             game_crc=game["crc"], headerless_crc=game["stripped"],
                             crc_match=crc_match,
                             name_match=title_key(cheat["stem"]) == title_key(game["stem"]),
                             note=note))
    return rows, missing


def possible_matches(cheats, missing):
    titles = defaultdict(lambda: defaultdict(list))
    for cheat in cheats:
        if not cheat["issue"]:
            title = re.sub(r"[^a-z0-9]+", " ", title_key(cheat["stem"])).strip()
            if title:
                titles[cheat["system"]][title].append(cheat)
    candidates = defaultdict(list)
    for game in missing:
        title = re.sub(r"[^a-z0-9]+", " ", title_key(game["stem"])).strip()
        choices = titles[game["system"]]
        # Different numbered games must not become sequel suggestions.
        numbers = re.findall(r"\b\d+\b", title)
        compatible = [choice for choice in choices
                      if re.findall(r"\b\d+\b", choice) == numbers]
        for close in difflib.get_close_matches(title, sorted(compatible), n=3, cutoff=0.85):
            for cheat in choices[close]:
                candidates[game["system"], game["path"]].append(cheat)
    return candidates


def console_folders(root):
    folders = defaultdict(list)
    for path in root.iterdir():
        if path.is_dir() and not path.is_symlink():
            folders[system_key(path.name)].append(path.name)
    return folders


def select_consoles(cheats_root, games_root):
    cheat_folders = console_folders(cheats_root)
    game_folders = console_folders(games_root)
    common = sorted((set(cheat_folders) & set(game_folders)) - SPECIAL_SYSTEMS)
    if not common:
        print("No supported console folders found in both Cheats and games.")
        return set()
    print("\nSELECT CONSOLE TO CHECK")
    print("Only folders present in both trees are listed; aliases are recognized.")
    for number, system in enumerate(common, 1):
        print("  {}. {}  (games: {})".format(number,
              ", ".join(sorted(cheat_folders[system])),
              ", ".join(sorted(game_folders[system]))))
    print("  A. All listed consoles\n  Q. Quit")
    while True:
        try:
            answer = input("Select number(s), separated by commas: ").strip().casefold()
        except EOFError:
            print("\nNo selection. Use --system SNES or --all for noninteractive runs.")
            return set()
        if answer == "q":
            return set()
        if answer == "a":
            return set(common)
        try:
            numbers = [int(part.strip()) for part in answer.split(",")]
            if all(1 <= number <= len(common) for number in numbers):
                return {common[number - 1] for number in numbers}
        except ValueError:
            pass
        print("Enter a listed number, comma-separated numbers, A, or Q.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cheats-root", default=CHEATS_ROOT)
    parser.add_argument("--games-root", default=GAMES_ROOT)
    parser.add_argument("--log-dir", default=LOG_DIR)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--system", action="append", help="Skip menu; only this system (repeatable)")
    selection.add_argument("--all", action="store_true", help="Skip menu; scan all common consoles")
    parser.add_argument("--map", action="append", default=[], metavar="CHEAT=GAME",
                        help="Map different system folder names, e.g. Genesis=MegaDrive")
    parser.add_argument("--deep", action="store_true",
                        help="Include all matched-game details and verify ROM/cheat ZIP contents")
    args = parser.parse_args(argv)
    for mapping in args.map:
        if "=" not in mapping:
            parser.error("--map requires CHEAT=GAME")
        left, right = mapping.split("=", 1)
        if not left or not right:
            parser.error("--map requires two folder names")
        ALIASES[re.sub(r"[^a-z0-9]", "", left.casefold())] = system_key(right)
    cheats_root, games_root = Path(args.cheats_root), Path(args.games_root)
    for root in (cheats_root, games_root):
        if not root.is_dir():
            parser.error("Directory not found: " + str(root))
    selected = {system_key(s) for s in args.system or []}
    if args.all:
        selected = (set(console_folders(cheats_root)) & set(console_folders(games_root))) - SPECIAL_SYSTEMS
        if not selected:
            print("No supported consoles found in both trees.")
            return 0
    elif not selected:
        selected = select_consoles(cheats_root, games_root)
        if not selected:
            print("No scan performed. Existing reports are unchanged.")
            return 0
    print("Selected consoles: " + ", ".join(sorted(selected)), flush=True)
    errors, skipped = [], []
    print("MiSTer cheat check {} - scanning cheats...".format(VERSION), flush=True)
    cheats = inventory_cheats(cheats_root, selected, errors, args.deep)
    # Prune unselected console directories before recursive traversal.
    wanted = selected
    print("Scanning games and computing ROM CRCs (large collections may take time)...", flush=True)
    games = inventory_games(games_root, wanted, errors, skipped, args.deep)
    rows, missing = compare(cheats, games)
    candidates = possible_matches(cheats, missing)
    totals = Counter({system: 0 for system in selected})
    totals.update(g["system"] for g in games)
    unmatched = Counter(g["system"] for g in missing)
    possible = Counter(g["system"] for g in missing
                       if candidates.get((g["system"], g["path"])))
    lines = ["MISTER CHEAT / ROM COMPARISON REPORT " + VERSION, "=" * 72,
             "Generated: " + datetime.now().astimezone().isoformat(timespec="seconds"),
             "Cheats: " + str(cheats_root), "Games: " + str(games_root),
             "Cheat archives: {} | ROM files/members checked: {}".format(len(cheats), len(games)),
             "Scan errors: {} | Skipped files: {}".format(len(errors), len(skipped)), "",
             "QUICK SUMMARY", "-" * 72]
    for system in sorted(selected):
        if not totals[system]:
            lines.append("WARNING: {}: no supported ROMs checked; cheat coverage is UNKNOWN. See skipped files/errors.".format(system))
    lines.append("Games with matching cheats (CRC or exact name): {}".format(len(games) - len(missing)))
    lines.append("Games WITHOUT matching cheats: {}".format(len(missing)))
    lines.extend(["", "TALLY BY CONSOLE", "-" * 72,
                  "Console | Checked | Matched | Unmatched | With possible matches"])
    for system in sorted(totals):
        lines.append("{} | {} | {} | {} | {}".format(
            system, totals[system], totals[system] - unmatched[system],
            unmatched[system], possible[system]))
    def location(path):
        # ZIP member paths become virtual subfolders for report grouping.
        normalized = path.replace("\\", "/").replace("::", "/")
        parts = normalized.split("/")
        return parts[0], "/".join(parts[1:-1]) or "(console root)"

    def order(path):
        console, folder = location(path)
        return console.casefold(), folder.casefold(), path.casefold()

    def group_heading(path, previous):
        console, folder = location(path)
        if previous is None or console != previous[0]:
            lines.extend(["", "CONSOLE: " + console, "=" * 72])
        if previous != (console, folder):
            lines.extend(["", "  FOLDER: " + folder, "  " + "-" * 68])
        return console, folder

    missing.sort(key=lambda game: order(game["path"]))
    rows.sort(key=lambda row: order(row["game"]))
    lines.extend(["", "GAMES WITHOUT MATCHING CHEATS", "=" * 72])
    previous = None
    for game in missing:
        previous = group_heading(game["path"], previous)
        lines.append("    {}  CRC {}".format(game["path"], game["crc"] or "not checked (CD name-only)"))
        suggestions = candidates.get((game["system"], game["path"]), [])
        for cheat in suggestions:
            lines.append("      POSSIBLE MATCH (still unmatched): {}  CRC {}".format(
                cheat["path"], cheat["crc"] or "not tagged"))
        if not suggestions:
            lines.append("      No similar-name cheat found.")
    if not missing:
        lines.append("None among checked ROMs." if games else "No ROMs checked; cheat coverage is UNKNOWN.")
    if args.deep:
        lines.extend(["", "CONFIRMED MATCH DETAILS", "=" * 72])
        previous = None
        for row in rows:
            previous = group_heading(row["game"], previous)
            lines.extend(["    " + row["game"], "      {}: {}".format(row["status"], row["cheat"]),
                          "      Raw ROM CRC: {} | Cheat CRC: {}".format(
                              row["game_crc"] or "not checked (CD name-only)", row["cheat_crc"] or "not tagged")])
            if row["headerless_crc"]:
                lines.append("      Headerless CRC: " + row["headerless_crc"])
            if row["note"]:
                lines.append("      Note: " + row["note"])
    lines.extend(["", "ERRORS / INCOMPLETE SCANS", "=" * 72] + (errors or ["None"]))
    lines.extend(["", "SKIPPED FILES (UNSUPPORTED FORMAT OR LOCATION)", "=" * 72]
                 + (skipped or ["None"]))
    report = "\n".join(lines) + "\n"
    output = Path(args.log_dir)
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / "cheat_rom_comparison_report.log"
    report_path.write_text(report, encoding="utf-8")
    colors = sys.stdout.isatty() and "NO_COLOR" not in os.environ and os.environ.get("TERM") != "dumb"
    for line in lines:
        color = GREEN if line.startswith("CRC_MATCH") else (
            RED if any(line.startswith(s) for s in ("INVALID_", "NO_GAME_", "TITLE_MATCH_")) else
            YELLOW if "CANDIDATE" in line or line.startswith("NAME_MATCH_CRC_DIFFERS") else "")
        print(color + line + RESET if colors and color else line)
    print("\nReport saved to:\n{}".format(report_path))
    return 1 if errors else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nScan canceled.", file=sys.stderr)
        sys.exit(130)
    except OSError as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        sys.exit(1)
