#!/usr/bin/env python3
"""Compare installed cheats with cartridge CRCs and game names. Read-only scan."""

import argparse
import difflib
import json
import os
import re
import sys
import zipfile
import zlib
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

VERSION = "v20"
CHEATS_ROOT = os.environ.get("CHEATS_ROOT", "/media/fat/Cheats")
GAMES_ROOT = os.environ.get("GAMES_ROOT", "/media/fat/games")
LOG_DIR = os.environ.get("LOG_DIR", "/media/fat/Scripts/logs")
CRC_TAG = re.compile(r"\[([0-9a-f]{8})\]", re.I)
RED, GREEN, YELLOW, RESET = "\033[1;31m", "\033[1;32m", "\033[1;33m", "\033[0m"
# These are cartridge/standalone ROM formats, not CD images or MAME ZIP parts.
ROM_EXTENSIONS = set(".nes .fds .sfc .smc .gb .gbc .gba .sgb .gen .md .smd .sms "
                     ".gg .sg .pce .sgx .a26 .a52 .a78 .lnx .col .int .vec .ws "
                     ".wsc .ngp .ngc .n64 .z64 .v64 .vb .vboy .lyx .j64 .jag .abs .cof .rom .bin".split())
SNES_ROM_EXTENSIONS = {".sfc", ".smc", ".bs"}
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
SHARED_CHEAT_SYSTEMS = {"gamegear": "mastersystem"}
LOCAL_CD_SYSTEMS = {"megacd", "turbografx16cd"}
CD_GAME_EXTENSIONS = {".cue", ".chd", ".iso", ".m3u", ".ccd", ".pbp", ".img"}
SPECIAL_SYSTEMS = {"saturn", "neogeocd", "mame", "hbmame", "arcade"}


def is_msu1_folder(name):
    return bool(re.search(r"(?<![a-z0-9])msu[\s_-]*1(?![a-z0-9])", name, re.I))


def system_key(name):
    key = re.sub(r"[^a-z0-9]", "", name.casefold())
    return ALIASES.get(key, key)


def cheat_lookup_system(system):
    # Game Gear uses the SMS core and its installed cheat directory.
    return SHARED_CHEAT_SYSTEMS.get(system, system)


def available_game_systems(cheat_folders, game_folders):
    return {system for system in game_folders
            if cheat_lookup_system(system) in cheat_folders and system not in SPECIAL_SYSTEMS}


def title_key(stem):
    # Strip only CRC tags. Region/revision/hack tags must stay distinct.
    return CRC_TAG.sub("", stem).strip().casefold()


def match_title_key(system, stem):
    title = title_key(stem)
    if system in CD_SYSTEMS:
        # Cheat collections include media labels absent from disc image names.
        title = re.sub(r"\(\s*(?:cd|scd)(?:\s*,\s*(?:cd|scd))*\s*\)", "", title)
        # Known collection labels may occur on many different disc titles.
        # Only drop a whole tag if every token belongs to this allowlist.
        collection_tags = {"fact", "fadt", "fabt"}
        title = re.sub(r"\(([^()]*)\)",
                       lambda m: "" if {part.strip() for part in m.group(1).split(",")} <= collection_tags
                       else m.group(0), title)
        regions = {"jpn": "japan", "jap": "japan", "us": "usa",
                   "euro": "europe", "eur": "europe"}
        title = re.sub(r"\(\s*(jpn|jap|us|euro|eur)\s*\)",
                       lambda m: "(" + regions[m.group(1)] + ")", title)
        title = re.sub(r"\s*\(", " (", title)
        title = re.sub(r"\s+", " ", title).strip()
        if system == "turbografx16cd":
            # Specific collection naming differences; do not discard arbitrary
            # revision/hack tags or reorder unrelated game titles.
            title = {
                "fantastic night dreams - cotton (usa)":
                    "cotton - fantastic night dreams (usa)",
            }.get(title, title)
    return title


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
    elif extension in SNES_ROM_EXTENSIONS and size % 1024 == 512:
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


def snes_support_reason(rel):
    """Identify known firmware and diagnostic ROMs without hiding game folders."""
    if system_key(rel.parts[0]) != "snes":
        return ""
    if len(rel.parts) == 2 and rel.name.casefold() in {
            "boot.rom", "boot0.rom", "boot1.rom", "bsx_bios.rom"}:
        return "SNES startup/BS-X firmware"
    title = rel.stem.casefold()
    if re.match(r"^(?:240p test suite|hd retrovision test rom)(?:\b|_)", title) or title == "snes test program":
        return "SNES diagnostic/calibration utility"
    if re.match(r"^game genie\s*\(", title):
        return "Game Genie cheat-device utility"
    return ""


