#!/usr/bin/env python3

import argparse
import difflib
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime

VERSION = "v52"

# Normal MiSTer paths. Environment-variable overrides are useful for testing.
MRA_ROOT = os.environ.get("MRA_ROOT", "/media/fat/_Arcade")
MAME_ROOT = os.environ.get("MAME_ROOT", "/media/fat/games/mame")
RBF_ROOT = os.environ.get("RBF_ROOT", os.path.join(MRA_ROOT, "cores"))
LOG_DIR = os.environ.get("LOG_DIR", "/media/fat/Scripts/logs")

COMBINED_REPORT_PATH = os.path.join(LOG_DIR, "arcade_cleanup_report.log")
ZIP_DELETE_LOG_PATH = os.path.join(LOG_DIR, "orphan_mame_zips_deleted.log")
RBF_DELETE_LOG_PATH = os.path.join(LOG_DIR, "orphan_arcade_rbfs_deleted.log")

# A build stamp is recognized only when it is:
#   * at the end of the stem,
#   * preceded by an underscore or hyphen, and
#   * 6 through 14 digits long, optionally followed by one revision letter.
# Same-date revisions sort after the original build: no letter < a < b < ... z.
#
# The full unstripped name is always tested too. Therefore a legitimate core
# whose actual name ends in digits is still retained when its MRA uses that
# complete name.
BUILD_SUFFIX_RE = re.compile(r"[_-](\d{6,14})([a-z]?)$", re.IGNORECASE)
ARCADE_PREFIX_RE = re.compile(r"^arcade[-_ ]+", re.IGNORECASE)
MISTER_SUFFIX_RE = re.compile(r"[-_ ]+mister$", re.IGNORECASE)
CRC_RE = re.compile(r"^[0-9a-f]{8}$", re.IGNORECASE)


# ANSI colors affect only the interactive console; saved reports stay plain text.
RED = "\033[1;31m"
GREEN = "\033[1;32m"
RESET = "\033[0m"


def terminal_colors_enabled():
    return (sys.stdout.isatty()
            and "NO_COLOR" not in os.environ
            and os.environ.get("TERM", "") != "dumb")


def missing_color(value, enabled):
    return RED + str(value) + RESET if enabled else str(value)


def safe_color(value, enabled):
    """Mark verified cleanup candidates in green on interactive consoles."""
    return GREEN + str(value) + RESET if enabled else str(value)


def print_colored_report(report_text, missing_rom_mras, orphan_mras,
                         colors=None):
    """Color missing files red and safe deletion candidates green, console only."""
    if colors is None:
        colors = terminal_colors_enabled()

    missing_rom_names = {item["mra"] for item in missing_rom_mras}
    orphan_mra_names = {mra for mra, _reference in orphan_mras}
    # Group ordering exactly matches the existing report-writing loop.
    group_states = iter(
        result["satisfied"]
        for item in missing_rom_mras
        for recipe in item["recipes"]
        for _group, result in recipe["groups"]
    )
    section = None
    last_group_missing = False
    problem_counts = (
        "MRA files with required ROM data not found:",
        "RBF names referenced by MRAs but not found in core folder:",
        "Orphan MRA files (no corresponding RBF):",
    )
    safe_delete_counts = (
        "Orphan ROM ZIP archives:",
        "Duplicate RBF files (older/extra builds):",
        "Orphan RBFs:",
        "RBF files safe to delete:",
    )

    for line in report_text.rstrip().splitlines():
        if line == "ORPHAN ROM ZIP ARCHIVES - NOT USED BY ANY MRA":
            section = "orphan_zip"
        elif line == "MRA ROM REFERENCE RESULTS":
            section = None
        elif line == "MRA FILES - REQUIRED ROM DATA NOT FOUND":
            section = "rom"
        elif line == "PARENT ZIP MATCH RESULTS":
            section = None
        elif line == "RBF SUMMARY":
            section = None
        elif line == "ORPHAN RBF FILES - UNREFERENCED":
            section = "orphan_rbf"
        elif line == "DUPLICATE RBF FILES - OLDER OR EXTRA BUILDS":
            section = "duplicate_rbf"
        elif line == "ORPHAN MRA FILES - NO CORRESPONDING RBF":
            section = "rbf"

        rendered = line
        if section == "orphan_zip":
            if line.lower().endswith(".zip"):
                rendered = safe_color(line, colors)
        elif section == "rom":
            if line in missing_rom_names:
                rendered = missing_color(line, colors)
            elif line.startswith("    Listed ROM ZIP(s): "):
                last_group_missing = not next(group_states, True)
                if last_group_missing:
                    prefix = "    Listed ROM ZIP(s): "
                    rendered = prefix + missing_color(line[len(prefix):], colors)
            elif line.startswith("    Result: ") and last_group_missing:
                prefix = "    Result: "
                rendered = prefix + missing_color(line[len(prefix):], colors)
        elif section == "orphan_rbf":
            if line.lower().endswith(".rbf"):
                rendered = safe_color(line, colors)
        elif section == "duplicate_rbf":
            if line.startswith("  Duplicate: "):
                prefix = "  Duplicate: "
                rendered = prefix + safe_color(line[len(prefix):], colors)
        elif section == "rbf":
            if line in orphan_mra_names:
                rendered = missing_color(line, colors)
            elif line.startswith("  Referenced RBF not found: "):
                prefix = "  Referenced RBF not found: "
                rendered = prefix + missing_color(line[len(prefix):], colors)

        if (any(line.startswith(prefix) for prefix in problem_counts)
                or any(line.startswith(prefix) for prefix in safe_delete_counts)):
            label, _, value = line.rpartition(": ")
            if value.isdigit() and int(value) > 0:
                color_fn = (safe_color if any(line.startswith(prefix)
                              for prefix in safe_delete_counts) else missing_color)
                rendered = label + ": " + color_fn(value, colors)
        print(rendered)


