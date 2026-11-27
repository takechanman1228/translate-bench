"""The hard-cases track (results/ltb-v1/): the Last Translation Benchmark's 911 eval items.

results/ltb-v1/ holds `items.jsonl` (one row per item: id, direction, languages, SHA-256 of the
source text, number of rules, whether the item is in the release's directions), `rows/SYSTEM.jsonl`
(one row per item: pass, per-rule verdicts, status, SHA-256 of the translation) and `summary.json`.
No source text, rule text or translation. `second-verifier.json`, when present, gives for some systems the
items in the release's directions that a second verifier passed and the items on which it agrees with the
summary's verifier; the check ties its counts to the rows.

Aggregation: an item passes when every one of its rules passed; a system's pass rate is the share of
passed items. An unsupported or empty item counts as failed. The 95% intervals are the 2.5th and
97.5th percentiles of 2,000 bootstrap draws of items with replacement, from a NumPy PCG64 generator
seeded with the first eight bytes of SHA-256(SEED): first the draws over all items in items.jsonl
order, then over the items in the release's directions. Every system gets the same draws.

Coverage: a system that covers fewer than the release's 18 directions in results/v1/ (both text types
complete) also gets `covered`, the pass rate on the items in the release's directions that it covers.
Items in the directions it does not cover leave that denominator instead of counting as failed. Its
draws come from a generator seeded with SEED + "/covered/" + the covered directions joined by commas,
so systems with the same coverage share them. The Overall score uses this figure for such systems.
"""

import hashlib
from pathlib import Path

import numpy as np

from translate_bench import aggregate, schema

BASE = Path("results") / "ltb-v1"
SUMMARY_SCHEMA = "translate-bench/ltb-summary@1"
SECOND = BASE / "second-verifier.json"
SECOND_SCHEMA = "translate-bench/ltb-second-verifier@1"
ITEMS_SCHEMA_FIELDS = ("id", "direction", "source_iso", "target_iso", "source_label", "target_label",
                       "source_sha256", "rules", "ours")
ROW_FIELDS = ("id", "pass", "verdicts", "status", "translation_sha256")
STATUSES = ("ok", "empty", "unsupported", "unscored")
VERDICTS = (True, False, "skipped")
SEED = "translate-bench/ltb-v1/item-bootstrap"
DRAWS = 2000
TOLERANCE = 1.5e-6  # the summary stores six decimals
# ISO 639-3 codes of the Last Translation Benchmark mapped to the release's language codes.
RELEASE_LANGUAGES = {"eng": "en", "jpn": "ja", "zho": "zh-Hans", "spa": "es", "kor": "ko", "fra": "fr", "deu": "de",
                     "por": "pt-BR", "ara": "ar", "ind": "id"}
AGGREGATION = (
    "An item passes when every one of its verification rules passed. The pass rate is the share of passed "
    "items; unsupported and empty items count as failed. Systems with any unscored item are listed as "
    "incomplete and not summarized.")
BOOTSTRAP = (
    "95% percentile intervals of 2,000 draws of items with replacement (NumPy PCG64, seeded with the first "
    "eight bytes of SHA-256 of the seed string): the draws over all items come first, then those over the "
    "items in the release's directions; every system gets the same draws.")


def exists(root):
    return (Path(root) / BASE / "summary.json").is_file()


def load(root):
    """(items, {system: rows}) of the published track."""
    base = Path(root) / BASE
    items = schema.read_jsonl(base / "items.jsonl")
    rows = {p.stem: schema.read_jsonl(p) for p in sorted((base / "rows").glob("*.jsonl"))}
    return items, rows


def draws(n, rng, count=DRAWS):
    return rng.integers(0, n, size=(count, n))


def generator(seed=SEED):
    return np.random.default_rng(int.from_bytes(hashlib.sha256(seed.encode()).digest()[:8], "big"))


def rate_block(passes, index):
    """Items, passed, pass rate and its 95% interval of a 0/1 array under the draw indices `index`."""
    passes = np.asarray(passes, dtype=float)
    if not len(passes):
        return dict(items=0, passed=0, pass_rate=None, ci95=None)
    means = passes[index].mean(axis=1)
    low, high = np.quantile(means, [0.025, 0.975])
    return dict(items=len(passes), passed=int(passes.sum()), pass_rate=float(passes.mean()),
                ci95=[float(low), float(high)])


def release_direction(item):
    """The release's direction of an item between English and one of its languages ("en-ja"), else None."""
    source, target = (RELEASE_LANGUAGES.get(item[k]) for k in ("source_iso", "target_iso"))
    if source and target and source != target and "en" in (source, target):
        return f"{source}-{target}"
    return None


