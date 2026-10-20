#!/usr/bin/env python3

import os
import re
import unicodedata
import xml.etree.ElementTree as ET
import difflib
from collections import defaultdict
from datetime import datetime

SCRIPT_VERSION = "v17"

# -----------------------------------------------------------------------------
# MiSTer paths
# Environment-variable overrides are included only to make testing easy.
# Normal use is simply:
#
#     python cleanup_orphan_mister_configs_v17.py
# -----------------------------------------------------------------------------
CONFIG_ROOT = os.environ.get("CONFIG_ROOT", "/media/fat/config")
MRA_ROOT = os.environ.get("MRA_ROOT", "/media/fat/_Arcade")
MAME_ROOT = os.environ.get("MAME_ROOT", "/media/fat/games/mame")
MEDIA_ROOT = os.environ.get("MEDIA_ROOT", "/media/fat")
ARCADE_RBF_ROOT = os.environ.get("RBF_ROOT", os.path.join(MRA_ROOT, "cores"))
LOG_DIR = os.environ.get("LOG_DIR", "/media/fat/Scripts/logs")

REPORT_PATH = os.path.join(LOG_DIR, "config_cleanup_report.log")
DELETE_LOG_PATH = os.path.join(LOG_DIR, "config_cleanup_deleted.log")

BUILD_SUFFIX_RE = re.compile(r"[_-]\d{6,14}$", re.IGNORECASE)
VERSION_SUFFIX_RE = re.compile(r"^(.+?)[_-]v\d+$", re.IGNORECASE)
ARCADE_PREFIX_RE = re.compile(r"^arcade[-_ ]+", re.IGNORECASE)
MISTER_SUFFIX_RE = re.compile(r"[-_ ]+mister$", re.IGNORECASE)
INPUT_MAP_RE = re.compile(r"^(.*?)_input_", re.IGNORECASE)

# Root files which are per-game/per-core configuration sidecars.
ROOT_SIDECAR_SUFFIXES = (
    "_gamma.cfg",
    "_scaler.cfg",
    "_shmask.cfg",
    "_volume.cfg",
    "_afilter.cfg",
)


def local_tag(element):
    return str(element.tag).rsplit("}", 1)[-1].lower()


def local_attr_name(name):
    return str(name).rsplit("}", 1)[-1].lower()


def split_pipe_values(value):
    for item in (value or "").split("|"):
        item = item.strip()
        if item:
            yield item


def basename_stem(value, extension=None):
    value = (value or "").strip().replace("\\", "/")
    value = value.rsplit("/", 1)[-1]
    if extension and value.lower().endswith(extension.lower()):
        value = value[: -len(extension)]
    return value.strip()


def exact_id(value):
    return unicodedata.normalize("NFKC", (value or "").strip()).casefold()


def compact_id(value):
    value = unicodedata.normalize("NFKC", (value or "").strip()).casefold()
    return re.sub(r"[^a-z0-9]+", "", value)


def canonical_title_tokens(value):
    """Canonical title tokens used for base-game comparisons."""
    value = unicodedata.normalize("NFKC", (value or "").strip()).casefold()
    if not value:
        return []
    value = re.sub(r"\be[\s_.-]*swat\b", "eswat", value)
    value = re.sub(r"\bslam\s+masters\b", "slammasters", value)
    value = re.sub(r"\bgun[.\s_-]*smoke\b", "gunsmoke", value)
    return re.findall(r"[a-z0-9]+", value)


def strict_title_key(value):
    """
    Strict normalized MRA-title key.

    Only formatting differences are ignored: case, punctuation, separators,
    and spacing. Word order and actual words/numbers remain significant.

    Examples that MATCH:
        Gun.Smoke  <-> Gun Smoke
        E-Swat     <-> ESWAT

    Examples that DO NOT MATCH:
        1944 ... (USA)    <-> 1944 ... (Europe)
        Simpsons 2 Players <-> Simpsons 4 Players
        Final Fight ... (World, hack) <-> Final Fight ...
        Chelnov - Atomic Runner <-> Atomic Runner Chelnov
    """
    tokens = canonical_title_tokens(value)
    return "".join(tokens)


def title_forms(value):
    key = strict_title_key(value)
    return {"strict:" + key} if key else set()