def local_tag(element):
    """Return an XML tag without its namespace, in lowercase."""
    return str(element.tag).rsplit("}", 1)[-1].lower()


def local_attr_name(name):
    """Return an XML attribute name without its namespace, in lowercase."""
    return str(name).rsplit("}", 1)[-1].lower()


def split_pipe_values(value):
    """Yield non-empty values from a single value or pipe-separated list."""
    for item in (value or "").split("|"):
        item = item.strip()
        if item:
            yield item


def normalize_zip_reference(value):
    """Normalize an MRA ZIP reference for case-insensitive path matching."""
    return (value or "").strip().replace("\\", "/").casefold()


def zip_reference_keys(value):
    """Return relative-path and basename keys for one ZIP reference."""
    normalized = normalize_zip_reference(value)
    if not normalized:
        return set()
    return {normalized, os.path.basename(normalized)}


def element_zip_references(element):
    """Return ZIP references from zip, zip1, zip2, etc. attributes."""
    references = []
    for attr_name, attr_value in element.attrib.items():
        name = local_attr_name(attr_name)
        if name == "zip" or (name.startswith("zip") and name[3:].isdigit()):
            for zip_name in split_pipe_values(attr_value):
                normalized = normalize_zip_reference(zip_name)
                if normalized and normalized not in references:
                    references.append(normalized)
    return references


def normalize_crc(value):
    """Return an eight-digit lowercase CRC32 string, or None."""
    value = (value or "").strip().lower()
    if value.startswith("0x"):
        value = value[2:]
    if CRC_RE.fullmatch(value):
        return value
    return None


def normalize_member_name(value):
    """Normalize a ROM member filename for case-insensitive matching."""
    value = (value or "").strip().replace("\\", "/").casefold()
    return os.path.basename(value)


def filename_stem(value, extension=None):
    """Return the basename stem from an MRA value or installed filename."""
    value = (value or "").strip().replace("\\", "/")
    value = value.rsplit("/", 1)[-1].strip()

    if extension and value.lower().endswith(extension.lower()):
        value = value[: -len(extension)]
    elif value.lower().endswith(".rbf"):
        value = value[:-4]

    return value.strip()


def normalized_name(value):
    """Compare core names case-insensitively while ignoring punctuation."""
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def core_name_forms(value, installed_filename=False):
    """
    Return deterministic exact-match forms for one RBF name.

    Each optional transformation has a cost. Matching later chooses the lowest
    cost so a specific reference such as "zerowing_mister" prefers the matching
    mister core instead of also claiming a more loosely related "zerowing" core.
    """
    stem = filename_stem(value, ".rbf" if installed_filename else None)
    pending = [(stem, "full name", 0)]
    best_stem_cost = {}
    forms = {}

    while pending:
        current, reason, cost = pending.pop(0)
        current = current.strip(" _-")
        stem_key = current.casefold()
        if not current or cost >= best_stem_cost.get(stem_key, 10**9):
            continue

        best_stem_cost[stem_key] = cost
        key = normalized_name(current)
        previous = forms.get(key)
        if key and (previous is None or cost < previous[2]):
            forms[key] = (current, reason, cost)

        without_build = BUILD_SUFFIX_RE.sub("", current).strip(" _-")
        if without_build != current:
            pending.append((without_build, reason + "; build stamp removed", cost + 1))

        without_prefix = ARCADE_PREFIX_RE.sub("", current).strip(" _-")
        if without_prefix != current:
            pending.append((without_prefix, reason + "; Arcade prefix removed", cost + 2))

        without_mister = MISTER_SUFFIX_RE.sub("", current).strip(" _-")
        if without_mister != current:
            pending.append(
                (
                    without_mister,
                    reason + "; optional mister suffix removed",
                    cost + 2,
                )
            )

    return forms


def compare_core_names(reference, installed_filename):
    """Return the lowest-cost deterministic match description, or None."""
    reference_forms = core_name_forms(reference, installed_filename=False)
    installed_forms = core_name_forms(installed_filename, installed_filename=True)

    shared = set(reference_forms).intersection(installed_forms)
    if not shared:
        return None

    choices = []
    for key in shared:
        ref_form, ref_reason, ref_cost = reference_forms[key]
        rbf_form, rbf_reason, rbf_cost = installed_forms[key]
        choices.append(
            (
                ref_cost + rbf_cost,
                ref_cost,
                rbf_cost,
                key,
                ref_form,
                ref_reason,
                rbf_form,
                rbf_reason,
            )
        )

    (
        total_cost,
        ref_cost,
        rbf_cost,
        key,
        ref_form,
        ref_reason,
        rbf_form,
        rbf_reason,
    ) = min(choices)

    return {
        "key": key,
        "reference_form": ref_form,
        "reference_reason": ref_reason,
        "reference_cost": ref_cost,
        "rbf_form": rbf_form,
        "rbf_reason": rbf_reason,
        "rbf_cost": rbf_cost,
        "total_cost": total_cost,
    }


