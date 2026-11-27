"""`translate-bench verify`: rebuild results/v1/summary.json from the item rows and compare.

Needs only NumPy and sacreBLEU, no network, model or test text. It validates every results
file against the schema, recomputes every number in the summary (scores, coverage, paired
intervals, size steps, MetricX-24 aggregates) from the item rows and exits non-zero on any
difference. It also recomputes the judge v1 aggregates (results/v1/judge/), the speed subsets and,
when results/ltb-v1/ exists, the hard-cases pass rates and their intervals (translate_bench/ltb.py) and,
when results/v1.1/overall.json exists, the Overall score from the three results it averages
(translate_bench/overall.py).

Speed, memory and cost are published measurements that the item rows cannot reproduce; verify
checks them for schema and range only. The summary's choices by memory, speed and cost are
recomputed from results/v1/speed.json, so a changed input to a choice changes the summary.
"""

import hashlib
import json
from statistics import mean

from translate_bench import aggregate, schema
from translate_bench.aggregate import paired, ranking, score, tied, view_keys

SCHEMA = "translate-bench/summary@1"
# Historical seed string of the speed subsets (protocol, "Speed and memory").
SPEED_SEED = "local-mt-bench/v2/amendment-5/speed/"
TOLERANCE = 1.5e-6  # the summary stores six decimals
SENTENCE_WEIGHTS = (0, 0.25, 0.5, 0.75, 1)
MEMORY_RULES = (("within-4-gib", "local", 4, None), ("within-8-gib", "local", 8, None),
                ("any-memory", "local", None, None), ("fastest-tied-with-local-leader", "local", None, "seconds"),
                ("cheapest-tied-with-cloud-leader", "cloud", None, "cost"),
                ("fastest-tied-with-cloud-leader", "cloud", None, "seconds"))
AGGREGATION = (
    "COMET-22 of a cell is the mean over its scored items; chrF++ of a cell is corpus chrF++ from pooled "
    "sufficient statistics. A cell is one text type in one direction: 200 sentences or 20 passages. The overall "
    "score is, in each direction, the mean of the sentence and passage cells (50:50), then the mean over "
    "directions with equal weight. Paired differences use, cell by cell, the items both systems scored. "
    "Intervals are the 2.5th and 97.5th percentiles of 2,000 paired document draws and are not adjusted for "
    "multiple comparisons or for leaders chosen on the same data."
)


def system_block(release, sid):
    t = release.tables[sid]
    rows = release.rows[sid]
    scored = sum(r["status"] == "ok" and r["comet22"] is not None for r in rows)
    ok = sum(r["status"] == "ok" for r in rows)
    block = dict(kind=release.kind(sid),
                 completion=dict(attempted=len(rows), ok=ok, scored=scored,
                                 rate=scored / len(rows) if rows else None),
                 directions={k: t.directions(k) for k in schema.TYPES})
    both = t.directions()
    for metric in aggregate.METRICS:
        values = {v: score(t, v, schema.DIRECTIONS, metric) for v in aggregate.VIEWS}
        values["overall_measured"] = score(t, "overall", both, metric) if both else None
        block[metric] = values
    block["overall_measured_directions"] = len(both)
    block["n"] = {k: sum(len(t.items["comet22"][k, d]) for d in t.directions(k)) for k in schema.TYPES}
    cells = {}
    for d in schema.DIRECTIONS:
        entry = {}
        for kind in schema.TYPES:
            if (kind, d) in t.counts:
                attempted, ok_n = t.counts[kind, d]
                items = t.items["comet22"][kind, d]
                entry[kind] = dict(attempted=attempted, ok=ok_n, scored=len(items),
                                   comet22=aggregate.cell_score(items, "comet22"),
                                   chrf=aggregate.cell_score(t.items["chrf"][kind, d], "chrf"))
        for subset in schema.SUBSETS:
            items = t.subsets["comet22"].get((subset, d))
            if items is not None:
                entry[subset] = dict(scored=len(items), comet22=aggregate.cell_score(items, "comet22"),
                                     chrf=aggregate.cell_score(t.subsets["chrf"][subset, d], "chrf"))
        if entry:
            cells[d] = entry
    block["cells"] = cells
    pairs = {}
    for language in schema.LANGUAGES:
        ds = [f"en-{language}", f"{language}-en"]
        values = {v: score(t, v, ds) for v in aggregate.VIEWS}
        if any(x is not None for x in values.values()):
            pairs[language] = values
    block["pairs"] = pairs
    block["metricx24"] = metricx(rows)
    return block