def support_rom_reason(rel):
    reason = snes_support_reason(rel)
    system = system_key(rel.parts[0])
    if reason:
        return reason
    if system == "gameboy":
        if len(rel.parts) == 2 and re.fullmatch(r"boot[0-3]?\.rom", rel.name, re.I):
            return "Game Boy startup firmware"
        if (len(rel.parts) > 2 and rel.parts[1].casefold() == "borders"
                and rel.suffix.casefold() == ".sgb"):
            return "Game Boy border artwork (not a game ROM)"
        return ""
    if system == "gba":
        if len(rel.parts) == 2 and rel.name.casefold() == "boot.rom":
            return "GBA startup firmware"
        if rel.stem.casefold().startswith("game boy advance video - "):
            return "GBA Video cartridge (non-game media)"
        return ""
    if system == "megadrive":
        title = rel.stem.casefold()
        if re.match(r"^game genie\s*\(", title):
            return "Game Genie cheat-device utility"
        if (re.match(r"^240p test suite(?:\b|_)", title)
                or re.match(r"^controller test - polygame\b", title)):
            return "Mega Drive diagnostic/calibration utility"
        if (len(rel.parts) > 2 and rel.parts[1].casefold() == "paprium"
                and (rel.suffix.casefold() == ".wav" or rel.name.casefold() == "paprium.cue")):
            return "Paprium audio/support asset (not a cartridge ROM)"
        return ""
    if system == "n64":
        if len(rel.parts) == 2:
            if rel.name.casefold() in {"boot.rom", "boot1.rom"}:
                return "N64 startup firmware"
            if rel.name.casefold() == "n64-database.txt":
                return "N64 ROM configuration database"
        return ""
    if system == "lynx":
        if len(rel.parts) == 2 and rel.name.casefold() == "boot0.rom":
            return "Atari Lynx startup firmware"
        return ""
    if system == "sgb":
        if len(rel.parts) == 2 and rel.name.casefold() in {"super game boy.sfc", "super game boy 2.sfc"}:
            return "Super Game Boy system firmware"
        return ""
    if system != "nes":
        return ""
    if len(rel.parts) == 2 and re.fullmatch(r"boot[0-3]?\.rom", rel.name, re.I):
        return "NES startup firmware"
    title = rel.stem.casefold()
    if (re.match(r"^240p test suite(?:\b|_)", title)
            or re.match(r"^nintendo world class service - (?:control deck|joystick|power pad) test cartridge\b", title)
            or re.match(r"^soundtest 2\b", title)
            or re.match(r"^zap ruder - zapper test program\b", title)):
        return "NES diagnostic/calibration utility"
    return ""


def inventory_games(root, wanted, errors, skipped, deep=False, excluded=None):
    games = []
    paths = list(walk_files(root, errors, wanted))
    descriptor_stems = {str(p.with_suffix("").resolve()).casefold()
                        for p in paths if p.suffix.casefold() in {".cue", ".ccd"}}
    playlist_members = set()
    tgfx_cd_tracks = {}
    for path in paths:
        rel = path.relative_to(root)
        if len(rel.parts) < 2 or system_key(rel.parts[0]) not in CD_SYSTEMS:
            continue
        if system_key(rel.parts[0]) == "turbografx16cd" and path.suffix.casefold() == ".cue":
            try:
                cue_text = path.read_text(encoding="utf-8-sig")
                for quoted, bare in re.findall(r'^\s*FILE\s+(?:"([^"]+)"|(\S+))', cue_text, re.M | re.I):
                    member = (path.parent / (quoted or bare).replace("\\", "/")).resolve()
                    tgfx_cd_tracks[str(member).casefold()] = str(rel)
            except (OSError, UnicodeError) as exc:
                errors.append("CUE {}: {}".format(rel, exc))
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
        if path.suffix.casefold() in {".pal", ".gbp"}:
            continue
        if len(rel.parts) < 2:
            skipped.append("Outside a system directory: " + str(rel))
            continue
        system = system_key(rel.parts[0])
        if (wanted and system not in wanted) or system in SPECIAL_SYSTEMS:
            continue
        ext = path.suffix.casefold()
        support_reason = support_rom_reason(rel)
        if support_reason:
            if excluded is not None:
                excluded.append("{}: {}".format(rel, support_reason))
            continue
        if system == "snes" and (is_msu1_folder(path.stem) or ext in {".msu", ".pcm"}):
            continue
        if system in CD_SYSTEMS:
            if system == "turbografx16cd" and str(path.resolve()).casefold() in tgfx_cd_tracks:
                if excluded is not None:
                    excluded.append("{}: CD track referenced by {}".format(rel, tgfx_cd_tracks[str(path.resolve()).casefold()]))
                continue
            if system == "psx" and ext == ".m3u":
                skipped.append(str(rel) + ": playlist; PSX discs checked individually")
                continue
            if system != "psx" and str(path.resolve()).casefold() in playlist_members:
                continue
            if ext == ".img" and str(path.with_suffix("").resolve()).casefold() in descriptor_stems:
                continue
            if ext in CD_GAME_EXTENSIONS:
                games.append(dict(system=system, path=str(rel), stem=path.stem,
                                  crc="", stripped="", n64_crc=""))
            elif ext not in {".bin", ".wav", ".ogg", ".sub"}:
                skipped.append(str(rel))
            continue
        system_extensions = ROM_EXTENSIONS | ({".bs"} if system == "snes" else set())
        if ext not in system_extensions and ext != ".zip":
            skipped.append(str(rel))
            continue
        try:
            if ext == ".zip":
                with zipfile.ZipFile(str(path)) as archive:
                    for info in archive.infolist():
                        member = Path(info.filename)
                        member_ext = member.suffix.casefold()
                        if info.is_dir() or member_ext not in system_extensions:
                            continue
                        support_reason = support_rom_reason(rel.parent / member)
                        if support_reason:
                            if excluded is not None:
                                excluded.append("{}::{}: {}".format(rel, info.filename, support_reason))
                            continue
                        # ZIP CRC is the uncompressed member CRC, never the ZIP's CRC.
                        crc, stripped, n64_crc = "{:08X}".format(info.CRC), "", ""
                        if deep or member_ext in (".nes", ".z64", ".v64", ".n64") or member_ext in SNES_ROM_EXTENSIONS:
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


PSX_ID_PREFIXES = (b"SCES", b"SLES", b"SCUS", b"SLUS", b"SCPM", b"SLPM",
                   b"SCPS", b"SLPS", b"SIPS", b"PUPX", b"PEPX", b"PAPX",
                   b"PCPX", b"SCZS", b"SCED", b"SLED")