def rbf_build_stamp(filename):
    """Return the numeric date/timestamp, ignoring any revision letter, or -1."""
    stem = filename_stem(filename, ".rbf")
    match = BUILD_SUFFIX_RE.search(stem)
    return int(match.group(1)) if match else -1


def rbf_build_revision(filename):
    """Return the same-date revision rank: original=0, a=1, ..., z=26."""
    match = BUILD_SUFFIX_RE.search(filename_stem(filename, ".rbf"))
    if not match or not match.group(2):
        return 0
    return ord(match.group(2).lower()) - ord("a") + 1


def rbf_duplicate_key(filename):
    """Group timestamped builds of the same exact core name."""
    stem = filename_stem(filename, ".rbf")
    stem = BUILD_SUFFIX_RE.sub("", stem).strip(" _-")
    return normalized_name(stem)


def choose_preferred_rbf(reference, candidates):
    """Choose one best RBF; newest build wins only when match quality ties."""
    minimum_cost = min(result["total_cost"] for _, result in candidates)
    best = [item for item in candidates if item[1]["total_cost"] == minimum_cost]

    reference_full = normalized_name(filename_stem(reference, ".rbf"))

    def preference(item):
        rel, result = item
        installed_full = normalized_name(filename_stem(os.path.basename(rel), ".rbf"))
        exact_full = installed_full == reference_full
        return (
            0 if exact_full else 1,
            -rbf_build_stamp(rel),
            -rbf_build_revision(rel),
            rel.casefold(),
        )

    return min(best, key=preference), best


def parse_mra_rom_recipes(root):
    """
    Return one ROM recipe containing every external ZIP source used by an MRA.

    MiSTer MRAs commonly place ZIP references on ROM indexes other than zero.
    Every <rom> element is therefore scanned. ZIP names separated by "|" are
    alternatives for that source group, while separate ROM source groups are
    all required by the MRA.
    """
    grouped_parts = {}
    group_order = []

    def ensure_group(zip_names):
        key = tuple(zip_names)
        if key and key not in grouped_parts:
            grouped_parts[key] = []
            group_order.append(key)
        return key

    for rom in root.iter():
        if local_tag(rom) != "rom":
            continue

        rom_zips = element_zip_references(rom)
        default_zip_used_by_external_part = False

        for part in rom.iter():
            if part is rom or local_tag(part) != "part":
                continue

            part_name = normalize_member_name(part.attrib.get("name", ""))
            part_crc = normalize_crc(part.attrib.get("crc", ""))

            # A part with neither a filename nor CRC is embedded data and does
            # not require an external ROM ZIP archive.
            if not part_name and not part_crc:
                continue

            explicit_part_zips = element_zip_references(part)
            part_zips = explicit_part_zips or rom_zips

            # An external raw file with no ZIP source is outside the MAME ZIP
            # inventory and is not part of this script's ZIP checks.
            if not part_zips:
                continue

            if not explicit_part_zips and rom_zips:
                default_zip_used_by_external_part = True

            key = ensure_group(part_zips)
            requirement = {"name": part_name or None, "crc": part_crc}
            if requirement not in grouped_parts[key]:
                grouped_parts[key].append(requirement)

        # Some ROM entries name a ZIP but contain only embedded/repeated data.
        # The explicitly named ZIP still counts as a source used by the MRA.
        if rom_zips and not default_zip_used_by_external_part:
            ensure_group(rom_zips)

    groups = [
        {"zip_names": list(key), "requirements": grouped_parts[key]}
        for key in group_order
    ]

    # The evaluator supports alternative recipes, but a normal MRA has one
    # recipe made up of all ZIP source groups found across all ROM indexes.
    return [groups] if groups else []

def build_archive_name_index(actual_zips):
    """Index installed ZIP archives by relative path and basename."""
    archive_key_index = defaultdict(set)

    for rel in actual_zips:
        for key in zip_reference_keys(rel):
            archive_key_index[key].add(rel)

    return archive_key_index


