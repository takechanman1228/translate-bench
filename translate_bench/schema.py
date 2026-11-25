"""File layout, vocabulary and validation of the public files.

Every results file is checked here: the system registry (`configs/systems.json`), the
item rows (`results/v1/items/<system>.jsonl`), the speed file (`results/v1/speed.json`)
and the summary (`results/v1/summary.json`). Validation returns a list of problems
instead of raising, so `translate-bench verify` can report all of them at once.
"""

import json
import math
import re
from pathlib import Path

RELEASE = "v1"
# Languages paired with English, in the order the release reports them.
LANGUAGES = ("ja", "zh-Hans", "es", "ko", "fr", "de", "pt-BR", "ar", "id")
CORE_LANGUAGES = ("ja", "zh-Hans", "es")
LANGUAGE_NAMES = {
    "en": "English", "ja": "Japanese", "zh-Hans": "Simplified Chinese", "es": "Spanish", "ko": "Korean",
    "fr": "French", "de": "German", "pt-BR": "Brazilian Portuguese", "ar": "Arabic", "id": "Indonesian",
}
DIRECTIONS = tuple(d for k in LANGUAGES for d in (f"en-{k}", f"{k}-en"))
TYPES = ("sentence", "passage")
# Passages of the twelve directions outside the core come from two sets of WMT24++ documents.
SUBSETS = {"set-8": 8, "set-12": 12}
CELL_SIZE = {"sentence": 200, "passage": 20}
STATUSES = ("ok", "failed")
KINDS = ("local", "cloud")
PROVENANCE = ("pilot", "release")
EXECUTION = ("serial", "throughput", "batched")
SHA256 = re.compile(r"[0-9a-f]{64}")
SYSTEM_ID = re.compile(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?")
ROW_FIELDS = (
    "id", "direction", "type", "subset", "doc", "status", "comet22", "chrf_stats", "metricx24_ref",
    "metricx24_qe", "output_sha256", "provenance", "execution", "request_batch", "failure", "output_equals_source",
)
REQUIRED_ROW_FIELDS = ("id", "direction", "type", "subset", "doc", "status", "comet22", "chrf_stats", "output_sha256")


def parse_direction(direction):
    """Split "en-pt-BR" or "zh-Hans-en" into its two language codes; English is always one side."""
    if direction.startswith("en-") and direction[3:] in LANGUAGE_NAMES:
        return "en", direction[3:]
    if direction.endswith("-en") and direction[:-3] in LANGUAGE_NAMES:
        return direction[:-3], "en"
    raise ValueError(f"Unknown direction: {direction!r}")


def language_of(direction):
    src, tgt = parse_direction(direction)
    return tgt if src == "en" else src


def is_core(direction):
    return language_of(direction) in CORE_LANGUAGES


def find_root(start=None):
    """The checkout that holds configs/systems.json and results/v1, searched upward from `start` or this file."""
    candidates = [Path(start or Path.cwd()).resolve(), Path(__file__).resolve().parent]
    for base in candidates:
        for folder in (base, *base.parents):
            if (folder / "configs" / "systems.json").is_file() and (folder / "results" / RELEASE).is_dir():
                return folder
    raise FileNotFoundError("Run inside a translate-bench checkout (configs/systems.json and results/v1 not found)")


def safe_location(path, root, option):
    """Resolve a writable location; inside the checkout only a directory Git ignores is accepted.

    Test texts, references and outputs must never land where Git would publish them."""
    import subprocess

    path = Path(path).expanduser().resolve()
    root = None if root is None else Path(root).resolve()
    if root is None or not path.is_relative_to(root):
        return path
    if (root / ".git").exists():
        relative = path.relative_to(root).as_posix() or "."
        ignored = subprocess.run(["git", "check-ignore", "-q", "--no-index", relative], cwd=root,
                                 capture_output=True).returncode == 0
    else:
        ignored = any(path.is_relative_to(root / d) for d in ("private", ".cache"))
    if not ignored:
        raise ValueError(f"{option} {path} is inside the checkout but not in a directory Git ignores; use a "
                         "location outside the checkout or under private/")
    return path


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_jsonl(path):
    rows = []
    with Path(path).open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    raise ValueError(f"{path}: invalid JSON at line {number}") from None
    return rows


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=1, allow_nan=False) + "\n"
    path.write_text(text, encoding="utf-8")


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n")


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def row_problems(row):
    """Problems with one item row, as short strings; an empty list means the row is valid."""
    problems = []
    if not isinstance(row, dict):
        return ["row is not an object"]
    unknown = set(row) - set(ROW_FIELDS)
    if unknown:
        problems.append(f"unknown fields {sorted(unknown)}")
    missing = [k for k in REQUIRED_ROW_FIELDS if k not in row]
    if missing:
        return problems + [f"missing fields {missing}"]
    if not isinstance(row["id"], str) or not row["id"]:
        problems.append("id must be a nonempty string")
    try:
        parse_direction(row["direction"])
    except (ValueError, TypeError, AttributeError):
        problems.append("unknown direction")
    if row["type"] not in TYPES:
        problems.append("type must be sentence or passage")
    if row["subset"] is not None and (row["subset"] not in SUBSETS or row["type"] != "passage"):
        problems.append("subset must be null, set-8 or set-12 (passages only)")
    if not isinstance(row["doc"], str) or not row["doc"]:
        problems.append("doc must be a nonempty string")
    if row["status"] not in STATUSES:
        problems.append("status must be ok or failed")
    ok = row["status"] == "ok"
    if row["comet22"] is not None and (not ok or not _number(row["comet22"])):
        problems.append("comet22 must be a number on an ok row, else null")
    stats = row["chrf_stats"]
    if ok:
        if not (isinstance(stats, list) and len(stats) == 24 and all(isinstance(x, int) and x >= 0 for x in stats)):
            problems.append("chrf_stats must be 24 nonnegative integers on an ok row")
        if not (isinstance(row["output_sha256"], str) and SHA256.fullmatch(row["output_sha256"])):
            problems.append("output_sha256 must be a SHA-256 hex digest on an ok row")
    elif stats is not None or row["output_sha256"] is not None:
        problems.append("a failed row has no chrf_stats or output_sha256")
    for key in ("metricx24_ref", "metricx24_qe"):
        value = row.get(key)
        if value is not None and (not ok or not _number(value) or not 0 <= value <= 25):
            problems.append(f"{key} must be null or a number in 0–25 on an ok row")
    if row.get("provenance") not in (None, *PROVENANCE):
        problems.append("provenance must be null, pilot or release")
    if row.get("execution") not in (None, *EXECUTION):
        problems.append("execution must be null, serial, throughput or batched")
    for key in ("request_batch", "failure"):
        if row.get(key) is not None and not isinstance(row[key], str):
            problems.append(f"{key} must be null or a string")
    if row.get("output_equals_source") not in (None, True, False):
        problems.append("output_equals_source must be null or a boolean")
    return problems