def classify_title_match(stem, active_titles):
    # Deletion decision is deliberately strict. Nearby/similar MRA titles are
    # written to the report for human review but NEVER affect keep/delete.
    if title_forms(stem).intersection(active_titles):
        return True, "exact normalized current MRA title/name match"
    return False, "no exact normalized current MRA title/name match"

def direct_child_text(root, wanted_tag):
    for child in list(root):
        if local_tag(child) == wanted_tag:
            text = (child.text or "").strip()
            if text:
                return text
    return ""


def element_zip_references(element):
    refs = []
    for attr_name, attr_value in element.attrib.items():
        name = local_attr_name(attr_name)
        if name == "zip" or (name.startswith("zip") and name[3:].isdigit()):
            for item in split_pipe_values(attr_value):
                refs.append(item)
    return refs


def archive_stem(value):
    value = basename_stem(value)
    if value.lower().endswith(".zip"):
        value = value[:-4]
    return exact_id(value)


def rbf_core_forms(filename_or_reference):
    """Return safe alternate names for an RBF/core reference."""
    stem = basename_stem(filename_or_reference)
    if stem.lower().endswith(".rbf"):
        stem = stem[:-4]

    pending = [stem.strip(" _-")]
    seen = set()
    forms = set()

    while pending:
        current = pending.pop(0).strip(" _-")
        key = exact_id(current)
        if not current or key in seen:
            continue
        seen.add(key)
        forms.add(key)
        forms.add(compact_id(current))

        no_build = BUILD_SUFFIX_RE.sub("", current).strip(" _-")
        if no_build != current:
            pending.append(no_build)

        no_arcade = ARCADE_PREFIX_RE.sub("", current).strip(" _-")
        if no_arcade != current:
            pending.append(no_arcade)

        no_mister = MISTER_SUFFIX_RE.sub("", current).strip(" _-")
        if no_mister != current:
            pending.append(no_mister)

    return {x for x in forms if x}


def version_base_key(key):
    """Return base game key for config names like ddp2_v1 or espgal-v1."""
    match = VERSION_SUFFIX_RE.match((key or "").strip())
    if not match:
        return ""
    return match.group(1).strip(" _-")


def arcade_like_shortname(value):
    """
    MAME/setname-style IDs are normally lowercase shortnames.

    If a root/input key has uppercase letters, spaces, or unusual punctuation and
    cannot be tied to an installed RBF, preserve it rather than risk deleting a
    non-arcade/system-core configuration.
    """
    value = (value or "").strip()
    if not value:
        return False
    if any(ch.isalpha() and ch.isupper() for ch in value):
        return False
    return re.fullmatch(r"[a-z0-9_.+\-]+", value) is not None


def scan_mras():
    active_game_ids = set()
    active_titles = set()
    active_title_strings = set()
    rbf_references = set()
    mra_count = 0

    if not os.path.isdir(MRA_ROOT):
        raise SystemExit("MRA folder not found: " + MRA_ROOT)

    arcade_rbf_abs = os.path.abspath(ARCADE_RBF_ROOT)

    for rootdir, dirs, files in os.walk(MRA_ROOT):
        dirs[:] = [
            d
            for d in dirs
            if os.path.abspath(os.path.join(rootdir, d)) != arcade_rbf_abs
        ]

        for filename in files:
            if not filename.lower().endswith(".mra"):
                continue

            mra_count += 1
            path = os.path.join(rootdir, filename)
            try:
                with open(path, "r", errors="ignore") as source:
                    xml_root = ET.fromstring(source.read())
            except Exception as exc:
                # Do not continue with destructive cleanup if the active MRA
                # inventory is incomplete.
                raise SystemExit("Unable to read MRA file {}: {}".format(path, exc))

            mra_filename_title = os.path.splitext(filename)[0]
            active_title_strings.add(mra_filename_title)
            active_titles.update(title_forms(mra_filename_title))

            name = direct_child_text(xml_root, "name")
            if name:
                active_title_strings.add(name)
                active_titles.update(title_forms(name))

            setname = direct_child_text(xml_root, "setname")
            if setname:
                active_game_ids.add(exact_id(setname))

            for element in xml_root.iter():
                if local_tag(element) == "rbf":
                    for value in split_pipe_values(element.text or ""):
                        rbf_references.update(rbf_core_forms(value))

                for zip_ref in element_zip_references(element):
                    stem = archive_stem(zip_ref)
                    if stem:
                        active_game_ids.add(stem)

    return mra_count, active_game_ids, active_titles, active_title_strings, rbf_references