class TargetedZipInspector:
    """Inspect only likely related ZIP candidates, never the full folder."""

    MAX_CANDIDATES_PER_REQUEST = 12

    def __init__(self, actual_zips):
        self.actual_zips = list(actual_zips)
        self.by_stem = defaultdict(set)
        self.cache = {}

        for rel in self.actual_zips:
            stem = os.path.splitext(os.path.basename(rel))[0].casefold()
            if stem:
                self.by_stem[stem].add(rel)

    @staticmethod
    def common_prefix_length(left, right):
        """Return the number of identical leading characters."""
        count = 0
        for left_char, right_char in zip(left, right):
            if left_char != right_char:
                break
            count += 1
        return count

    def plausible_parent_archives(self, listed_zip_names):
        """
        Return a small set of likely related installed ZIPs.

        Direct prefix relationships are preferred, such as robocop2.zip for
        robocop2u.zip. A similarity fallback also handles MAME short names
        which differ internally, such as nbahangt.zip for nbamht.zip. Every
        candidate must still contain all ROM parts required by the MRA before
        it is accepted. Unrelated archives such as 1941.zip are not opened.
        """
        best_score_by_rel = {}

        for listed in listed_zip_names:
            requested = os.path.splitext(os.path.basename(listed))[0].casefold()
            if len(requested) < 3:
                continue

            request_candidates = []

            for installed_stem, rels in self.by_stem.items():
                if installed_stem == requested or len(installed_stem) < 3:
                    continue

                prefix_length = self.common_prefix_length(requested, installed_stem)
                length_difference = abs(len(requested) - len(installed_stem))
                similarity = difflib.SequenceMatcher(
                    None, requested, installed_stem
                ).ratio()

                direct_prefix = (
                    requested.startswith(installed_stem)
                    or installed_stem.startswith(requested)
                )

                if direct_prefix:
                    if length_difference > 8:
                        continue
                    category = 0
                else:
                    # MAME parent and clone short names sometimes share only a
                    # short franchise prefix and differ in the middle, such as
                    # nbamht -> nbahangt. Keep this fallback deliberately
                    # narrow, then verify every ROM part inside the candidate.
                    if prefix_length < 3:
                        continue
                    if similarity < 0.60:
                        continue
                    if length_difference > 6:
                        continue
                    category = 1

                for rel in rels:
                    score = (
                        category,
                        -similarity,
                        -prefix_length,
                        length_difference,
                        rel.casefold(),
                    )
                    request_candidates.append((score, rel))

            request_candidates.sort(key=lambda item: item[0])
            for score, rel in request_candidates[: self.MAX_CANDIDATES_PER_REQUEST]:
                previous = best_score_by_rel.get(rel)
                if previous is None or score < previous:
                    best_score_by_rel[rel] = score

        return [
            rel
            for rel, score in sorted(
                best_score_by_rel.items(), key=lambda item: item[1]
            )
        ]

    def archive_contents(self, rel):
        """Read one ZIP central directory and cache its filenames and CRCs."""
        if rel in self.cache:
            return self.cache[rel]

        full = os.path.join(MAME_ROOT, rel)
        names = set()
        crcs = set()
        name_crcs = defaultdict(set)

        try:
            with zipfile.ZipFile(full, "r") as archive:
                for info in archive.infolist():
                    if info.is_dir():
                        continue

                    member = info.filename.replace("\\", "/").casefold()
                    names.add(member)
                    names.add(os.path.basename(member))
                    entry_crc = "{:08x}".format(info.CRC & 0xFFFFFFFF)
                    crcs.add(entry_crc)
                    name_crcs[member].add(entry_crc)
                    name_crcs[os.path.basename(member)].add(entry_crc)
        except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
            raise SystemExit(
                "Unable to read ROM ZIP archive {}: {}".format(full, exc)
            )

        self.cache[rel] = {"names": names, "crcs": crcs, "name_crcs": name_crcs}
        return self.cache[rel]

    def archives_match_requirement(self, archives, requirement):
        """Match by filename across listed ZIPs, then by CRC if needed."""
        name = requirement.get("name")
        crc = requirement.get("crc")
        if name and any(name in self.archive_contents(rel)["names"] for rel in archives):
            return True
        if crc and any(crc in self.archive_contents(rel)["crcs"] for rel in archives):
            return True
        return False

    def deep_requirement_status(self, archives, requirement):
        """Check each part against its MRA CRC, allowing renamed ROM members."""
        name = requirement.get("name")
        crc = requirement.get("crc")
        contents = [self.archive_contents(rel) for rel in archives]
        if crc:
            if any(crc in item["crcs"] for item in contents):
                return None
            actual = sorted({value for item in contents
                             for value in item["name_crcs"].get(name, ())}) if name else []
            if actual:
                return "{} (expected CRC {}, found CRC {})".format(
                    name, crc, ", ".join(actual))
            return "{} (expected CRC {}, not found)".format(name or "ROM part", crc)
        if name and any(name in item["names"] for item in contents):
            return None
        return "{} (no MRA CRC provided; filename not found)".format(name or "ROM part")

    def archive_matches_requirement(self, rel, requirement):
        """Return True when one candidate archive contains the required part."""
        contents = self.archive_contents(rel)

        if requirement.get("crc") and requirement["crc"] in contents["crcs"]:
            return True
        if requirement.get("name") and requirement["name"] in contents["names"]:
            return True
        return False