def rows_problems(rows, label):
    """Row problems plus duplicate IDs and partial cells, for one system's file."""
    problems = []
    seen = set()
    for number, row in enumerate(rows, 1):
        for problem in row_problems(row):
            problems.append(f"{label} row {number}: {problem}")
        if isinstance(row, dict) and row.get("id") in seen:
            problems.append(f"{label} row {number}: duplicate id {row['id']}")
        elif isinstance(row, dict):
            seen.add(row.get("id"))
    return problems


SYSTEM_FIELDS = ("id", "name", "developer", "kind", "family", "directions_attempted", "directions_complete",
                 "passage_sets_attempted")
MACHINE_MEMORY_GIB = 32  # the one machine every local system ran on


def _direction_map(value):
    return isinstance(value, dict) and set(value) == set(TYPES) and all(
        isinstance(v, list) and all(d in DIRECTIONS for d in v) for v in value.values())


def registry_problems(registry):
    problems = []
    systems = registry.get("systems")
    if not isinstance(systems, list) or not systems:
        return ["configs/systems.json: systems must be a nonempty list"]
    ids = [s.get("id") for s in systems]
    if len(set(ids)) != len(ids):
        problems.append("configs/systems.json: duplicate system ids")
    for s in systems:
        label = f"configs/systems.json {s.get('id')}"
        for key in SYSTEM_FIELDS:
            if key not in s:
                problems.append(f"{label}: missing {key}")
        if not isinstance(s.get("id"), str) or not SYSTEM_ID.fullmatch(s["id"]):
            problems.append(f"{label}: id must be lower-case letters, digits, dots and hyphens")
        if s.get("kind") not in KINDS:
            problems.append(f"{label}: kind must be local or cloud")
        for key in ("directions_attempted", "directions_complete"):
            if not _direction_map(s.get(key)):
                problems.append(f"{label}: {key} must map sentence and passage to lists of directions")
        if _direction_map(s.get("directions_attempted")) and _direction_map(s.get("directions_complete")):
            for kind in TYPES:
                if not set(s["directions_complete"][kind]) <= set(s["directions_attempted"][kind]):
                    problems.append(f"{label}: a complete {kind} direction that was not attempted")
        if not set(s.get("passage_sets_attempted") or []) <= set(SUBSETS):
            problems.append(f"{label}: passage_sets_attempted must list set-8 and/or set-12")
        weights = s.get("weights")
        if weights is not None and weights.get("sha256") is not None and not SHA256.fullmatch(weights["sha256"]):
            problems.append(f"{label}: weights.sha256 must be a SHA-256 hex digest")
    return problems