def metricx(rows):
    """MetricX-24 as published: plain means per cell, sentences and passages 50:50 per direction,
    then the mean over directions with both types; per type, the mean over that type's cells."""
    cells = {}
    for r in rows:
        if r["status"] == "ok" and r.get("metricx24_ref") is not None:
            cells.setdefault((r["type"], r["direction"]), []).append(r)
    if not cells:
        return None
    if {d for t, d in cells if t == "sentence"} != {d for t, d in cells if t == "passage"}:
        return None  # the two text types cover different directions; no overall on the release's scale
    directions = sorted({d for _, d in cells})
    out = dict(directions=len(directions), n=sum(len(v) for v in cells.values()))
    for name in ("metricx24_ref", "metricx24_qe", "comet22"):
        def cell_mean(kind, d, name=name):
            return mean(r[name] for r in cells[kind, d] if r.get(name) is not None)
        if any(all(r.get(name) is None for r in v) for v in cells.values()):
            continue  # e.g. rows scored with MetricX-24 but without COMET-22
        out[name] = mean((cell_mean("sentence", d) + cell_mean("passage", d)) / 2 for d in directions)
        for kind in schema.TYPES:
            out[f"{name}_{kind}"] = mean(cell_mean(k, d) for (k, d) in cells if k == kind)
    return out


def leaders(release, view, directions=schema.DIRECTIONS, metric="comet22", systems=None):
    result = {}
    for kind in schema.KINDS:
        order = ranking(release, view, directions, kind, metric, systems)
        result[kind] = order[0] if order else None
    return result


def versus_leader(release, draws):
    rows = []
    for view in aggregate.VIEWS:
        keys = view_keys(view, schema.DIRECTIONS)
        for kind in schema.KINDS:
            order = ranking(release, view, kind=kind)
            for sid in order[1:]:
                rows.append(dict(view=view, kind=kind, leader=order[0], system=sid,
                                 **paired(draws, keys, sid, order[0])))
    local = ranking(release, "overall", kind="local")[0]
    keys = view_keys("overall", schema.DIRECTIONS)
    for sid in ranking(release, "overall", kind="cloud"):
        rows.append(dict(view="overall", kind="cloud-vs-local-leader", leader=local, system=sid,
                         **paired(draws, keys, sid, local)))
    return rows


def verdict(result):
    lo, hi = result["ci95"]
    return "cloud higher" if lo > 0 else "local higher" if hi < 0 else "not distinguishable"


def cloud_vs_local(release, draws):
    rows = []
    for view in aggregate.VIEWS:
        for directions in (schema.DIRECTIONS, *([d] for d in schema.DIRECTIONS)):
            lead = leaders(release, view, directions)
            keys = view_keys(view, directions)
            result = paired(draws, keys, lead["cloud"], lead["local"])
            n = min(sum(len(release.tables[s].items["comet22"][k]) for k in keys) for s in lead.values())
            rows.append(dict(view=view, direction=None if len(directions) > 1 else directions[0],
                             cloud=lead["cloud"], local=lead["local"], delta=result["delta"], ci95=result["ci95"],
                             paired_n=result["n"], n=n, verdict=verdict(result)))
    return rows