def evaluate_zip_group(group, archive_key_index, content_inspector, deep=False):
    """
    Determine whether one MRA ZIP source group is satisfied.

    Preference order:
      1. For pipe-separated listed ZIPs, verify ROM member name then CRC.
         For a single listed ZIP, accept an existing archive immediately.
      2. If none exists, inspect only a small set of likely related ZIP names.
      3. Accept a candidate only when it contains every required ROM part.
      4. Never walk unrelated ZIPs merely to find a possible content match.
    """
    explicit_archives = set()
    for zip_name in group["zip_names"]:
        for key in zip_reference_keys(zip_name):
            explicit_archives.update(archive_key_index.get(key, set()))

    # Normal mode retains v47 behavior. Deep mode checks the MRA CRC for
    # every external ROM part, including parts in single-ZIP source groups.
    if explicit_archives and (deep or len(group["zip_names"]) > 1):
        missing = []
        for requirement in group["requirements"]:
            name = requirement.get("name")
            crc = requirement.get("crc")
            if not name and not crc:
                continue
            if deep:
                issue = content_inspector.deep_requirement_status(
                    explicit_archives, requirement)
                if issue:
                    missing.append(issue)
            elif not content_inspector.archives_match_requirement(
                explicit_archives, requirement
            ):
                missing.append(name or "CRC " + crc)
        if missing:
            return {
                "satisfied": False,
                "used": set(explicit_archives),
                "content_archives": set(),
                "explicit_archives": explicit_archives,
                "reason": ("CRC mismatch / missing ROM member(s): " if deep else
                           "missing ROM member(s): ") + ", ".join(missing),
            }
        return {
            "satisfied": True,
            "used": set(explicit_archives),
            "content_archives": set(),
            "explicit_archives": explicit_archives,
            "reason": ("all required ROM parts verified against MRA CRCs" if deep else
                       "all required ROM parts found by filename or CRC across listed ZIPs"),
        }

    if explicit_archives:
        return {
            "satisfied": True,
            "used": set(explicit_archives),
            "content_archives": set(),
            "explicit_archives": explicit_archives,
            "reason": "listed archive found",
        }

    requirements = group["requirements"]
    if not requirements:
        return {
            "satisfied": False,
            "used": set(),
            "content_archives": set(),
            "explicit_archives": set(),
            "reason": "listed archive not found; no ROM parts available to verify a parent ZIP",
        }

    parent_candidates = content_inspector.plausible_parent_archives(
        group["zip_names"]
    )
    if not parent_candidates:
        return {
            "satisfied": False,
            "used": set(),
            "content_archives": set(),
            "explicit_archives": set(),
            "reason": "listed archive not found; no likely related parent ZIP filename found",
        }

    complete_archives = set()
    for rel in parent_candidates:
        if all(
            (content_inspector.deep_requirement_status([rel], requirement) is None
             if deep else content_inspector.archive_matches_requirement(rel, requirement))
            for requirement in requirements
        ):
            complete_archives.add(rel)

    if complete_archives:
        return {
            "satisfied": True,
            "used": complete_archives,
            "content_archives": complete_archives,
            "explicit_archives": set(),
            "reason": "listed archive not found; related parent ZIP verified by contents",
        }

    return {
        "satisfied": False,
        "used": set(),
        "content_archives": set(),
        "explicit_archives": set(),
        "reason": "listed archive not found; likely related parent ZIP candidates did not contain all required ROM parts",
    }

def delete_files(root, relative_paths, label):
    """Delete relative paths beneath root and return successes and failures."""
    deleted = []
    failed = []

    for rel in relative_paths:
        full = os.path.join(root, rel)
        try:
            os.remove(full)
            deleted.append(rel)
            print(safe_color("DELETED {}: {}".format(label, rel),
                             terminal_colors_enabled()))
        except Exception as exc:
            failed.append((rel, str(exc)))
            print(missing_color("FAILED {}: {} : {}".format(label, rel, exc),
                                terminal_colors_enabled()))

    return deleted, failed


def write_delete_log(path, heading, root, deleted, failed):
    """Write the deletion results for this run only."""
    with open(path, "w") as log:
        log.write("\n")
        log.write("Delete run: " + datetime.now().isoformat(timespec="seconds") + "\n")
        log.write(heading + ": " + root + "\n")
        log.write("Deleted files: " + str(len(deleted)) + "\n")
        log.write("Failed files: " + str(len(failed)) + "\n\n")

        for rel in deleted:
            log.write("DELETED: " + rel + "\n")

        for rel, err in failed:
            log.write("FAILED: " + rel + " : " + err + "\n")


