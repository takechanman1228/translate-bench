"""The release's judge results (judge protocol v1): files, aggregation and the check `verify` runs.

results/v1/judge/ holds, for every system, the rows of its pairwise comparison with DeepL API
(`pairwise/SYSTEM__JUDGE.json`) and of the error annotation of its own translations
(`errors/SYSTEM__JUDGE.json`), on the fixed sample of datasets/judge-sample.json, and `summary.json`
with the aggregates. No text: each row holds the item id, its cell and document, a status, the
verdict and the counts.

The aggregates are those of `translate-bench judge` (translate_bench/judge.py), so a user's own judge
run is reported in the same terms:

- Each direction counts equally and its sentences and passages 50:50: item i of direction d and type t
  weighs 1 / (D * 2 * n_dt), with D the directions counted. "all" uses the directions in which the
  system has rows of both types; "sentence" and "passage" every direction with rows of that type.
- Pairwise: net = sum of w * v with v = +1 (preferred to DeepL API), -1 (DeepL API preferred) or 0 (a tie,
  judged or identical outputs); preferred = W+ / (W+ + W-), the share of the decided items' weight.
- Errors: error-free = the weighted share of items with no error counted; penalty = 25 per critical,
  5 per major and 1 per minor error.
- 95% intervals: percentiles of 2,000 paired document-bootstrap draws (seed string
  "translate-bench/v1/judge-bootstrap"), documents drawn within strata that cover the same cells of
  the release's inputs; a draw that leaves a needed cell without documents is skipped (`draws` counts
  the draws used).
"""

from pathlib import Path

from translate_bench import schema

BASE = Path("results") / schema.RELEASE / "judge"
SUMMARY_SCHEMA = "translate-bench/judge-summary@1"
ROWS_SCHEMA = "translate-bench/judge-rows@1"
STAGES = ("pairwise", "errors")
# The summary stores four decimals; a value on a rounding boundary can land on either side on another platform.
TOLERANCE = 1.5e-4
ROW_FIELDS = {
    "pairwise": ("id", "direction", "type", "subset", "doc", "status", "reason", "winner", "shown_first",
                 "major_system", "major_against"),
    "errors": ("id", "direction", "type", "subset", "doc", "status", "reason", "critical", "major", "minor",
               "shared"),
}
STATUSES = {"pairwise": ("judged", "identical", "missing"), "errors": ("annotated", "missing")}
REASONS = (None, "not run", "failed")


def exists(root):
    return (Path(root) / BASE / "summary.json").is_file()


def load(root):
    """(summary, {stage: {system: file}}) of the published judge results."""
    _, files = load_rows(root)
    return schema.read_json(Path(root) / BASE / "summary.json"), files


def load_rows(root):
    """(None, {stage: {system: file}}): the row files alone."""
    base = Path(root) / BASE
    files = {stage: {} for stage in STAGES}
    for stage in STAGES:
        for path in sorted((base / stage).glob("*.json")):
            data = schema.read_json(path)
            files[stage][data["system"]] = data
    return None, files


def aggregate(root, files):
    """The summary's pairwise and errors lists, recomputed from the rows."""
    from translate_bench.judge import Documents, error_stats, load_sample, pairwise_stats

    root = Path(root)
    manifest = schema.read_jsonl(root / "datasets" / "items.jsonl")
    documents = Documents(load_sample(root), manifest)
    kinds = {s["id"]: s["kind"] for s in schema.read_json(root / "configs" / "systems.json")["systems"]}
    out = {}
    for stage, stats in (("pairwise", pairwise_stats), ("errors", error_stats)):
        entries = []
        for system, data in sorted(files[stage].items()):
            rows = data["rows"]
            scored = [r for r in rows if r["status"] != "missing"]
            entries.append(dict(system=system, kind=kinds.get(system), judge=data["judge"],
                                missing=sum(r["status"] == "missing" for r in rows), **stats(scored, documents)))
        out[stage] = entries
    return out


def row_problems(root, files, summary):
    sample = {i["id"]: i for i in schema.read_json(Path(root) / "datasets" / "judge-sample.json")["items"]}
    systems = {s["id"]: s for s in schema.read_json(Path(root) / "configs" / "systems.json")["systems"]}
    reference = summary.get("reference")
    problems = []
    expected = {"pairwise": set(systems) - {reference}, "errors": set(systems)}
    for stage in STAGES:
        if set(files[stage]) != expected[stage]:
            problems.append(f"results/v1/judge/{stage}: systems differ from the registry")
        for system, data in files[stage].items():
            label = f"results/v1/judge/{stage}/{system}"
            if data.get("schema") != ROWS_SCHEMA or data.get("stage") != stage:
                problems.append(f"{label}: schema and stage must be {ROWS_SCHEMA}, {stage}")
                continue
            if stage == "pairwise" and data.get("against") != reference:
                problems.append(f"{label}: against must be the summary's reference")
            attempted = set(systems[system]["directions_attempted"]["sentence"]) | set(
                systems[system]["directions_attempted"]["passage"]) if system in systems else set()
            ids = [r.get("id") for r in data["rows"]]
            wanted = [i for i, it in sample.items() if it["direction"] in attempted]
            if sorted(ids) != sorted(wanted):
                problems.append(f"{label}: rows must be the sampled items of the system's directions")
            for r in data["rows"]:
                if tuple(r) != ROW_FIELDS[stage]:
                    problems.append(f"{label}: row fields must be {', '.join(ROW_FIELDS[stage])}")
                    break
                it = sample.get(r["id"])
                if it is None or any(r[k] != it[k] for k in ("direction", "type", "subset", "doc")):
                    problems.append(f"{label}: {r['id']} differs from datasets/judge-sample.json")
                    break
                if r["status"] not in STATUSES[stage] or r["reason"] not in REASONS:
                    problems.append(f"{label}: {r['id']} has an unknown status or reason")
                    break
                if (r["status"] == "missing") != (r["reason"] is not None):
                    problems.append(f"{label}: {r['id']}: a reason is given exactly for a missing item")
                    break
                if stage == "pairwise":
                    ok = {"judged": ("system", "against", "tie"), "identical": ("tie",), "missing": (None,)}
                    if r["winner"] not in ok[r["status"]]:
                        problems.append(f"{label}: {r['id']}: winner {r['winner']!r} with status {r['status']}")
                        break
                else:
                    counts = [r[k] for k in ("critical", "major", "minor")]
                    if r["status"] == "annotated" and not all(isinstance(c, int) and c >= 0 for c in counts):
                        problems.append(f"{label}: {r['id']}: error counts must be non-negative integers")
                        break
    return problems


def check(root):
    """Differences between the published judge summary and a recomputation from the rows, plus row problems."""
    from translate_bench.verify import differences

    if not exists(root):
        return []
    summary, files = load(root)
    found = []
    if summary.get("schema") != SUMMARY_SCHEMA:
        found.append(f"results/v1/judge/summary.json: schema must be {SUMMARY_SCHEMA}")
    found += row_problems(root, files, summary)
    if found:
        return found
    recomputed = aggregate(root, files)
    for stage in STAGES:
        found += differences(summary[stage], recomputed[stage], f"judge.{stage}", limit=20, tolerance=TOLERANCE)
    return found


def entry(summary, stage, system, scope="all"):
    """One system's aggregate of one stage and scope, or None."""
    for e in summary[stage]:
        if e["system"] == system:
            return e.get(scope)
    return None