def language_pairs(release):
    rows = []
    for language in schema.LANGUAGES:
        ds = [f"en-{language}", f"{language}-en"]
        for view in aggregate.VIEWS:
            entry = dict(language=language, view=view)
            for kind in schema.KINDS:
                sid = ranking(release, view, ds, kind)[0]
                entry[kind] = dict(system=sid, score=score(release.tables[sid], view, ds))
            rows.append(entry)
    return rows


def families(release):
    """Local families with two or more sizes of known parameter count, in ascending size."""
    groups = {}
    for sid in release.published:
        s = release.systems[sid]
        if s["kind"] == "local" and s.get("parameters"):
            groups.setdefault(s["family"], []).append(sid)
    return {f: sorted(m, key=lambda x: release.systems[x]["parameters"]) for f, m in groups.items() if len(m) > 1}


def size_steps(release, draws):
    rows = []
    for family, members in families(release).items():
        for small, large in zip(members, members[1:]):
            entry = dict(family=family, smaller=small, larger=large)
            for view in aggregate.VIEWS:
                kind = None if view == "overall" else view
                ds = [d for d in schema.DIRECTIONS
                      if d in release.tables[small].directions(kind) and d in release.tables[large].directions(kind)]
                order = aggregate.release_order if view == "overall" else aggregate.frame_order
                result = paired(draws, view_keys(view, ds), large, small, order=order)
                entry[view] = dict(directions=len(ds), delta=result["delta"], ci95=result["ci95"], n=result["n"])
            rows.append(entry)
    return rows


def resources(release, sid):
    """Seconds per item (mean of the sentence and passage medians), peak memory and estimated cost."""
    entry = release.speed.get(sid) or {}
    if release.kind(sid) == "local":
        parts = [entry.get(k, {}).get("median_s") for k in schema.TYPES]
        return dict(seconds=None if None in parts or not entry else mean(parts),
                    memory=entry.get("peak_memory_gib"), cost=None)
    ref = entry.get("reference") or {}
    seconds = [ref.get(k, {}).get("seconds_per_item") for k in schema.TYPES]
    cost = [ref.get(k, {}).get("estimated_usd_per_1000_items") for k in schema.TYPES]
    return dict(seconds=None if None in seconds else mean(seconds), memory=None,
                cost=None if None in cost else mean(cost))


def choices(release, draws):
    keys = view_keys("overall", schema.DIRECTIONS)
    rows = []
    for rule, kind, budget, order in MEMORY_RULES:
        everyone = ranking(release, "overall", kind=kind)
        leader = everyone[0]
        res = {s: resources(release, s) for s in everyone}
        pool = [s for s in everyone if budget is None or res[s]["memory"] is not None and res[s]["memory"] <= budget]
        pick = pool[0] if pool else None
        if order and pick:
            close = [s for s in pool if res[s][order] is not None
                     and (s == pick or tied(paired(draws, keys, s, pick)))]
            pick = min(close, key=lambda s: (res[s][order], s)) if close else None
        entry = dict(rule=rule, kind=kind, memory_limit_gib=budget, leader=leader, system=pick)
        if pick:
            entry.update(score=score(release.tables[pick], "overall", schema.DIRECTIONS), **res[pick])
            entry["versus_leader"] = None if pick == leader else paired(draws, keys, pick, leader)
        entry["pending"] = sorted(s for s in everyone if kind == "local" and res[s]["seconds"] is None)
        rows.append(entry)
    return rows


def sentence_weights(release):
    rows = []
    members = ranking(release, "overall")
    for w in SENTENCE_WEIGHTS:
        values = {s: score(release.tables[s], "overall", schema.DIRECTIONS, weight=w) for s in members}
        entry = dict(sentence_weight=w)
        for kind in schema.KINDS:
            order = sorted((s for s in members if release.kind(s) == kind), key=lambda s: (-values[s], s))
            entry[kind] = [dict(system=s, score=values[s]) for s in order[:3]]
        rows.append(entry)
    return rows