def main():
    parser = argparse.ArgumentParser(description="Find orphan arcade ROM ZIPs and RBFs.")
    parser.add_argument("--version", action="version", version="%(prog)s " + VERSION)
    parser.add_argument("-deep", "--deep", action="store_true",
                        help="Check every ROM part against its MRA CRC, including single-ZIP MRAs.")
    args = parser.parse_args()
    # Deletion reports are per-run only. Remove stale reports from previous runs.
    os.makedirs(LOG_DIR, exist_ok=True)
    for delete_log_path in (ZIP_DELETE_LOG_PATH, RBF_DELETE_LOG_PATH):
        try:
            os.remove(delete_log_path)
        except FileNotFoundError:
            pass
        except OSError as exc:
            print("WARNING: Unable to remove old deletion report {}: {}".format(
                delete_log_path, exc
            ))

    for required_path, description in (
        (MRA_ROOT, "MRA folder"),
        (MAME_ROOT, "MAME ROM folder"),
        (RBF_ROOT, "Arcade core folder"),
    ):
        if not os.path.isdir(required_path):
            raise SystemExit(description + " not found: " + required_path)

    mra_rom_recipes = {}

    # Key normal MRA RBF references case-insensitively so values such as
    # "tecmo" and "Tecmo" count as the same core reference. Keep the first
    # spelling for readable reports and collect every MRA which uses it.
    rbf_references = defaultdict(list)
    rbf_reference_display = {}

    # Supplemental launcher references are intentionally used only to protect
    # an installed RBF from being classified as orphaned. They do not affect
    # the normal MRA counts, missing-reference reports, or ROM ZIP checks.
    supplemental_rbf_references = defaultdict(list)
    supplemental_rbf_reference_display = {}
    mra_count = 0

    # Scan MRAs normally. A supplemental .mgl launcher may also claim an RBF,
    # but it remains invisible to the normal report/summary accounting.
    for rootdir, dirs, files in os.walk(MRA_ROOT):
        # Never descend into the installed core directory.
        dirs[:] = [
            directory
            for directory in dirs
            if os.path.abspath(os.path.join(rootdir, directory))
            != os.path.abspath(RBF_ROOT)
        ]

        for filename in files:
            lower_filename = filename.lower()
            is_mra = lower_filename.endswith(".mra")
            is_mgl = lower_filename.endswith(".mgl")
            if not (is_mra or is_mgl):
                continue

            if is_mra:
                mra_count += 1

            launcher_path = os.path.join(rootdir, filename)
            launcher_rel = os.path.relpath(launcher_path, MRA_ROOT)

            try:
                with open(launcher_path, "r", errors="ignore") as source:
                    root = ET.fromstring(source.read())
            except Exception as exc:
                raise SystemExit(
                    "Unable to read arcade launcher file {}: {}".format(
                        launcher_path, exc
                    )
                )

            if is_mra:
                recipes = parse_mra_rom_recipes(root)
                if recipes:
                    mra_rom_recipes[launcher_rel] = recipes

            for element in root.iter():
                if local_tag(element) != "rbf":
                    continue

                for rbf_value in split_pipe_values(element.text or ""):
                    cleaned = filename_stem(rbf_value, ".rbf")
                    if cleaned:
                        reference_key = cleaned.casefold()
                        if is_mra:
                            rbf_reference_display.setdefault(reference_key, cleaned)
                            rbf_references[reference_key].append(launcher_rel)
                        else:
                            supplemental_rbf_reference_display.setdefault(reference_key, cleaned)
                            supplemental_rbf_references[reference_key].append(launcher_rel)

    # Inventory installed ROM ZIP archives.
    actual_zips = []
    for rootdir, dirs, files in os.walk(MAME_ROOT):
        for filename in files:
            if filename.lower().endswith(".zip"):
                full = os.path.join(rootdir, filename)
                actual_zips.append(os.path.relpath(full, MAME_ROOT))
    actual_zips.sort(key=str.lower)

    archive_key_index = build_archive_name_index(actual_zips)
    content_inspector = TargetedZipInspector(actual_zips)

    used_zips = set()
    missing_rom_mras = []
    content_name_matches = []

    for mra_file in sorted(mra_rom_recipes, key=str.lower):
        recipes = mra_rom_recipes[mra_file]
        recipe_results = []

        for recipe_number, groups in enumerate(recipes, start=1):
            group_results = []
            recipe_satisfied = True

            # Pipe-separated source groups are verified by ROM
            # member filename first, then CRC, across the listed archives.
            for group in groups:
                result = evaluate_zip_group(
                    group,
                    archive_key_index,
                    content_inspector,
                    deep=args.deep,
                )
                group_results.append((group, result))
                if not result["satisfied"]:
                    recipe_satisfied = False

            recipe_results.append(
                {
                    "number": recipe_number,
                    "satisfied": recipe_satisfied,
                    "groups": group_results,
                }
            )

        satisfied_recipes = [result for result in recipe_results if result["satisfied"]]

        if satisfied_recipes:
            for recipe in satisfied_recipes:
                for group, result in recipe["groups"]:
                    used_zips.update(result["used"])

                    explicitly_named = set(result["explicit_archives"])
                    differently_named = sorted(
                        result["content_archives"] - explicitly_named,
                        key=str.lower,
                    )
                    if differently_named:
                        content_name_matches.append(
                            {
                                "mra": mra_file,
                                "listed": list(group["zip_names"]),
                                "archives": differently_named,
                                "part_count": len(group["requirements"]),
                            }
                        )
        else:
            # Protect ZIPs referenced by incomplete recipes from orphan classification.
            for recipe in recipe_results:
                for group, result in recipe["groups"]:
                    used_zips.update(result["explicit_archives"])
                    used_zips.update(result["content_archives"])
            missing_rom_mras.append(
                {"mra": mra_file, "recipes": recipe_results}
            )

    # A ZIP is orphaned when it is not used by any satisfied MRA recipe.
    orphan_zips = sorted(set(actual_zips) - used_zips, key=str.lower)

    # Inventory installed arcade RBFs.
    installed_rbfs = []
    for rootdir, dirs, files in os.walk(RBF_ROOT):
        for filename in files:
            if filename.lower().endswith(".rbf"):
                full = os.path.join(rootdir, filename)
                installed_rbfs.append(os.path.relpath(full, RBF_ROOT))
    installed_rbfs.sort(key=str.lower)

    # Compare normal MRA references against installed RBFs. Only the single best
    # match is retained. When two timestamped builds tie, the newest is kept.
    matched_rbfs = set()
    retained_rbf_sources = defaultdict(list)
    exact_matches = []
    unresolved_references = []

    for reference_key in sorted(rbf_references):
        reference = rbf_reference_display[reference_key]
        mra_files = sorted(set(rbf_references[reference_key]), key=str.lower)
        candidates = []

        for rel in installed_rbfs:
            result = compare_core_names(reference, os.path.basename(rel))
            if result is not None:
                candidates.append((rel, result))

        if candidates:
            selected, equally_ranked = choose_preferred_rbf(reference, candidates)
            selected_rel, selected_result = selected
            matched_rbfs.add(selected_rel)
            for mra_file in mra_files:
                retained_rbf_sources[selected_rel].append(
                    ("MRA", mra_file, reference)
                )
            exact_matches.append(
                (reference, mra_files, selected_rel, selected_result, equally_ranked)
            )
        else:
            unresolved_references.append((reference, mra_files))

    # Silently allow a supplemental arcade launcher to claim an installed RBF.
    # Missing supplemental references are ignored because this is only a safety
    # net against false orphan deletion, not another reporting category.
    for reference_key in sorted(supplemental_rbf_references):
        if reference_key in rbf_references:
            continue

        reference = supplemental_rbf_reference_display[reference_key]
        launcher_files = sorted(
            set(supplemental_rbf_references[reference_key]),
            key=str.lower,
        )
        candidates = []

        for rel in installed_rbfs:
            result = compare_core_names(reference, os.path.basename(rel))
            if result is not None:
                candidates.append((rel, result))

        if candidates:
            selected, _equally_ranked = choose_preferred_rbf(reference, candidates)
            selected_rel, _selected_result = selected
            matched_rbfs.add(selected_rel)
            for launcher_file in launcher_files:
                retained_rbf_sources[selected_rel].append(
                    ("MGL supplemental", launcher_file, reference)
                )

    # Files sharing the selected core's exact timestamp-stripped name are
    # duplicate builds. They are listed separately from truly unreferenced RBFs.
    installed_by_duplicate_key = defaultdict(list)
    for rel in installed_rbfs:
        key = rbf_duplicate_key(rel)
        if key:
            installed_by_duplicate_key[key].append(rel)

    duplicate_groups = []
    duplicate_rbfs = set()
    for key, files in sorted(installed_by_duplicate_key.items()):
        if len(files) < 2:
            continue
        kept = sorted(set(files).intersection(matched_rbfs), key=str.lower)
        extras = sorted(set(files) - set(kept), key=str.lower)
        if kept and extras:
            duplicate_groups.append((key, kept, extras))
            duplicate_rbfs.update(extras)

    orphan_rbfs = sorted(
        set(installed_rbfs) - matched_rbfs - duplicate_rbfs,
        key=str.lower,
    )
    duplicate_rbfs = sorted(duplicate_rbfs, key=str.lower)
    deletable_rbfs = sorted(set(orphan_rbfs).union(duplicate_rbfs), key=str.lower)

    # Count and list MRA files whose referenced RBF is not installed.
    orphan_mras = sorted(
        [
            (mra_file, reference)
            for reference, mra_files in unresolved_references
            for mra_file in mra_files
        ],
        key=lambda item: item[0].lower(),
    )

    with open(COMBINED_REPORT_PATH, "w") as log:
        log.write("MRA folder: " + MRA_ROOT + "\n")
        log.write("MAME ROM folder: " + MAME_ROOT + "\n")
        log.write("Arcade core folder: " + RBF_ROOT + "\n")
        log.write("MRA files scanned: " + str(mra_count) + "\n")
        log.write("ROM check mode: " + ("deep CRC" if args.deep else "normal") + "\n")

        log.write("\nROM ZIP SUMMARY\n")
        log.write("===============\n")
        log.write("Installed ROM ZIP archives found: " + str(len(actual_zips)) + "\n")
        log.write("ROM ZIP archives matched to MRAs: " + str(len(used_zips)) + "\n")
        log.write("Orphan ROM ZIP archives: " + str(len(orphan_zips)) + "\n")
        log.write(
            "MRA files with required ROM data not found: "
            + str(len(missing_rom_mras))
            + "\n"
        )

        log.write("\n================================================================\n")
        log.write("ZIP FILE RESULTS\n")
        log.write("================================================================\n")
        log.write("ORPHAN ROM ZIP ARCHIVES - NOT USED BY ANY MRA\n")
        log.write("------------------------------------------------\n")
        if orphan_zips:
            for rel in orphan_zips:
                log.write(rel + "\n")
        else:
            log.write("None\n")

        log.write("\n================================================================\n")
        log.write("MRA ROM REFERENCE RESULTS\n")
        log.write("================================================================\n")
        log.write("MRA FILES - REQUIRED ROM DATA NOT FOUND\n")
        log.write("-----------------------------------------\n")
        if missing_rom_mras:
            for item in missing_rom_mras:
                log.write("\n" + item["mra"] + "\n")
                for recipe in item["recipes"]:
                    log.write("  ROM recipe {}:\n".format(recipe["number"]))
                    for group, result in recipe["groups"]:
                        listed = " | ".join(group["zip_names"]) or "none"
                        log.write("    Listed ROM ZIP(s): " + listed + "\n")
                        log.write("    Result: " + result["reason"] + "\n")
        else:
            log.write("None\n")

        log.write("\n================================================================\n")
        log.write("PARENT ZIP MATCH RESULTS\n")
        log.write("================================================================\n")
        log.write("PARENT ZIP PROVIDED REQUIRED ROMS\n")
        log.write("---------------------------------\n")
        if content_name_matches:
            for item in content_name_matches:
                log.write("\nMRA: " + item["mra"] + "\n")
                log.write(
                    "  Requested ZIP(s): "
                    + (" | ".join(item["listed"]) if item["listed"] else "none")
                    + "\n"
                )
                for archive in item["archives"]:
                    log.write("  ROM located within parent ROM ZIP: " + archive + "\n")
                log.write(
                    "  All "
                    + str(item["part_count"])
                    + " required ROM files were found.\n"
                )
        else:
            log.write("None\n")

        log.write("\nRBF SUMMARY\n")
        log.write("===========\n")
        log.write("Unique RBF names referenced by MRAs: " + str(len(rbf_references)) + "\n")
        log.write("RBF files found: " + str(len(installed_rbfs)) + "\n")
        log.write("MRA references with exact matches: " + str(len(exact_matches)) + "\n")
        log.write("RBF files retained as referenced: " + str(len(matched_rbfs)) + "\n")
        log.write("Duplicate RBF files (older/extra builds): " + str(len(duplicate_rbfs)) + "\n")
        log.write("Orphan RBFs: " + str(len(orphan_rbfs)) + "\n")
        log.write("RBF files safe to delete: " + str(len(deletable_rbfs)) + "\n")
        log.write(
            "RBF names referenced by MRAs but not found in core folder: "
            + str(len(unresolved_references))
            + "\n"
        )
        log.write(
            "Orphan MRA files (no corresponding RBF): "
            + str(len(orphan_mras))
            + "\n"
        )

        log.write("\nORPHAN RBF FILES - UNREFERENCED\n")
        log.write("========================================\n")
        if orphan_rbfs:
            for rel in orphan_rbfs:
                log.write(rel + "\n")
        else:
            log.write("None\n")

        log.write("\nDUPLICATE RBF FILES - OLDER OR EXTRA BUILDS\n")
        log.write("=============================================\n")
        if duplicate_groups:
            for key, kept, extras in duplicate_groups:
                log.write("\nCore: " + key + "\n")
                for rel in kept:
                    log.write("  Kept: " + rel + "\n")
                for rel in extras:
                    log.write("  Duplicate: " + rel + "\n")
        else:
            log.write("None\n")

        log.write("\nORPHAN MRA FILES - NO CORRESPONDING RBF\n")
        log.write("=========================================\n")
        if orphan_mras:
            for mra_file, reference in orphan_mras:
                log.write("\n" + mra_file + "\n")
                log.write("  Referenced RBF not found: " + reference + "\n")
        else:
            log.write("None\n")

    print()
    print("=" * 72)
    print("ARCADE CLEANUP REPORT")
    print("=" * 72)
    try:
        with open(COMBINED_REPORT_PATH, "r") as report:
            print_colored_report(report.read(), missing_rom_mras, orphan_mras)
    except OSError as exc:
        print("WARNING: Unable to display combined report: {}".format(exc))
    print("=" * 72)
    print("Report saved to:")
    print(COMBINED_REPORT_PATH)
    print("=" * 72)
    print()

    zip_deleted = []
    zip_failed = []
    rbf_deleted = []
    rbf_failed = []

    # ZIP and RBF cleanup are independent. Neither runs without confirmation.
    if orphan_zips:
        print("This can delete ZIP files from:")
        print(MAME_ROOT)
        print("Type DELETE ZIPS to delete every orphan ZIP listed in the combined report.")
        zip_answer = input("Delete orphan ZIPs now? ").strip()

        if zip_answer == "DELETE ZIPS":
            zip_deleted, zip_failed = delete_files(MAME_ROOT, orphan_zips, "ZIP")
            if zip_deleted or zip_failed:
                write_delete_log(
                    ZIP_DELETE_LOG_PATH,
                    "MAME ROM folder",
                    MAME_ROOT,
                    zip_deleted,
                    zip_failed,
                )
        else:
            print("ZIP deletion canceled.")

    print()

    if deletable_rbfs:
        print("This can delete orphan and duplicate RBF core files from:")
        print(RBF_ROOT)
        print("Type DELETE RBFS to delete every RBF marked safe in the combined report.")
        rbf_answer = input("Delete orphan/duplicate RBFs now? ").strip()

        if rbf_answer == "DELETE RBFS":
            rbf_deleted, rbf_failed = delete_files(RBF_ROOT, deletable_rbfs, "RBF")
            if rbf_deleted or rbf_failed:
                write_delete_log(
                    RBF_DELETE_LOG_PATH,
                    "Arcade core folder",
                    RBF_ROOT,
                    rbf_deleted,
                    rbf_failed,
                )
        else:
            print("RBF deletion canceled.")

    print()
    print("ZIPs deleted:", len(zip_deleted))
    print("ZIP deletion failures:", len(zip_failed))
    print("RBFs deleted:", len(rbf_deleted))
    print("RBF deletion failures:", len(rbf_failed))

    if zip_deleted or zip_failed:
        print("ZIP delete log:")
        print(ZIP_DELETE_LOG_PATH)

    if rbf_deleted or rbf_failed:
        print("RBF delete log:")
        print(RBF_DELETE_LOG_PATH)

    if zip_failed or rbf_failed:
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