def coverage(root):
    """{system: covered directions} for the systems below all 18 directions in results/v1/summary.json.

    A direction is covered when both text types are complete in it, as for the release's overall score."""
    path = Path(root) / "results" / schema.RELEASE / "summary.json"
    if not path.is_file():
        return {}
    out = {}
    for sid, block in schema.read_json(path)["systems"].items():
        kinds = block["directions"]
        covered = [d for d in schema.DIRECTIONS if d in kinds["sentence"] and d in kinds["passage"]]
        if len(covered) < len(schema.DIRECTIONS):
            out[sid] = covered
    return out


def covered_draws(directions, n, seed=SEED, count=DRAWS):
    return draws(n, generator(f"{seed}/covered/{','.join(directions)}"), count) if n else None


def system_block(items, rows, index_all, index_ours, covered=None, seed=SEED, count=DRAWS):
    by_id = {r["id"]: r for r in rows}
    passes = [bool(by_id[it["id"]]["pass"]) for it in items]
    ours = [p for p, it in zip(passes, items) if it["ours"]]
    pairs = {}
    for it, p in zip(items, passes):
        pair = pairs.setdefault(it["direction"], [0, 0])
        pair[0] += 1
        pair[1] += p
    statuses = [by_id[it["id"]]["status"] for it in items]
    checked = [v for r in rows for v in r["verdicts"] if v != "skipped"]
    block = dict(
        all=rate_block(passes, index_all), our_directions=rate_block(ours, index_ours),
        unsupported=statuses.count("unsupported"), empty=statuses.count("empty"),
        unscored=statuses.count("unscored"), rules_checked=len(checked),
        rules_skipped=sum(v == "skipped" for r in rows for v in r["verdicts"]),
        by_pair={d: dict(items=n, passed=k, pass_rate=k / n) for d, (n, k) in sorted(pairs.items())})
    if covered is not None:
        inside = [(p, it) for p, it in zip(passes, items) if it["ours"] and release_direction(it) in covered]
        outside = [it for it in items if it["ours"] and release_direction(it) not in covered]
        figures = rate_block([p for p, _ in inside], covered_draws(covered, len(inside), seed, count))
        block["covered"] = dict(
            directions=len(covered), **figures, left_out=len(outside),
            unsupported_inside=sum(by_id[it["id"]]["status"] == "unsupported" for _, it in inside),
            attempted_outside=sum(by_id[it["id"]]["status"] != "unsupported" for it in outside))
    return block


def systems(items, rows, seed=SEED, count=DRAWS, coverage=None):
    """{system: block} recomputed from the rows of the complete systems; `coverage` as `coverage(root)` gives it."""
    rng = generator(seed)
    index_all = draws(len(items), rng, count)
    index_ours = draws(sum(it["ours"] for it in items), rng, count)
    coverage = coverage or {}
    return aggregate.rounded({sid: system_block(items, rs, index_all, index_ours, coverage.get(sid), seed, count)
                              for sid, rs in sorted(rows.items())})


def row_problems(items, rows, summary):
    """Rows that do not fit items.jsonl, the vocabulary or the summary's lists of systems."""
    problems = []
    rules = {it["id"]: it["rules"] for it in items}
    for it in items:
        if set(it) != set(ITEMS_SCHEMA_FIELDS):
            problems.append(f"ltb-v1 items.jsonl {it.get('id')}: fields differ from {ITEMS_SCHEMA_FIELDS}")
            break
    if len(rules) != len(items):
        problems.append("ltb-v1 items.jsonl: duplicate ids")
    off = [it["id"] for it in items if it["ours"] != (release_direction(it) is not None)]
    if off:
        problems.append(f"ltb-v1 items.jsonl: `ours` differs from the release's directions for {len(off)} items, "
                        f"e.g. {off[0]}")
    listed = set(summary["systems"])
    if set(rows) != listed:
        problems.append(f"ltb-v1: row files {sorted(set(rows) ^ listed)} differ from summary.json's systems")
    held_back = {e["system"] for e in summary.get("incomplete", [])} | set(summary.get("pending", []))
    if held_back & set(rows):
        problems.append(f"ltb-v1: incomplete or pending systems have row files: {sorted(held_back & set(rows))}")
    for sid, rs in rows.items():
        label = f"ltb-v1 rows/{sid}"
        if [r.get("id") for r in rs] != [it["id"] for it in items]:
            problems.append(f"{label}: ids differ from items.jsonl")
            continue
        for r in rs:
            v = r["verdicts"]
            if set(r) != set(ROW_FIELDS):
                problems.append(f"{label} {r['id']}: fields differ from {ROW_FIELDS}")
            elif r["status"] not in STATUSES or r["status"] == "unscored":
                problems.append(f"{label} {r['id']}: status {r['status']!r} in a complete system")
            elif not isinstance(v, list) or len(v) != rules[r["id"]] or any(
                    x not in VERDICTS or isinstance(x, int) and not isinstance(x, bool) for x in v):
                problems.append(f"{label} {r['id']}: verdicts do not match the item's rules")
            elif r["pass"] is not (all(x is True for x in v)):
                problems.append(f"{label} {r['id']}: pass differs from the verdicts")
            elif "skipped" in v and False not in v[:v.index("skipped")]:
                problems.append(f"{label} {r['id']}: a rule is skipped before any rule failed")
            elif (r["translation_sha256"] is None) != (r["status"] in ("empty", "unsupported")):
                problems.append(f"{label} {r['id']}: translation digest does not fit the status")
            elif r["status"] in ("empty", "unsupported") and any(x is not False for x in v):
                problems.append(f"{label} {r['id']}: an item without translation must fail every rule")
            else:
                continue
            break
    return problems