def psx_game_id(path):
    """Mirror Main_MiSTer's psx_get_game_info scan, not a whole-disc CRC."""
    if path.suffix.casefold() != ".cue":
        return "", "Game-ID reader currently supports CUE/BIN only; this disc is unverified."
    filename, mode, track, index = None, None, None, None
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        match = re.match(r'\s*FILE\s+(?:"([^"]+)"|(\S+))\s+(\S+)', line, re.I)
        if match:
            filename = match.group(1) or match.group(2)
            if match.group(3).upper() != "BINARY":
                return "", "Unsupported first-track file type; disc unverified."
        match = re.match(r"\s*TRACK\s+(\d+)\s+(\S+)", line, re.I)
        if match:
            track, mode = int(match.group(1)), match.group(2).upper()
            if track != 1:
                break
        match = re.match(r"\s*INDEX\s+01\s+(\d+):(\d+):(\d+)", line, re.I)
        if match and track == 1:
            minute, second, frame = map(int, match.groups())
            index = (minute * 60 + second) * 75 + frame
            break
    if not filename or mode not in {"MODE1/2352", "MODE2/2352"} or index != 0:
        return "", "Unsupported/malformed first track or nonzero INDEX 01; disc unverified."
    track_path = path.parent / filename.replace("\\", "/")
    with track_path.open("rb") as stream:
        stream.seek(22 * 2352)
        data = stream.read(25 * 2352)
    if len(data) != 25 * 2352:
        return "", "Truncated game-ID scan area; disc unverified."
    for offset in range(0, len(data), 2352):
        sector = data[offset:offset + 2352]
        start = -1
        for prefix in PSX_ID_PREFIXES:
            start = sector.find(prefix)
            if start >= 0:
                break
        if start < 0:
            continue
        end = sector.find(b";1", start)
        if end < 0:
            continue
        value = sector[start:end]
        if len(value) == 11:
            if value[4:5] == b"_":
                value = value[:4] + b"-" + value[5:]
            if value[8:9] == b".":
                value = value[:8] + value[9:]
        value = value[:10].decode("ascii", errors="replace")
        if re.fullmatch(r"[A-Z]{4}-\d{5}", value):
            return value, ""
        return "", "MiSTer found a nonstandard game ID; disc unverified."
    return "", "No game ID in MiSTer's scan area; disc unverified."


def inventory_psx_lookup(root, games, errors, deep=False):
    for game in games:
        if game["system"] != "psx":
            continue
        path = root / game["path"]
        game["game_id"], game["psx_issue"] = "", ""
        game["psx_local_cheats"] = []
        try:
            game["game_id"], game["psx_issue"] = psx_game_id(path)
        except (OSError, UnicodeError, ValueError) as exc:
            game["psx_issue"] = "Cannot read game ID: " + str(exc)
            errors.append("PSX {}: {}".format(game["path"], exc))
        # PSX tries a ZIP with the exact disc basename beside the disc first.
        local = path.with_suffix(".zip")
        if not local.is_file() or local.is_symlink():
            continue
        try:
            with zipfile.ZipFile(str(local)) as archive:
                members = [i for i in archive.infolist() if not i.is_dir()]
                if not members:
                    raise ValueError("Empty cheat archive")
                if deep and archive.testzip():
                    raise ValueError("Corrupt cheat archive")
            game["psx_local_cheats"].append(dict(path=str(local), crc="", issue="",
                                                stem=local.stem, system="psx"))
        except (OSError, ValueError, RuntimeError, NotImplementedError, zipfile.BadZipFile) as exc:
            errors.append("PSX local cheat {}: {}".format(local, exc))


def psx_cheat_matches(cheats, game):
    local = game.get("psx_local_cheats", [])
    if local:
        return "PSX_LOCAL_FILENAME_MATCH", local
    # Main_MiSTer checks only the core directory, not nested subdirectories.
    usable = [c for c in cheats if c["system"] == "psx" and not c["issue"] and c.get("validated", True)
              and not c.get("nested", len(Path(c["path"]).parts) > 2)]
    for name, status in ((game["stem"], "PSX_FILENAME_MATCH"),
                         (game.get("game_id", ""), "PSX_GAME_ID_MATCH")):
        matches = [c for c in usable if name and Path(c["path"]).name == name + ".zip"]
        if matches:
            return status, matches
    return "", []


def inventory_cheats(root, selected, errors, deep=False, psx_targets=None):
    cheats = []
    for path in walk_files(root, errors, selected):
        if path.suffix.casefold() != ".zip":
            continue
        rel = path.relative_to(root)
        system = system_key(rel.parts[0]) if len(rel.parts) > 1 else ""
        if selected and system not in selected:
            continue
        issue = ""
        validate = not (system == "psx" and psx_targets is not None and
                        (len(rel.parts) != 2 or path.name not in psx_targets))
        try:
            if validate:
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
                           validated=validate,
                           nested=len(rel.parts) > 2, size_bytes=path.stat().st_size))
    return cheats



def inventory_cd_local_cheats(root, games, errors, skipped, deep=False):
    """Recognize local cheats only for explicitly approved CD consoles."""
    by_folder = {}
    recognized = set()
    for game in games:
        if game["system"] not in LOCAL_CD_SYSTEMS:
            continue
        folder = (root / game["path"]).parent
        if folder not in by_folder:
            found = []
            try:
                paths = sorted(folder.iterdir(), key=lambda p: p.name.casefold())
            except OSError as exc:
                errors.append("CD cheat folder {}: {}".format(folder, exc))
                paths = []
            for path in paths:
                if path.suffix.casefold() != ".zip" or not path.is_file() or path.is_symlink():
                    continue
                try:
                    with zipfile.ZipFile(str(path)) as archive:
                        members = [i for i in archive.infolist() if not i.is_dir()]
                        # Disc-image ZIPs and empty ZIPs are not cheat archives.
                        codes = [i for i in members if i.filename.casefold().endswith(".gg")]
                        if not codes:
                            continue
                        if any(not i.file_size or i.file_size % 16 for i in codes):
                            raise ValueError("Invalid cheat entry length (expected multiples of 16 bytes)")
                        if deep:
                            bad = archive.testzip()
                            if bad:
                                raise ValueError("Corrupt member: " + bad)
                    found.append(dict(system=game["system"], path=str(path), stem=path.stem,
                                      crc="", issue="", source="GAME_FOLDER", size_bytes=path.stat().st_size))
                    recognized.add(str(path.relative_to(root)))
                except (OSError, ValueError, RuntimeError, NotImplementedError, zipfile.BadZipFile) as exc:
                    errors.append("CD local cheat {}: {}".format(path, exc))
            by_folder[folder] = found
        game["local_cheats"] = by_folder[folder]
    skipped[:] = [path for path in skipped if path not in recognized]