def scan_mame_zips():
    if not os.path.isdir(MAME_ROOT):
        raise SystemExit("MAME ROM folder not found: " + MAME_ROOT)

    stems = set()
    count = 0
    for rootdir, dirs, files in os.walk(MAME_ROOT):
        for filename in files:
            if filename.lower().endswith(".zip"):
                count += 1
                stems.add(exact_id(os.path.splitext(filename)[0]))
    return count, stems


def rbf_scan_roots():
    """
    Scan arcade cores plus MiSTer's other underscore-prefixed core folders.
    This protects console/computer configs such as NES, SNES, Atari, etc.
    without crawling large ROM/game directories.
    """
    roots = []

    if os.path.isdir(ARCADE_RBF_ROOT):
        roots.append(ARCADE_RBF_ROOT)

    if os.path.isdir(MEDIA_ROOT):
        try:
            for name in os.listdir(MEDIA_ROOT):
                path = os.path.join(MEDIA_ROOT, name)
                if not os.path.isdir(path):
                    continue
                if not name.startswith("_"):
                    continue
                if os.path.abspath(path) == os.path.abspath(MRA_ROOT):
                    continue
                roots.append(path)
        except OSError:
            pass

    # Remove duplicate paths while preserving order.
    unique = []
    seen = set()
    for path in roots:
        key = os.path.abspath(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def scan_rbfs():
    forms = set()
    count = 0

    # Root-level RBF files, if any.
    if os.path.isdir(MEDIA_ROOT):
        try:
            for filename in os.listdir(MEDIA_ROOT):
                path = os.path.join(MEDIA_ROOT, filename)
                if os.path.isfile(path) and filename.lower().endswith(".rbf"):
                    count += 1
                    forms.update(rbf_core_forms(filename))
        except OSError:
            pass

    for root in rbf_scan_roots():
        for rootdir, dirs, files in os.walk(root):
            for filename in files:
                if filename.lower().endswith(".rbf"):
                    count += 1
                    forms.update(rbf_core_forms(filename))

    return count, forms


def root_config_key(filename):
    low = filename.lower()

    # Global/recent bookkeeping should never be treated as a game config.
    if low == "cores_recent.cfg" or "_recent_" in low or low.startswith("recent_"):
        return None

    for suffix in ROOT_SIDECAR_SUFFIXES:
        if low.endswith(suffix):
            return filename[: -len(suffix)]

    if low.endswith(".cfg"):
        return filename[:-4]

    return None


def matches_core(key, referenced_core_forms):
    forms = {exact_id(key), compact_id(key)}
    forms.discard("")
    return bool(forms.intersection(referenced_core_forms))


def keep_game_key(key, active_game_ids, referenced_core_forms):
    """
    Decide whether a root config/input-map key is still active.

    Current MRAs are the source of truth.  Installed ZIP/RBF files by
    themselves do NOT protect a config, because merged ROM archives can
    contain clone sets for which no MRA is currently installed, and an
    unreferenced RBF can likewise be stale.

    A key is kept only when a current MRA explicitly calls out the game/set
    (via setname/ZIP reference) or references the corresponding RBF core.
    """
    key_exact = exact_id(key)

    if key_exact in active_game_ids:
        return True, "exact active MRA game/set/ZIP reference"
    if matches_core(key, referenced_core_forms):
        return True, "exact RBF core referenced by a current MRA"

    # MiSTer can create/use per-game root configs with local version suffixes,
    # for example ddp2_v1.CFG or espgal-v1.CFG, while the active MRA/ZIP ID is
    # still the base game key ddp2 or espgal. Treat that suffix as an alias only
    # for matching; do not rename files and do not strip controller map suffixes
    # such as inputs/foo_input_..._v3.map.
    base_key = version_base_key(key)
    if base_key:
        if exact_id(base_key) in active_game_ids:
            return True, "version-suffixed config matches base active MRA game/set/ZIP reference"
        if matches_core(base_key, referenced_core_forms):
            return True, "version-suffixed config matches base RBF core referenced by a current MRA"

    if not arcade_like_shortname(key):
        return True, "preserved: not safely identifiable as an arcade shortname"

    return False, "no exact game/set/ZIP or RBF reference in any current MRA"

def scan_config(active_game_ids, active_titles, referenced_core_forms):
    if not os.path.isdir(CONFIG_ROOT):
        raise SystemExit("Config folder not found: " + CONFIG_ROOT)

    root_orphans = []
    input_orphans = []
    dip_orphans = []
    nvram_orphans = []
    preserved_unknown = []
    scanned = 0

    # -------------------- Root config files --------------------
    for filename in sorted(os.listdir(CONFIG_ROOT), key=str.lower):
        path = os.path.join(CONFIG_ROOT, filename)
        if not os.path.isfile(path):
            continue

        key = root_config_key(filename)
        if key is None:
            continue

        scanned += 1
        keep, reason = keep_game_key(
            key,
            active_game_ids,
            referenced_core_forms,
        )
        if not keep:
            root_orphans.append((path, reason))
        elif reason.startswith("preserved:"):
            preserved_unknown.append((path, reason))

    # -------------------- Input maps --------------------
    input_dir = os.path.join(CONFIG_ROOT, "inputs")
    if os.path.isdir(input_dir):
        for filename in sorted(os.listdir(input_dir), key=str.lower):
            path = os.path.join(input_dir, filename)
            if not os.path.isfile(path) or not filename.lower().endswith(".map"):
                continue

            scanned += 1
            match = INPUT_MAP_RE.match(filename)
            if not match:
                # Generic input_*.map mappings are intentionally global.
                continue

            key = match.group(1).strip()
            if not key:
                continue

            keep, reason = keep_game_key(
                key,
                active_game_ids,
                referenced_core_forms,
            )
            if not keep:
                input_orphans.append((path, reason))
            elif reason.startswith("preserved:"):
                preserved_unknown.append((path, reason))

    # -------------------- DIP files --------------------
    dip_dir = os.path.join(CONFIG_ROOT, "dips")
    if os.path.isdir(dip_dir):
        for filename in sorted(os.listdir(dip_dir), key=str.lower):
            path = os.path.join(dip_dir, filename)
            if not os.path.isfile(path) or not filename.lower().endswith(".dip"):
                continue

            scanned += 1
            stem = os.path.splitext(filename)[0]
            keep, reason = classify_title_match(stem, active_titles)
            if not keep:
                dip_orphans.append((path, reason))

    # -------------------- NVRAM files --------------------
    nvram_dir = os.path.join(CONFIG_ROOT, "nvram")
    if os.path.isdir(nvram_dir):
        for filename in sorted(os.listdir(nvram_dir), key=str.lower):
            path = os.path.join(nvram_dir, filename)
            if not os.path.isfile(path) or not filename.lower().endswith(".nvm"):
                continue

            scanned += 1
            stem = os.path.splitext(filename)[0]
            keep, reason = classify_title_match(stem, active_titles)
            if not keep:
                nvram_orphans.append((path, reason))

    return {
        "scanned": scanned,
        "root": root_orphans,
        "inputs": input_orphans,
        "dips": dip_orphans,
        "nvram": nvram_orphans,
        "preserved_unknown": preserved_unknown,
    }


def rel_config(path):
    return os.path.relpath(path, CONFIG_ROOT)


def nearby_ids(key, active_game_ids, installed_zip_ids, limit=4):
    key_id = exact_id(key)
    pool = sorted(set(active_game_ids) | set(installed_zip_ids))
    if not key_id or not pool:
        return []
    return difflib.get_close_matches(key_id, pool, n=limit, cutoff=0.50)


def orphan_game_key_from_path(path):
    rel = rel_config(path)
    if rel.lower().startswith("inputs" + os.sep):
        filename = os.path.basename(path)
        match = INPUT_MAP_RE.match(filename)
        return match.group(1).strip() if match else ""
    return root_config_key(os.path.basename(path)) or ""


def write_game_orphan_section(log, title, entries, active_game_ids, installed_zip_ids):
    log.write("\n" + title + "\n")
    log.write("=" * len(title) + "\n")
    if not entries:
        log.write("None\n")
        return

    for path, reason in entries:
        log.write(rel_config(path) + "\n")
        log.write("  Reason: " + reason + "\n")
        key = orphan_game_key_from_path(path)
        nearby = nearby_ids(key, active_game_ids, installed_zip_ids)
        if nearby:
            log.write("  Nearby active MRA/ZIP ID(s) - diagnostic only: " + ", ".join(nearby) + "\n")


def nearby_titles(title, active_title_strings, limit=4):
    """Diagnostic suggestions only; never used to decide deletion."""
    query = compact_id(title)
    if not query:
        return []

    by_compact = defaultdict(list)
    for candidate in sorted(active_title_strings, key=str.casefold):
        key = compact_id(candidate)
        if key:
            by_compact[key].append(candidate)

    matches = difflib.get_close_matches(query, list(by_compact), n=limit, cutoff=0.50)
    out = []
    for key in matches:
        for candidate in by_compact[key]:
            if candidate not in out:
                out.append(candidate)
                if len(out) >= limit:
                    return out
    return out


def write_title_orphan_section(log, title, entries, active_title_strings):
    log.write("\n" + title + "\n")
    log.write("=" * len(title) + "\n")
    if not entries:
        log.write("None\n")
        return

    for path, reason in entries:
        log.write(rel_config(path) + "\n")
        log.write("  Reason: " + reason + "\n")
        stem = os.path.splitext(os.path.basename(path))[0]
        nearby = nearby_titles(stem, active_title_strings)
        if nearby:
            log.write("  Nearby active MRA title(s) - diagnostic only: " + " | ".join(nearby) + "\n")


def write_section(log, title, entries):
    log.write("\n" + title + "\n")
    log.write("=" * len(title) + "\n")
    if not entries:
        log.write("None\n")
        return

    for path, reason in entries:
        log.write(rel_config(path) + "\n")
        log.write("  Reason: " + reason + "\n")


def write_report(mra_count, zip_count, rbf_count, result, active_game_ids, installed_zip_ids, active_title_strings):
    os.makedirs(LOG_DIR, exist_ok=True)

    with open(REPORT_PATH, "w", encoding="utf-8") as log:
        log.write("MISTER CONFIG CLEANUP REPORT - " + SCRIPT_VERSION + "\n")
        log.write("================================\n")
        log.write("Config folder: " + CONFIG_ROOT + "\n")
        log.write("MRA folder: " + MRA_ROOT + "\n")
        log.write("MAME ROM folder: " + MAME_ROOT + "\n")
        log.write("MRA files scanned: " + str(mra_count) + "\n")
        log.write("Installed ROM ZIP archives found: " + str(zip_count) + "\n")
        log.write("RBF files found: " + str(rbf_count) + "\n")
        log.write("Config files checked: " + str(result["scanned"]) + "\n")
        log.write("\n")
        log.write("Orphan root config files: " + str(len(result["root"])) + "\n")
        log.write("Orphan input maps: " + str(len(result["inputs"])) + "\n")
        log.write("Orphan DIP files (no exact MRA title/name): " + str(len(result["dips"])) + "\n")
        log.write("Orphan NVRAM files (no exact MRA title/name): " + str(len(result["nvram"])) + "\n")
        log.write("Matching: Files matching current MRA references are protected; similar names do not count as matches.\n")

        write_game_orphan_section(
            log,
            "ROOT CONFIG FILES - NO CORRESPONDING CURRENT MRA REFERENCE",
            result["root"],
            active_game_ids,
            installed_zip_ids,
        )
        write_game_orphan_section(
            log,
            "INPUT MAPS - NO CORRESPONDING CURRENT MRA REFERENCE",
            result["inputs"],
            active_game_ids,
            installed_zip_ids,
        )
        write_title_orphan_section(
            log,
            "DIP FILES - NO EXACT CORRESPONDING MRA TITLE/NAME",
            result["dips"],
            active_title_strings,
        )
        write_title_orphan_section(
            log,
            "NVRAM FILES - NO EXACT CORRESPONDING MRA TITLE/NAME",
            result["nvram"],
            active_title_strings,
        )
        # These are intentionally not candidates. Listing them makes it clear
        # why an unmatched mixed-case/system-looking config was not deleted.
        write_section(
            log,
            "UNMATCHED FILES PRESERVED FOR SAFETY",
            result["preserved_unknown"],
        )


def delete_files(entries, category):
    deleted = []
    failures = []

    for path, reason in entries:
        try:
            os.remove(path)
            deleted.append(path)
        except OSError as exc:
            failures.append((path, str(exc)))

    if deleted or failures:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(DELETE_LOG_PATH, "a", encoding="utf-8") as log:
            log.write("\n{} - {}\n".format(datetime.now().isoformat(timespec="seconds"), category))
            for path in deleted:
                log.write("DELETED: " + path + "\n")
            for path, error in failures:
                log.write("FAILED: {} - {}\n".format(path, error))

    return len(deleted), len(failures)


def main():
    # Deletion log is for this run only. Remove any stale log from a previous run.
    try:
        os.remove(DELETE_LOG_PATH)
    except FileNotFoundError:
        pass
    except OSError as exc:
        print("WARNING: Unable to remove old deletion log {}: {}".format(
            DELETE_LOG_PATH, exc
        ))

    mra_count, active_game_ids, active_titles, active_title_strings, referenced_core_forms = scan_mras()
    zip_count, installed_zip_ids = scan_mame_zips()
    rbf_count, installed_core_forms = scan_rbfs()

    result = scan_config(active_game_ids, active_titles, referenced_core_forms)

    write_report(mra_count, zip_count, rbf_count, result, active_game_ids, installed_zip_ids, active_title_strings)

    print()
    print("=" * 72)
    print(" MISTER CONFIG CLEANUP REPORT ")
    print("=" * 72)
    try:
        with open(REPORT_PATH, "r", encoding="utf-8") as report:
            report_text = report.read().rstrip()

        # Keep this safety/debug section in the log file, but omit it from the
        # terminal display to keep interactive output concise.
        terminal_report = re.sub(
            r"\nUNMATCHED FILES PRESERVED FOR SAFETY\n"
            r"=+\n.*\Z",
            "",
            report_text,
            flags=re.DOTALL,
        ).rstrip()

        if terminal_report:
            print(terminal_report)
    except OSError as exc:
        print("WARNING: Unable to display report in terminal:", exc)
    print("=" * 72)
    print("Report saved to:")
    print(REPORT_PATH)
    print("=" * 72)

    root_configs = result["root"]
    input_maps = result["inputs"]
    dip_files = result["dips"]
    nvram_files = result["nvram"]

    deleted_root = failed_root = 0
    deleted_maps = failed_maps = 0
    deleted_dips = failed_dips = 0
    deleted_nvram = failed_nvram = 0

    if root_configs:
        print()
        print("Type DELETE CONFIGS to delete {} orphan root config files.".format(len(root_configs)))
        answer = input("> ").strip()
        if answer == "DELETE CONFIGS":
            deleted_root, failed_root = delete_files(root_configs, "ROOT CONFIG FILES")
        else:
            print("Root config deletion cancelled.")

    if input_maps:
        print()
        print("Type DELETE MAPS to delete {} orphan input maps.".format(len(input_maps)))
        answer = input("> ").strip()
        if answer == "DELETE MAPS":
            deleted_maps, failed_maps = delete_files(input_maps, "INPUT MAPS")
        else:
            print("Input map deletion cancelled.")

    if dip_files:
        print()
        print("Type DELETE DIPS to delete {} orphan DIP files.".format(len(dip_files)))
        answer = input("> ").strip()
        if answer == "DELETE DIPS":
            deleted_dips, failed_dips = delete_files(dip_files, "DIP FILES")
        else:
            print("DIP deletion cancelled.")

    # NVRAM is separated because it may contain saved game/state data.
    if nvram_files:
        print()
        print("Type DELETE NVRAM to delete {} orphan NVRAM files.".format(len(nvram_files)))
        answer = input("> ").strip()
        if answer == "DELETE NVRAM":
            deleted_nvram, failed_nvram = delete_files(nvram_files, "NVRAM FILES")
        else:
            print("NVRAM deletion cancelled.")

    print()
    print("Root config files deleted:", deleted_root)
    print("Root config deletion failures:", failed_root)
    print("Input maps deleted:", deleted_maps)
    print("Input map deletion failures:", failed_maps)
    print("DIP files deleted:", deleted_dips)
    print("DIP deletion failures:", failed_dips)
    print("NVRAM files deleted:", deleted_nvram)
    print("NVRAM deletion failures:", failed_nvram)


if __name__ == "__main__":
    main()