def second_verifier(root):
    """The published cross-check by a second verifier, or None."""
    path = Path(root) / SECOND
    return schema.read_json(path) if path.is_file() else None


def second_problems(summary, second):
    """Counts of second-verifier.json that do not fit the summary (and so the rows) or each other.

    Per system: the items are the summary's items in the release's directions; the primary verifier's passes
    are the summary's; the items on which the two disagree are at least the difference of their passes, and of
    the same parity (each disagreement moves one pass)."""
    label = "ltb-v1 second-verifier.json"
    primary, other = summary["verifier"]["model"], second["verifier"]["model"]
    problems = []
    if second.get("schema") != SECOND_SCHEMA:
        problems.append(f"{label}: schema is not {SECOND_SCHEMA}")
    if second["primary"] != primary or other == primary:
        problems.append(f"{label}: primary verifier {second['primary']!r} is not the summary's {primary!r}")
    items = agreed = 0
    for sid, e in second["systems"].items():
        ours = (summary["systems"].get(sid) or {}).get("our_directions")
        if ours is None:
            problems.append(f"{label} {sid}: not a system of the summary")
            continue
        n, passed = e["items"], e["passed"]
        if n != ours["items"] or n != summary["dataset"]["our_direction_items"]:
            problems.append(f"{label} {sid}: {n} items, the summary has {ours['items']} in the release's directions")
        elif set(passed) != {primary, other}:
            problems.append(f"{label} {sid}: passes of {sorted(passed)}, expected {sorted((primary, other))}")
        elif passed[primary] != ours["passed"]:
            problems.append(f"{label} {sid}: {passed[primary]} passed under {primary}, the rows have {ours['passed']}")
        elif not (0 <= passed[other] <= n and 0 <= e["agreed"] <= n):
            problems.append(f"{label} {sid}: counts outside 0..{n}")
        elif (n - e["agreed"]) < abs(passed[primary] - passed[other]) or (
                n - e["agreed"] - abs(passed[primary] - passed[other])) % 2:
            problems.append(f"{label} {sid}: agreement {e['agreed']} does not fit the passes")
        items += n
        agreed += e["agreed"]
    if second["total"] != dict(items=items, agreed=agreed):
        summed = dict(items=items, agreed=agreed)
        problems.append(f"{label}: total {second['total']} differs from the systems' sum {summed}")
    return problems


def check(root):
    """Differences between results/ltb-v1/summary.json and a recomputation from the rows; [] when absent."""
    from translate_bench.verify import differences

    if not exists(root):
        return []
    summary = schema.read_json(Path(root) / BASE / "summary.json")
    items, rows = load(root)
    problems = row_problems(items, rows, summary)
    if problems:
        return problems
    boot = summary["bootstrap"]
    again = systems(items, rows, boot["seed_string"], boot["draws"], coverage(root))
    found = differences(summary["systems"], again, "ltb-v1 summary.systems", tolerance=TOLERANCE)
    counts = dict(items=len(items), our_direction_items=sum(it["ours"] for it in items),
                  rules=sum(it["rules"] for it in items))
    for key, value in counts.items():
        if summary["dataset"][key] != value:
            found.append(f"ltb-v1 summary.dataset.{key}: published {summary['dataset'][key]}, items.jsonl {value}")
    second = second_verifier(root)
    if second is not None:
        found += second_problems(summary, second)
    return found