def matching_cd_local_cheats(game):
    if game["system"] == "turbografx16cd":
        return game.get("local_cheats", [])
    return [cheat for cheat in game.get("local_cheats", [])
            if title_key(cheat["stem"]) == title_key(game["stem"])]


def compare(cheats, games):
    indexes = {kind: defaultdict(list) for kind in ("crc", "name")}
    for cheat in cheats:
        if cheat["issue"] or not cheat["system"] or cheat["system"] in SPECIAL_SYSTEMS:
            continue
        system = cheat["system"]
        if cheat["crc"]:
            indexes["crc"][system, cheat["crc"]].append(cheat)
        # CRC metadata is not part of the agreed game-title comparison.
        name = match_title_key(system, cheat["stem"])
        indexes["name"][system, name].append(cheat)
    rows, missing = [], []
    for game in games:
        system = game["system"]
        if system == "psx":
            status, matches = psx_cheat_matches(cheats, game)
            if not matches:
                missing.append(game)
            for cheat in matches:
                rows.append(dict(system=system, status=status, cheat=cheat["path"],
                                 cheat_crc="", game=game["path"], game_crc="",
                                 headerless_crc="", crc_match=False,
                                 name_match=status != "PSX_GAME_ID_MATCH", game_id=game.get("game_id", ""),
                                 note="PASS: PSX loader finds this installed ZIP. Gameplay not tested."))
            continue
        lookup_system = cheat_lookup_system(system)
        matches = matching_cd_local_cheats(game) if system in LOCAL_CD_SYSTEMS else []
        status = "LOCAL_CHEAT_ZIP" if matches else "CRC_MATCH"
        if not matches:
            matches = indexes["crc"].get((lookup_system, game["crc"]), []) if game["crc"] else []
        # NES iNES and SNES copier headers are excluded by MiSTer's loader CRC.
        rom_ext = Path(game["path"].split("::")[-1]).suffix.casefold()
        header_crc = game["stripped"] if rom_ext == ".nes" or rom_ext in SNES_ROM_EXTENSIONS else ""
        if not matches and header_crc:
            matches = indexes["crc"].get((lookup_system, header_crc), [])
            status = "HEADERLESS_CRC_MATCH"
        if not matches and game.get("n64_crc"):
            matches = indexes["crc"].get((lookup_system, game["n64_crc"]), [])
            status = "N64_BYTE_SWAPPED_CRC_MATCH"
        if not matches:
            name = match_title_key(system, game["stem"])
            matches = indexes["name"].get((lookup_system, name), [])
            status = "EXACT_NAME_MATCH"
        if not matches:
            missing.append(game)
            continue
        for cheat in matches:
            crc_match = bool(cheat["crc"] and cheat["crc"] in (game["crc"], header_crc, game.get("n64_crc", "")))
            note = ""
            if status == "LOCAL_CHEAT_ZIP":
                note = "PASS: Local cheat ZIP found for this CD console. Gameplay compatibility not tested."
            elif status == "N64_BYTE_SWAPPED_CRC_MATCH":
                note = "N64 byte-swapped CRC: " + game["n64_crc"]
            elif status == "HEADERLESS_CRC_MATCH":
                note = "CRC matches ROM data excluding its header (MiSTer loader behavior)."
            elif status != "CRC_MATCH":
                if system in CD_SYSTEMS:
                    note = "CD collection title match. CD image CRC/game ID is not checked."
                else:
                    note = "Titles match after removing CRC tags; CRC agreement is not required for a name match."
                if cheat["crc"] and game["crc"] and not crc_match:
                    note += " Checksums differ."
            rows.append(dict(system=system, status=status, cheat=cheat["path"],
                             cheat_crc=cheat["crc"], game=game["path"],
                             game_crc=game["crc"], headerless_crc=game["stripped"],
                             crc_match=crc_match,
                             name_match=match_title_key(system, cheat["stem"]) == match_title_key(system, game["stem"]),
                             note=note))
    return rows, missing


def translation_marked(text):
    return bool(re.search(r"(?<![a-z])translations?(?![a-z])|\bt[+-](?:eng|en)(?![a-z])|"
                          r"english\s*\+\s*unlocks|\bt-en\b", text, re.I))


def hack_marked(text):
    return bool(re.search(r"(?<![a-z])(?:patch(?:ed)?|hacks?|rom[ _-]*hacks?|modification|"
                          r"enhanced[ _-]+colou?rs?|pyron[ _-]+colou?rs?|everdrive[ _-]+fixed)(?![a-z])",
                          text, re.I))


def proposal_exclusions(games):
    # A translated ROM may also be copied into multiplayer or curated folders.
    translated = {(g["system"], g["crc"]) for g in games
                  if g["crc"] and translation_marked(g["path"])}
    hacked = {(g["system"], g["crc"]) for g in games
              if g["crc"] and hack_marked(g["path"])}
    reasons = {}
    for game in games:
        reason = ""
        if re.search(r"top[ _-]*100\b", game["path"], re.I):
            reason = "Top 100 folder: excluded from filename proposals."
        elif translation_marked(game["path"]) or (game["system"], game["crc"]) in translated:
            reason = "Translation: excluded from filename proposals (including identical CRC copies)."
        elif re.search(r"pal[ _-]*to[ _-]*ntsc|\bntsc[ _-]+(?:60\s*hz|fix|hidden stages unlock)\b",
                       game["path"], re.I):
            reason = "PAL-to-NTSC conversion hack: excluded from filename proposals."
        elif hack_marked(game["path"]) or (game["system"], game["crc"]) in hacked:
            reason = "Explicit patched/hacked build: excluded from filename proposals (including identical CRC copies)."
        if reason:
            reasons[game["system"], game["path"]] = reason
    return reasons