def build_summary(release):
    draws = release.draws("comet22")
    summary = dict(
        schema=SCHEMA, release=schema.RELEASE, aggregation=AGGREGATION,
        bootstrap=dict(description=("Paired document bootstrap: each source document gets one multiplicity per draw "
                                    "in every cell it appears in; 95% intervals are the 2.5th and 97.5th percentiles."),
                       draws=2000, seed_string="site-v2"),
        directions=list(schema.DIRECTIONS),
        systems={sid: system_block(release, sid) for sid in release.published},
        rankings={view: {kind: ranking(release, view, kind=kind) for kind in schema.KINDS}
                  for view in aggregate.VIEWS},
        versus_leader=versus_leader(release, draws),
        cloud_vs_local=cloud_vs_local(release, draws),
        language_pairs=language_pairs(release),
        size_steps=size_steps(release, draws),
        choices=choices(release, draws),
        sentence_weights=sentence_weights(release),
    )
    return aggregate.rounded(summary)


def differences(expected, actual, path="summary", found=None, limit=50, tolerance=TOLERANCE):
    """Paths where two summaries differ (numbers within `tolerance` are equal)."""
    found = [] if found is None else found
    if len(found) >= limit:
        return found
    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in sorted(set(expected) | set(actual), key=str):
            if key not in expected or key not in actual:
                found.append(f"{path}.{key}: present in only one")
            else:
                differences(expected[key], actual[key], f"{path}.{key}", found, limit, tolerance)
    elif isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            found.append(f"{path}: {len(expected)} entries published, {len(actual)} recomputed")
        else:
            for i, (a, b) in enumerate(zip(expected, actual)):
                differences(a, b, f"{path}[{i}]", found, limit, tolerance)
    elif isinstance(expected, bool) or isinstance(actual, bool) or not (
            isinstance(expected, (int, float)) and isinstance(actual, (int, float))):
        if expected != actual:
            found.append(f"{path}: published {expected!r}, recomputed {actual!r}")
    elif abs(expected - actual) > tolerance:
        found.append(f"{path}: published {expected!r}, recomputed {actual!r}")
    return found


def schema_problems(root):
    problems = []
    registry = schema.read_json(root / "configs" / "systems.json")
    problems += schema.registry_problems(registry)
    ids = {s["id"] for s in registry["systems"]}
    folder = root / "results" / schema.RELEASE / "items"
    manifest = root / "datasets" / "items.jsonl"
    frame = {}
    if manifest.is_file():
        frame = {i["id"]: (i["direction"], i["type"], i["subset"], i["doc"]) for i in schema.read_jsonl(manifest)}
    files = {p.stem for p in folder.glob("*.jsonl")}
    for extra in sorted(files - ids):
        problems.append(f"results/v1/items/{extra}.jsonl: not in the registry")
    for sid in sorted(ids):
        path = folder / f"{sid}.jsonl"
        if not path.is_file():
            problems.append(f"{path.relative_to(root)}: missing")
            continue
        rows = schema.read_jsonl(path)
        problems += schema.rows_problems(rows, f"items/{sid}")
        outside = [r["id"] for r in rows if frame and frame.get(r.get("id")) != (r.get("direction"), r.get("type"),
                                                                             r.get("subset"), r.get("doc"))]
        if outside:
            problems.append(f"items/{sid}: {len(outside)} rows differ from datasets/items.jsonl, e.g. {outside[0]}")
        system = next(s for s in registry["systems"] if s["id"] == sid)
        table = aggregate.Tables(rows)
        for kind in schema.TYPES:
            have = sorted({r["direction"] for r in rows if r["type"] == kind}, key=schema.DIRECTIONS.index)
            if have != system["directions_attempted"][kind]:
                problems.append(f"items/{sid}: attempted {kind} directions differ from the registry")
            if table.directions(kind) != system["directions_complete"][kind]:
                problems.append(f"items/{sid}: complete {kind} directions differ from the registry")
        if sorted({r["subset"] for r in rows if r["subset"]}) != system["passage_sets_attempted"]:
            problems.append(f"items/{sid}: passage sets differ from the registry")
    speed = root / "results" / schema.RELEASE / "speed.json"
    if speed.is_file():
        problems += schema.speed_problems(schema.read_json(speed), {s["id"]: s["kind"] for s in registry["systems"]})
    return problems