SPEED_PART = ("attempts", "successful", "failures", "median_s", "p90_s", "repetition_median_s", "repetition_spread_s",
              "median_output_tokens_per_s", "median_decode_tokens_per_s", "median_output_chars_per_s")
LOCAL_SPEED = ("kind", "date", "machine", "runtime", "load_s", "peak_memory_gib", "memory_measured", "memory_note",
               "download_bytes", "sentence", "passage", "start_conditions_met", "flagged", "items")
CLOUD_SPEED = ("kind", "reference")
REFERENCE = ("seconds_per_item", "estimated_usd_per_1000_items", "tokens_per_item", "directions")


def speed_problems(speed, kinds):
    """Schema and range checks of speed.json. The times, memory and cost are published measurements:
    they cannot be recomputed from the item rows, only checked for form and plausibility."""
    problems = []
    for sid, entry in speed.get("systems", {}).items():
        label = f"results/v1/speed.json {sid}"
        if sid not in kinds:
            problems.append(f"{label}: unknown system")
            continue
        expected = LOCAL_SPEED if kinds[sid] == "local" else CLOUD_SPEED
        if entry.get("kind") != kinds[sid] or set(entry) != set(expected):
            problems.append(f"{label}: fields must be exactly {', '.join(expected)}")
            continue
        if kinds[sid] == "cloud":
            ref = entry["reference"]
            if ref is None:
                continue
            for kind in TYPES:
                part = ref.get(kind) or {}
                if set(part) - {"cost_note"} != set(REFERENCE):
                    problems.append(f"{label}: reference.{kind} fields must be {', '.join(REFERENCE)}")
                    continue
                if not (_number(part["seconds_per_item"]) and part["seconds_per_item"] > 0):
                    problems.append(f"{label}: reference.{kind}.seconds_per_item must be positive")
                cost = part["estimated_usd_per_1000_items"]
                if cost is not None and not (_number(cost) and cost > 0):
                    problems.append(f"{label}: reference.{kind}.estimated_usd_per_1000_items must be positive")
                if (cost is None) != ("cost_note" in part):
                    problems.append(f"{label}: reference.{kind} needs a cost_note exactly when the cost is null")
            continue
        for kind in TYPES:
            part = entry[kind]
            if set(part) != set(SPEED_PART):
                problems.append(f"{label}: {kind} fields must be {', '.join(SPEED_PART)}")
                continue
            counts = [part[k] for k in ("attempts", "successful", "failures")]
            if not all(isinstance(c, int) and c >= 0 for c in counts) or counts[1] + counts[2] != counts[0]:
                problems.append(f"{label}: {kind} attempts must equal successful + failures")
            if not (_number(part["median_s"]) and 0 < part["median_s"] <= part["p90_s"]):
                problems.append(f"{label}: {kind}.median_s must be positive and at most p90_s")
            reps = part["repetition_median_s"]
            if not (isinstance(reps, list) and len(reps) == 3 and all(_number(x) and x > 0 for x in reps)):
                problems.append(f"{label}: {kind}.repetition_median_s must hold three positive numbers")
            elif abs(max(reps) - min(reps) - part["repetition_spread_s"]) > 0.0015:
                problems.append(f"{label}: {kind}.repetition_spread_s must equal the spread of the medians")
        rss = entry["peak_memory_gib"]
        if entry["memory_measured"] is not (rss is not None):
            problems.append(f"{label}: peak_memory_gib must be present exactly when memory_measured")
        if rss is not None and not (_number(rss) and 0 < rss <= MACHINE_MEMORY_GIB):
            problems.append(f"{label}: peak_memory_gib must be within the machine's {MACHINE_MEMORY_GIB} GiB")
        if entry["start_conditions_met"] is not True:
            problems.append(f"{label}: a published speed run must have started under the benchmark's conditions")
        flags = entry["flagged"]
        if not (isinstance(flags, list) and len(flags) == 3 and all(isinstance(f, bool) for f in flags)):
            problems.append(f"{label}: flagged must hold one boolean per repetition (three), with no reason")
    return problems