def title_regions(stem):
    aliases = {"j": "japan", "jpn": "japan", "jap": "japan", "japan": "japan",
               "u": "usa", "us": "usa", "usa": "usa",
               "e": "europe", "eur": "europe", "euro": "europe", "europe": "europe"}
    regions = set()
    for tag in re.findall(r"\(([^()]*)\)", stem.casefold()):
        for token in tag.split(","):
            token = token.strip()
            if token in aliases:
                regions.add(aliases[token])
            elif token in {"world", "asia", "france", "germany", "spain", "italy",
                           "korea", "china", "brazil", "australia", "canada", "sweden"}:
                regions.add(token)
    return regions


def suggestion_title(system, stem):
    title = match_title_key(system, stem)
    # Remove release metadata, preserving text after it: a named romhack suffix
    # must not disappear merely because it follows a (USA) tag.
    title = re.sub(r"\([^()]*\)|\[[^\[\]]*\]", " ", title)
    title = re.sub(r"\s+pal[ -]to[ -]ntsc patched\b.*$", "", title)
    title = re.sub(r"\s+ntsc(?:\s+(?:fix|60\s*hz|hidden stages unlock))\b.*$", "", title)
    title = re.sub(r"\s*-?\s+skip waits\b.*$", "", title)
    title = re.sub(r"^the\s+|,\s*the\s*$", "", title.strip())
    # Numbers and Roman numerals distinguish sequels and yearly releases.
    identifiers = tuple(re.findall(r"\b(?:\d+|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii)\b", title))
    key = re.sub(r"[^a-z0-9]", "", title)
    if system == "snes":
        # Reviewed collection title aliases; never apply across console systems.
        key = {"frontmissiongunhazard": "frontmissionseriesgunhazard",
               "puzzlebobble": "bustamove",
               "superearthdefenseforce": "earthdefenseforce",
               "superedf": "earthdefenseforce",
               "megalomaniajikuudaisenryaku": "megalomania"}.get(key, key)
    elif system == "turbografx16cd":
        # Reviewed subtitle variants, used only for central availability reports
        # and suggestions; local TGFX16-CD passes never depend on these aliases.
        key = {"rainbowislandsthestoryofbubblebobble2": "rainbowislands",
               "imagefightiioperationdeepstriker": "imagefightii"}.get(key, key)
    elif system == "gameboy":
        # The Japanese cartridge title includes Kaisen Game; older cheat names
        # use Radar Mission. Keep this alias local to this console and region gate.
        key = {"kaisengameradarmission": "radarmission"}.get(key, key)
    return key, identifiers


def release_metadata(stem):
    """Keep non-CRC, non-region release tags significant for suggestions too."""
    tags = []
    for paren, bracket in re.findall(r"\(([^()]*)\)|\[([^\[\]]*)\]", CRC_TAG.sub("", stem)):
        tokens = []
        for token in (paren or bracket).casefold().split(","):
            token = token.strip()
            if paren and title_regions("(" + token + ")"):
                continue
            normalized = re.sub(r"[^a-z0-9]", "", token)
            if normalized:
                tokens.append(normalized)
        if tokens:
            tags.append(tuple(sorted(tokens)))
    return tuple(sorted(tags))


def possible_matches(cheats, missing, excluded=None):
    excluded = proposal_exclusions(missing) if excluded is None else excluded
    indexed = defaultdict(list)
    for cheat in cheats:
        if not cheat["issue"] and not translation_marked(cheat["path"]):
            key, identifiers = suggestion_title(cheat["system"], cheat["stem"])
            if key:
                indexed[cheat["system"]].append((cheat, key, identifiers, title_regions(cheat["stem"]),
                                                release_metadata(cheat["stem"])))
    candidates = defaultdict(list)
    for game in missing:
        if (game["system"], game["path"]) in excluded:
            continue
        title, identifiers = suggestion_title(game["system"], game["stem"])
        if not title:
            continue
        ranked = []
        regions = title_regions(game["stem"])
        metadata = release_metadata(game["stem"])
        for cheat, other, other_ids, other_regions, other_metadata in indexed[cheat_lookup_system(game["system"])]:
            if regions and other_regions and "world" not in regions | other_regions and not regions & other_regions:
                continue
            if metadata != other_metadata:
                continue
            if title == other:
                score, reason = 1.0, "Same normalized title/spacing or reviewed regional alias."
            elif identifiers == other_ids and min(len(title), len(other)) >= 8:
                # Safe upper bounds avoid expensive full comparisons on MiSTer.
                if 2 * min(len(title), len(other)) < 0.94 * (len(title) + len(other)):
                    continue
                matcher = difflib.SequenceMatcher(None, title, other, autojunk=False)
                if matcher.quick_ratio() < 0.94:
                    continue
                score = matcher.ratio()
                if score < 0.94:
                    continue
                reason = "Close spelling ({:.0%}); sequel/year identifiers agree.".format(score)
            else:
                continue
            item = dict(cheat, candidate_reason=reason, candidate_score=score)
            ranked.append(item)
        candidates[game["system"], game["path"]] = sorted(
            ranked, key=lambda c: (-c["candidate_score"], c["path"].casefold()))
    return candidates