def speed_subset_problems(root, release):
    """Recompute the frozen speed subsets from item ids alone and compare with speed.json."""
    path = root / "results" / schema.RELEASE / "speed.json"
    if not path.is_file():
        return []
    speed = schema.read_json(path)
    seed = speed["selection"]["seed_string"]
    count = speed["selection"]["per_type"]
    problems = [] if seed == SPEED_SEED else ["speed.json: seed string differs from the historical one"]
    for sid, entry in speed["systems"].items():
        if entry["kind"] != "local":
            continue
        rows = release.rows[sid]
        for kind in schema.TYPES:
            by_direction = {}
            for r in rows:
                if r["type"] == kind:
                    by_direction.setdefault(r["direction"], []).append(r["id"])
            queues = {d: sorted(ids, key=lambda i: hashlib.sha256((seed + i).encode()).digest())
                      for d, ids in by_direction.items()}
            picked, round_ = [], 0
            while len(picked) < count:
                for d in sorted(queues):
                    if round_ < len(queues[d]) and len(picked) < count:
                        picked.append(queues[d][round_])
                round_ += 1
            if picked != entry["items"][kind]:
                problems.append(f"speed.json {sid}: {kind} subset differs from the selection rule")
    return problems


def main(root, quiet=False):
    from translate_bench import judge_results, ltb, overall

    problems = schema_problems(root)
    if problems:
        for p in problems[:50]:
            print(p)
        print(f"verify: {len(problems)} schema problems")
        return 1
    release = aggregate.Release(root)
    published = schema.read_json(root / "results" / schema.RELEASE / "summary.json")
    recomputed = json.loads(json.dumps(build_summary(release)))
    found = differences(published, recomputed)
    found += speed_subset_problems(root, release)
    found += judge_results.check(root)
    found += ltb.check(root)
    found += overall.check(root)
    for line in found:
        print(line)
    systems = len(release.published)
    rows = sum(len(r) for r in release.rows.values())
    if found:
        print(f"verify: {len(found)} differences")
        return 1
    if not quiet:
        judged = (" and the judge v1 aggregates with their document-bootstrap intervals"
                  if judge_results.exists(root) else "")
        print(f"verify: {systems} systems, {rows:,} item rows. Every results file matches its schema. "
              "Recomputed from the item rows with no difference: summary.json (scores, coverage, paired intervals, "
              f"size steps, MetricX-24 aggregates){judged}. Recomputed from the item ids: the speed subsets.")
        if ltb.exists(root):
            count = len(schema.read_json(root / ltb.BASE / "summary.json")["systems"])
            second = " and the second verifier's counts checked against them" if ltb.second_verifier(root) else ""
            print(f"verify: hard cases (results/ltb-v1/): pass rates and bootstrap intervals of {count} systems, on "
                  "all items, on those in the release's directions and, below 18 directions, on those in the covered "
                  f"directions, recomputed from the rows with no difference{second}.")
        if overall.exists(root):
            counts = schema.read_json(root / overall.PATH)["counts"]
            print(f"verify: Overall score ({overall.PATH.as_posix()}): {counts['overall']} of {counts['systems']} "
                  "systems, recomputed from summary.json, the judge summary and the hard-cases summary with no "
                  "difference.")
        print("verify: speed, memory and cost figures are published measurements and cannot be recomputed from the "
              "item rows; they are checked for schema and range only. The memory, speed and cost choices in "
              "summary.json were recomputed from them.")
    return 0