def cd_central_reports(cheats, game):
    """Central archives are information only, including size comparisons."""
    if game["system"] not in LOCAL_CD_SYSTEMS:
        return []
    system = game["system"]
    local_titles = {match_title_key(system, c["stem"]) for c in game.get("local_cheats", [])}
    close = {c["path"] for c in possible_matches(cheats, [game]).get((system, game["path"]), [])}
    reports = []
    game_title = suggestion_title(system, game["stem"])[0]
    regions = title_regions(game["stem"])
    def without_revision_tags(stem):
        return tuple(tag for tag in release_metadata(match_title_key(system, stem))
                     if not all(re.fullmatch(r"re\d*|\d+r", token) for token in tag))
    for cheat in cheats:
        if cheat["system"] != system or cheat["issue"]:
            continue
        exact = match_title_key(system, cheat["stem"]) == match_title_key(system, game["stem"])
        other_regions = title_regions(cheat["stem"])
        related = (game_title == suggestion_title(system, cheat["stem"])[0]
                   and not (regions and other_regions and not regions & other_regions)
                   and without_revision_tags(game["stem"]) == without_revision_tags(cheat["stem"]))
        local_title_match = match_title_key(system, cheat["stem"]) in local_titles
        if not (exact or cheat["path"] in close or related or local_title_match):
            continue
        comparisons = []
        for local in game.get("local_cheats", []):
            local_size, central_size = local.get("size_bytes"), cheat.get("size_bytes")
            status = ("UNKNOWN" if local_size is None or central_size is None else
                      "SAME_SIZE" if local_size == central_size else "DIFFERENT_SIZE")
            comparisons.append(dict(local_path=local["path"], local_size_bytes=local_size,
                                    central_size_bytes=central_size, status=status))
        reports.append(dict(path=cheat["path"], size_bytes=cheat.get("size_bytes"),
                            relationship=("Exact title" if exact else "Matches local cheat ZIP title" if local_title_match
                                          else "Close title or different release tag; review only"),
                            size_comparisons=comparisons))
    return reports


def classify_games(cheats, games, rows):
    by_game = defaultdict(list)
    for row in rows:
        by_game[row["system"], row["game"]].append(row)
    excluded = proposal_exclusions(games)
    unverified = [g for g in games if not by_game[g["system"], g["path"]]]
    candidates = possible_matches(cheats, unverified, excluded)
    existing_names = {(c["system"], c["stem"].casefold()) for c in cheats}
    results = []
    for game in games:
        key = game["system"], game["path"]
        lookup = by_game[key]
        suggestions, proposals = [], []
        exact_name = any(r["status"] == "EXACT_NAME_MATCH" for r in lookup)
        central_reports = cd_central_reports(cheats, game)
        if game["system"] == "psx":
            if lookup:
                classification = "MATCHED_BY_GAME_ID" if lookup[0]["status"] == "PSX_GAME_ID_MATCH" else "MATCHED_BY_PSX_FILENAME"
                reason = "PASS: PSX loader finds {}{}; gameplay not tested.".format(
                    "the exact game-ID ZIP " if classification == "MATCHED_BY_GAME_ID" else "the exact disc-filename ZIP ", lookup[0]["cheat"])
            elif game.get("psx_issue") or not game.get("game_id"):
                classification, reason = "PSX_UNVERIFIED", game.get("psx_issue") or "Disc game ID not read; coverage unknown."
            elif key in excluded:
                classification, reason = "EXCLUDED_FROM_PROPOSALS", excluded[key]
            else:
                classification, reason = "NON_MATCHING", "No installed local-filename, central-filename or game-ID ZIP for {}.".format(game["game_id"])
        elif game["system"] in LOCAL_CD_SYSTEMS and matching_cd_local_cheats(game):
            classification = "MATCHED_BY_LOCAL_CHEAT"
            reason = ("PASS: Valid TGFX16-CD cheat ZIP in game folder; filename matching is not required."
                      if game["system"] == "turbografx16cd" else
                      "PASS: Game-folder cheat ZIP name matches the disc filename. Central copy is not required.")
        elif game["system"] == "megacd" and game.get("local_cheats"):
            classification, reason = "LOCAL_CHEAT_NAME_MISMATCH", "NOT A PASS: Local cheat ZIP exists, but its name does not match the disc filename."
        elif game["system"] in LOCAL_CD_SYSTEMS and central_reports:
            classification, reason = "CENTRAL_CHEAT_ONLY", "NOT A PASS: Central cheat found, but no cheat ZIP in the game folder."
        elif game["system"] not in LOCAL_CD_SYSTEMS and any(r["crc_match"] for r in lookup):
            classification, reason = "MATCHED", "ROM checksum matches an installed cheat target."
        elif game["system"] in CD_SYSTEMS - LOCAL_CD_SYSTEMS and lookup:
            classification, reason = "CD_NAME_ONLY", "CD title match; checksum/game ID compatibility not verified."
        elif exact_name and game["system"] not in LOCAL_CD_SYSTEMS:
            classification, reason = "MATCHED_BY_NAME", "Titles match after removing CRC tags; CRC agreement is not required for a name match."
        elif key in excluded:
            classification, reason = "EXCLUDED_FROM_PROPOSALS", excluded[key]
        else:
            suggestions = candidates.get(key, [])
            if suggestions:
                classification = "CANDIDATE"
                reason = "Close but different filename; a matching filename is needed for MiSTer lookup."
                if game["system"] in CD_SYSTEMS:
                    reason = "Close relevant CD title; CRC is not checked. Compatibility unverified."
                for cheat in suggestions:
                    if (cheat_lookup_system(game["system"]), game["stem"].casefold()) in existing_names:
                        continue
                    folder = Path(cheat["path"]).parts[0]
                    proposals.append(dict(action="COPY_CHEAT_ZIP", source=cheat["path"],
                                          target=str(Path(folder) / (game["stem"] + ".zip"))))
            else:
                classification, reason = "NON_MATCHING", "No CRC match and no close relevant cheat title; skip."
        result = dict(game=game, classification=classification, reason=reason,
                      available_by_name=exact_name, candidates=suggestions, proposals=proposals)
        if game["system"] in LOCAL_CD_SYSTEMS:
            result["central_cheat_reports"] = central_reports
            notices = []
            if classification in {"CENTRAL_CHEAT_ONLY", "LOCAL_CHEAT_NAME_MISMATCH"}:
                notices.append(reason)
            if classification == "MATCHED_BY_LOCAL_CHEAT":
                matching_paths = {c["path"] for c in matching_cd_local_cheats(game)}
                for central in central_reports:
                    for pair in central["size_comparisons"]:
                        if (pair["local_path"] in matching_paths
                                and pair["central_size_bytes"] is not None
                                and pair["local_size_bytes"] is not None
                                and pair["central_size_bytes"] > pair["local_size_bytes"]):
                            notices.append("CENTRAL LARGER: {} ({} bytes) > {} ({} bytes); local cheat still passes.".format(
                                central["path"], pair["central_size_bytes"], pair["local_path"], pair["local_size_bytes"]))
            result["notices"] = notices
        results.append(result)
    return results


def console_folders(root):
    folders = defaultdict(list)
    for path in root.iterdir():
        if path.is_dir() and not path.is_symlink():
            folders[system_key(path.name)].append(path.name)
    return folders


def select_consoles(cheats_root, games_root):
    cheat_folders = console_folders(cheats_root)
    game_folders = console_folders(games_root)
    common = sorted(available_game_systems(cheat_folders, game_folders))
    if not common:
        print("No supported console folders found in both Cheats and games.")
        return set()
    print("\nSELECT CONSOLE TO CHECK")
    print("Installed game/cheat folders are listed; Game Gear uses the shared SMS cheat folder.")
    for number, system in enumerate(common, 1):
        print("  {}. {}  (games: {})".format(number,
              ", ".join(sorted(cheat_folders[cheat_lookup_system(system)])),
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
    parser.add_argument("--json-report", metavar="PATH",
                        help="Optional machine-readable audit report (no ROM/cheat changes)")
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
        selected = available_game_systems(console_folders(cheats_root), console_folders(games_root))
        if not selected:
            print("No supported consoles found in both trees.")
            return 0
    elif not selected:
        selected = select_consoles(cheats_root, games_root)
        if not selected:
            print("No scan performed. Existing reports are unchanged.")
            return 0
    print("Selected consoles: " + ", ".join(sorted(selected)), flush=True)
    if "gamegear" in selected:
        print("Game Gear cheat lookup: Cheats/SMS (shared SMS core).", flush=True)
    errors, skipped, excluded = [], [], []
    # Prune unselected console directories before recursive traversal.
    wanted = selected
    print("Scanning games and computing ROM CRCs (large collections may take time)...", flush=True)
    games = inventory_games(games_root, wanted, errors, skipped, args.deep, excluded)
    inventory_cd_local_cheats(games_root, games, errors, skipped, args.deep)
    inventory_psx_lookup(games_root, games, errors, args.deep)
    psx_targets = {name + ".zip" for g in games if g["system"] == "psx"
                   for name in (g["stem"], g.get("game_id", "")) if name}
    print("MiSTer cheat check {} - scanning cheats...".format(VERSION), flush=True)
    cheats = inventory_cheats(cheats_root, {cheat_lookup_system(s) for s in selected}, errors,
                              args.deep, psx_targets if "psx" in selected else None)
    rows, missing = compare(cheats, games)
    results = classify_games(cheats, games, rows)
    totals = Counter({system: 0 for system in selected})
    totals.update(g["system"] for g in games)
    counts = Counter(r["classification"] for r in results)
    by_console = Counter((r["game"]["system"], r["classification"]) for r in results)
    lines = ["MISTER CHEAT / ROM COMPARISON REPORT " + VERSION, "=" * 72,
             "Generated: " + datetime.now().astimezone().isoformat(timespec="seconds"),
             "Cheats: " + str(cheats_root), "Games: " + str(games_root),
             "Cheat archives: {} | ROM files/members checked: {}".format(len(cheats), len(games)),
             "Scan errors: {} | Skipped files: {}".format(len(errors), len(skipped)), "",
             "QUICK SUMMARY", "-" * 72]
    for system in sorted(selected):
        if not totals[system]:
            lines.append("WARNING: {}: no supported ROMs checked; cheat coverage is UNKNOWN. See skipped files/errors.".format(system))
    if "psx" in selected:
        lines.append("PSX: validated {} potentially selectable central ZIPs; other PSX ZIPs inventoried by name only.".format(
            sum(c["system"] == "psx" and c.get("validated", True) for c in cheats)))
    labels = [("MATCHED", "MATCHED (CRC)"),
              ("MATCHED_BY_GAME_ID", "MATCHED_BY_GAME_ID (PSX internal disc ID)"),
              ("MATCHED_BY_PSX_FILENAME", "MATCHED_BY_PSX_FILENAME (PSX exact disc filename)"),
              ("PSX_UNVERIFIED", "PSX_UNVERIFIED (disc ID unavailable; coverage UNKNOWN)"),
              ("MATCHED_BY_NAME", "MATCHED_BY_NAME (CRC tag ignored in title comparison)"),
              ("MATCHED_BY_LOCAL_CHEAT", "MATCHED_BY_LOCAL_CHEAT (PASS: approved CD local-cheat rule)"),
              ("LOCAL_CHEAT_NAME_MISMATCH", "LOCAL_CHEAT_NAME_MISMATCH (NOT A PASS: local ZIP name differs)"),
              ("CENTRAL_CHEAT_ONLY", "CENTRAL_CHEAT_ONLY (NOT A PASS: no game-folder cheat)"),
              ("CANDIDATE", "CANDIDATE (close but different filename; proposal only)"),
              ("NON_MATCHING", "NON_MATCHING (no installed match under this console's rules)"),
              ("EXCLUDED_FROM_PROPOSALS", "EXCLUDED_FROM_PROPOSALS (translation / Top 100 / patch / hack)"),
              ("CD_NAME_ONLY", "CD_NAME_ONLY (checksum / game ID not verified)")]
    for classification, label in labels:
        lines.append("{}: {}".format(label, counts[classification]))
    lines.append("Games passing by CRC, title, PSX game ID or approved local cheat: {}".format(
        sum(counts[c] for c in ("MATCHED", "MATCHED_BY_NAME", "MATCHED_BY_LOCAL_CHEAT", "MATCHED_BY_GAME_ID", "MATCHED_BY_PSX_FILENAME"))))
    lines.append("All candidate actions below are proposals only; ROMs and cheats are never changed.")
    if selected == {"snes"}:
        lines.append("Distinct nonmatching ROM checksums: {} (folder copies counted above)".format(
            len({r["game"]["crc"] for r in results if r["classification"] == "NON_MATCHING"})))
    lines.extend(["", "TALLY BY CONSOLE", "-" * 72,
                  "Console | Checked | " + " | ".join(category for category, _ in labels)])
    for system in sorted(totals):
        lines.append(" | ".join(str(value) for value in
                     [system, totals[system]] + [by_console[system, category] for category, _ in labels]))
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

    results.sort(key=lambda r: order(r["game"]["path"]))
    rows.sort(key=lambda row: order(row["game"]))
    for classification, label in labels:
        if classification in {"MATCHED", "MATCHED_BY_NAME", "MATCHED_BY_LOCAL_CHEAT", "MATCHED_BY_GAME_ID", "MATCHED_BY_PSX_FILENAME"}:
            continue
        lines.extend(["", label.upper(), "=" * 72])
        previous = None
        for result in results:
            if result["classification"] != classification:
                continue
            game = result["game"]
            previous = group_heading(game["path"], previous)
            lines.extend(["    {}  CRC {}".format(game["path"], game["crc"] or "not checked"),
                          "      " + result["reason"]])
            if game["system"] == "psx":
                lines.append("      PSX game ID: " + (game.get("game_id") or "UNKNOWN"))
            for cheat in result["candidates"]:
                lines.extend(["      CANDIDATE: {}  CRC {}".format(cheat["path"], cheat["crc"] or "not tagged"),
                              "        " + cheat["candidate_reason"]])
            if result["proposals"]:
                lines.append("      ALTERNATIVE COPY PROPOSALS (choose/test one; not performed):")
                for proposal in result["proposals"]:
                    lines.append("        {} -> {}".format(proposal["source"], proposal["target"]))
        if previous is None:
            lines.append("None.")
    if selected & LOCAL_CD_SYSTEMS:
        lines.extend(["", "CD GAME-FOLDER / CENTRAL CHEATS AND ZIP FILE SIZES", "=" * 72,
                      "MegaCD: local ZIP name must match disc. TGFX16-CD: local ZIP name may differ. Central is optional.",
                      "Sizes are ZIP file bytes. Equal sizes do not establish equal cheat contents."])
        for result in results:
            game = result["game"]
            if game["system"] not in LOCAL_CD_SYSTEMS or not (game.get("local_cheats") or result["central_cheat_reports"]):
                continue
            lines.append("    " + game["path"])
            for notice in result["notices"]:
                lines.append("      NOTICE: " + notice)
            for local in game.get("local_cheats", []):
                lines.append("      LOCAL: {} | {} bytes".format(local["path"], local["size_bytes"]))
            if not game.get("local_cheats"):
                lines.append("      LOCAL: NONE - NOT A PASS")
            for central in result["central_cheat_reports"]:
                lines.append("      CENTRAL (report only): {} | {} bytes | {}".format(
                    central["path"], central["size_bytes"], central["relationship"]))
                for pair in central["size_comparisons"]:
                    lines.append("        {}: local {} bytes / central {} bytes | {}".format(
                        pair["status"], pair["local_size_bytes"], pair["central_size_bytes"], pair["local_path"]))
            if not result["central_cheat_reports"]:
                lines.append("      CENTRAL: no corresponding title found (not required for a local-name pass)")
    if args.deep:
        lines.extend(["", "CHECKSUM / EXACT-NAME LOOKUP DETAILS", "=" * 72])
        previous = None
        for row in rows:
            previous = group_heading(row["game"], previous)
            lines.extend(["    " + row["game"], "      {}: {}".format(row["status"], row["cheat"]),
                          "      Raw ROM CRC: {} | Cheat CRC: {}".format(
                              row["game_crc"] or "not checked (CD name-only)", row["cheat_crc"] or "not tagged")])
            if row["system"] == "psx":
                lines.append("      PSX game ID: " + (row.get("game_id") or "UNKNOWN") + " | Disc CRC not used")
            if row["headerless_crc"]:
                lines.append("      Headerless CRC: " + row["headerless_crc"])
            if row["note"]:
                lines.append("      Note: " + row["note"])
    lines.extend(["", "ERRORS / INCOMPLETE SCANS", "=" * 72] + (errors or ["None"]))
    lines.extend(["", "EXCLUDED SUPPORT FILES (NOT GAMES)", "=" * 72]
                 + (excluded or ["None"]))
    lines.extend(["", "SKIPPED FILES (UNSUPPORTED FORMAT OR LOCATION)", "=" * 72]
                 + (skipped or ["None"]))
    report = "\n".join(lines) + "\n"
    output = Path(args.log_dir)
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / "cheat_rom_comparison_report.log"
    report_path.write_text(report, encoding="utf-8")
    if args.json_report:
        json_path = Path(args.json_report)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(dict(version=VERSION, counts=dict(counts), results=results,
                                             cheats=cheats,
                                             lookup_rows=rows, errors=errors,
                                             skipped=skipped, excluded_support=excluded), indent=2), encoding="utf-8")
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
