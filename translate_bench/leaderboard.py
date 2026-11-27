"""`translate-bench leaderboard`: the release's table, computed from the published results.

By default the table is ranked by the Overall score of v1.1 (results/v1.1/overall.json: the mean of
COMET-22 x 100, the judge's error-free share and the hard-case pass rate, for the systems with every
pillar on at least 12 of the 18 directions; below 18, means over the directions covered, marked "(16/18)");
`--metric hard_cases` ranks every system by its hard-case pass rate (results/ltb-v1/). Both are one published figure per
system, so they take no `--pairs` or `--view`; every table shows them as columns.

`--metric comet22`, `chrf`, `metricx24_ref` and `metricx24_qe` rank on any selection of language pairs and
text types, computed from the item rows. Systems that cover every selected cell are ranked by the
release's aggregation; the others are listed below with their coverage. MetricX-24 uses plain cell
means (lower is better). Without `--metric`, a table with `--pairs` or `--view` ranks by COMET-22.

The judge metrics come from results/v1/judge/ (judge protocol v1, one judge model, 288 items for a system
with every direction): `judge_preferred`, the share of decided (non-tied) items on which the judge preferred
the system to DeepL API; `judge_net`, wins minus losses as a weighted share of all items; `error_free`, the
weighted share of items with no error counted. They are aggregated like `translate-bench judge` reports a
user's own run (translate_bench/judge.py), on the sampled items of the selected directions.
"""

import json
from statistics import mean

from translate_bench import aggregate, schema
from translate_bench.prepare import parse_pairs

JUDGE_METRICS = {"judge_preferred": ("pairwise", "preferred", "net_95"), "judge_net": ("pairwise", "net", "net_95"),
                 "error_free": ("errors", "error_free", "error_free_95")}
PUBLISHED_METRICS = ("overall", "hard_cases")
METRICS = (*PUBLISHED_METRICS, "comet22", "chrf", "metricx24_ref", "metricx24_qe", *JUDGE_METRICS)


def published(root):
    """{system: {overall, coverage, hard_cases, hard_cases_ci95, hard_cases_items}} from results/v1.1/ and
    results/ltb-v1/.

    `overall` is 0-100 (None without an Overall score) and `coverage` the directions its pillars cover. The
    hard-case pass rate (0-1, None without the track) is the Overall score's pillar: on the items in the
    release's directions, or in the directions a system covers when it covers fewer than 18."""
    from translate_bench import ltb, overall

    entries = schema.read_json(root / overall.PATH)["systems"] if overall.exists(root) else {}
    hard = schema.read_json(root / ltb.BASE / "summary.json")["systems"] if ltb.exists(root) else {}
    n = len(schema.DIRECTIONS)
    out = {}
    for sid in {*entries, *hard}:
        e, h = entries.get(sid) or {}, hard.get(sid) or {}
        covered = h.get("covered") if (e.get("directions") or {}).get("hard_cases", n) < n else None
        figure = covered or h.get("our_directions")
        out[sid] = dict(overall=e.get("overall"), coverage=e.get("coverage", n),
                        hard_cases=figure["passed"] / figure["items"] if figure and figure["items"] else None,
                        hard_cases_ci95=figure["ci95"] if figure else None,
                        hard_cases_items=figure["items"] if figure else None)
    return out


def default_metric(root, pairs=None, view="overall"):
    """The Overall score on the full release when it is published, else COMET-22."""
    from translate_bench import overall

    return "overall" if pairs is None and view == "overall" and overall.exists(root) else "comet22"


def published_table(root, metric, kind=None):
    """Every system ranked by the Overall score or the hard-case pass rate, with the pillars beside it."""
    from translate_bench import ltb, overall

    if metric == "overall" and not overall.exists(root):
        raise ValueError(f"{overall.PATH.as_posix()} is missing; the Overall score needs it")
    if metric == "hard_cases" and not ltb.exists(root):
        raise ValueError(f"{ltb.BASE.as_posix()}/ is missing; the hard cases need it")
    figures = published(root)
    entries = schema.read_json(root / overall.PATH)["systems"] if overall.exists(root) else {}
    summary = schema.read_json(root / "results" / schema.RELEASE / "summary.json")
    judge = schema.read_json(root / "results" / schema.RELEASE / "judge" / "summary.json")
    errors = {e["system"]: e["all"] for e in judge["errors"] if e["judge"] == overall.JUDGE and "all" in e}
    speed = schema.read_json(root / "results" / schema.RELEASE / "speed.json")["systems"]
    rows, missing = [], []
    for system in schema.read_json(root / "configs" / "systems.json")["systems"]:
        sid = system["id"]
        if kind and system["kind"] != kind:
            continue
        f = figures.get(sid) or dict(overall=None, coverage=len(schema.DIRECTIONS), hard_cases=None,
                                     hard_cases_ci95=None, hard_cases_items=None)
        e, ef = entries.get(sid) or {}, errors.get(sid)
        s = speed.get(sid) or {}
        seconds = mean([s["sentence"]["median_s"], s["passage"]["median_s"]]) \
            if system["kind"] == "local" and s.get("sentence") and s.get("passage") else None
        row = dict(system=sid, name=system["name"], kind=system["kind"], score=f[metric], **f,
                   comet22=summary["systems"][sid]["comet22"]["overall_measured"],
                   error_free=ef["error_free"] if ef else None,
                   seconds_per_item=seconds, peak_memory_gib=s.get("peak_memory_gib"),
                   directions=e.get("directions"))
        (rows if row["score"] is not None else missing).append(row)
    rows.sort(key=lambda r: (-r["score"], -(r["comet22"] or 0), r["system"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return dict(metric=metric, view="overall", directions=list(schema.DIRECTIONS), rows=rows, not_covered=missing,
                hard_items=hard_items(root), min_directions=overall.MIN_DIRECTIONS)


def hard_items(root):
    from translate_bench import ltb

    path = root / ltb.BASE / "summary.json"
    return schema.read_json(path)["dataset"]["our_direction_items"] if path.is_file() else None


def pct(x, digits=1):
    return "—" if x is None else f"{100 * x:.{digits}f}%"


def format_published_table(result):
    overall_first = result["metric"] == "overall"
    scope = (f"all {len(result['directions'])} directions · both text types" if overall_first else
             f"{result['hard_items']} Last Translation Benchmark items in the release's directions")
    lines = [f"{result['metric']} · {scope}", "",
             "| # | System | Kind | Overall | COMET-22 | Error-free | Hard cases [95%] | s/item | Peak GiB |",
             "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    n = len(result["directions"])
    for r in result["rows"]:
        ci = r["hard_cases_ci95"]
        hard = pct(r["hard_cases"]) + (f" [{100 * ci[0]:.1f}, {100 * ci[1]:.1f}]" if ci else "")
        name = r["name"] + (f" ({r['coverage']}/{n})" if 0 < r["coverage"] < n else "")
        lines.append(f"| {r['rank']} | {name} | {r['kind']} | {fmt(r['overall'], 1)} | {fmt(r['comet22'], 4)} | "
                     f"{pct(r['error_free'])} | {hard} | {fmt(r['seconds_per_item'], 2)} | "
                     f"{fmt(r['peak_memory_gib'], 2)} |")
    if result["not_covered"]:
        lines.append("")
        if overall_first:
            lines.append(f"No Overall score (it needs every pillar on at least {result['min_directions']} of {n} "
                         "directions): " + ", ".join(
                f"{r['name']} (COMET-22 {r['directions']['standard']}/{n}, judge {r['directions']['reliability']}/{n})"
                if r["directions"] else r["name"] for r in result["not_covered"]))
        else:
            lines.append("No hard-case score: " + ", ".join(r["name"] for r in result["not_covered"]))
    lines.append(published_note(result))
    return "\n".join(lines)


def published_note(result):
    from translate_bench import overall

    items, n = result.get("hard_items"), len(schema.DIRECTIONS)
    return ("Overall: the mean of COMET-22 x 100, the error-free share (%) and the hard-case pass rate (%), for "
            f"systems with every pillar on at least {overall.MIN_DIRECTIONS} of the {n} directions "
            f"(results/v1.1/overall.json). Hard cases: the pass rate on the {items or 'hard-case'} Last Translation "
            "Benchmark items in the release's directions (results/ltb-v1/). A system marked (16/18) is scored over "
            "the directions it covers, in COMET-22 and error-free too, and on the hard-case items in those "
            "directions. Overall and Hard cases are fixed per system and do not follow --pairs or --view.")


def fmt(x, digits):
    return "—" if x is None else f"{x:.{digits}f}"


def metricx_score(rows, view, directions, name):
    cells = {}
    for r in rows:
        if r["status"] == "ok" and r.get(name) is not None:
            cells.setdefault((r["type"], r["direction"]), []).append(r[name])
    values = []
    for d in directions:
        types = schema.TYPES if view == "overall" else (view,)
        if any((t, d) not in cells for t in types):
            return None
        values.append(mean(mean(cells[t, d]) for t in types))
    return mean(values)


def judge_table(root, metric, pairs=None, view="overall", kind=None):
    """Judge v1 aggregates of every system on the sampled items of the selected directions."""
    from translate_bench import judge_results
    from translate_bench.judge import Documents, error_stats, load_sample, pairwise_stats

    if not judge_results.exists(root):
        raise ValueError("results/v1/judge/ is missing; the judge metrics need it")
    summary, files = judge_results.load(root)
    stage, field, interval = JUDGE_METRICS[metric]
    languages = parse_pairs(pairs)
    directions = [d for d in schema.DIRECTIONS if schema.language_of(d) in languages]
    scope = "all" if view == "overall" else view
    documents = Documents(load_sample(root), schema.read_jsonl(root / "datasets" / "items.jsonl"))
    systems = {s["id"]: s for s in schema.read_json(root / "configs" / "systems.json")["systems"]}
    rows, missing = [], []
    for sid, data in files[stage].items():
        system = systems[sid]
        if kind and system["kind"] != kind:
            continue
        chosen = [r for r in data["rows"] if r["direction"] in directions and r["status"] != "missing"]
        types = schema.TYPES if view == "overall" else (view,)
        covered = [d for d in directions if all(any(r["direction"] == d and r["type"] == t for r in chosen)
                                                for t in types)]
        if len(covered) != len(directions):
            missing.append(dict(system=sid, name=system["name"], kind=system["kind"], directions=len(covered)))
            continue
        stats = (pairwise_stats if stage == "pairwise" else error_stats)(chosen, documents)[scope]
        entry = dict(system=sid, name=system["name"], kind=system["kind"], score=stats[field],
                     ci95=stats[interval] if interval.startswith(field) else None, n=stats["n"])
        if stage == "pairwise":
            entry.update(preferred=stats["preferred"], wins=stats["wins"], losses=stats["losses"],
                         ties=stats["ties"], identical=stats["identical"], net=stats["net"], net_95=stats["net_95"])
        rows.append(entry)
    rows.sort(key=lambda r: (-r["score"] if r["score"] is not None else 9e9, r["system"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i if r["score"] is not None else None  # no decided item: preferred is undefined
    return dict(metric=metric, view=view, directions=directions, rows=rows, not_covered=missing,
                judge=summary["judge"]["system"], reference=systems[summary["reference"]]["name"])


def format_judge_table(result):
    pairwise = result["metric"] != "error_free"
    extra = result.get("published")
    head = ("| # | System | Kind | Preferred | Net [95%] | Wins / losses / ties (identical) | n |"
            if pairwise else "| # | System | Kind | Error-free [95%] | n |")
    head += " Overall | Hard cases |" if extra else ""
    lines = [f"{result['metric']} · {result['view']} · {len(result['directions'])} directions · judge "
             f"{result['judge']} (judge v1)", "", head, "| ---: | --- | --- |" + " ---: |" * (head.count("|") - 4)]
    tail = (lambda r: f" {fmt(r['overall'], 1)} | {pct(r['hard_cases'])} |") if extra else (lambda r: "")
    for r in result["rows"]:
        if pairwise:
            preferred = "—" if r["preferred"] is None else f"{r['preferred']:.3f}"
            net = "—" if r["net"] is None else f"{r['net']:+.3f}"
            ci = "" if not r["net_95"] or None in r["net_95"] else f" [{r['net_95'][0]:+.3f}, {r['net_95'][1]:+.3f}]"
            lines.append(f"| {r['rank'] or '—'} | {r['name']} | {r['kind']} | {preferred} | {net}{ci} | {r['wins']} / "
                         f"{r['losses']} / {r['ties']} ({r['identical']}) | {r['n']} |" + tail(r))
        else:
            score = "—" if r["score"] is None else f"{r['score']:.3f}"
            ci = "" if not r["ci95"] or None in r["ci95"] else f" [{r['ci95'][0]:.3f}, {r['ci95'][1]:.3f}]"
            lines.append(f"| {r['rank'] or '—'} | {r['name']} | {r['kind']} | {score}{ci} | {r['n']} |" + tail(r))
    if result["not_covered"]:
        lines.append("")
        lines.append("Not ranked (fewer directions): " + ", ".join(
            f"{r['name']} ({r['directions']}/{len(result['directions'])})" for r in result["not_covered"]))
    lines.append(("Preferred: the share of decided (non-tied) items on which the judge preferred the system to "
                  f"{result['reference']}; net: wins minus losses over all items, weighted; " if pairwise else
                  "Error-free: the weighted share of the system's items in which the judge counted no error; ")
                 + "each direction counts equally and its sentences and passages 50:50. One language-model judge, "
                   "not human ratings.")
    if extra:
        lines.append(published_note(result))
    return "\n".join(lines)


def table(root, metric=None, pairs=None, view="overall", kind=None):
    metric = metric or default_metric(root, pairs, view)
    if metric in PUBLISHED_METRICS:
        if pairs is not None or view != "overall":
            raise ValueError(f"--metric {metric} is one published figure per system over all "
                             f"{len(schema.DIRECTIONS)} directions; --pairs and --view apply to the other metrics")
        return published_table(root, metric, kind)
    result = judge_table(root, metric, pairs, view, kind) if metric in JUDGE_METRICS else \
        score_table(root, metric, pairs, view, kind)
    figures = published(root)
    for r in result["rows"] + result["not_covered"]:
        f = figures.get(r["system"]) or {}
        r.update(overall=f.get("overall"), hard_cases=f.get("hard_cases"))
    result["published"] = bool(figures)
    result["hard_items"] = next((f["hard_cases_items"] for f in figures.values() if f["hard_cases_items"]), None)
    return result


def score_table(root, metric, pairs, view, kind):
    release = aggregate.Release(root)
    languages = parse_pairs(pairs)
    directions = [d for d in schema.DIRECTIONS if schema.language_of(d) in languages]
    keys = aggregate.view_keys(view, directions)
    rows, missing = [], []
    for sid in release.published:
        system = release.systems[sid]
        if kind and system["kind"] != kind:
            continue
        t = release.tables[sid]
        if not t.has(keys):
            have = len([d for d in directions if t.has(aggregate.view_keys(view, [d]))])
            missing.append(dict(system=sid, name=system["name"], kind=system["kind"], directions=have))
            continue
        if metric.startswith("metricx"):
            value = metricx_score(release.rows[sid], view, directions, metric)
            parts = {k: metricx_score(release.rows[sid], k, directions, metric) for k in schema.TYPES}
        else:
            value = aggregate.score(t, view, directions, metric)
            parts = {k: aggregate.score(t, k, directions, metric) for k in schema.TYPES}
        speed = release.speed.get(sid, {})
        seconds = None
        if system["kind"] == "local" and speed.get("sentence") and speed.get("passage"):
            seconds = mean([speed["sentence"]["median_s"], speed["passage"]["median_s"]])
        n = {k: sum(len(t.items["comet22"].get((k, d), {})) for d in directions) for k in schema.TYPES}
        rows.append(dict(system=sid, name=system["name"], kind=system["kind"], score=value, **parts, n=n,
                         seconds_per_item=seconds, peak_memory_gib=speed.get("peak_memory_gib")))
    descending = not metric.startswith("metricx")
    rows.sort(key=lambda r: ((-r["score"] if descending else r["score"]) if r["score"] is not None else 9e9,
                             r["system"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return dict(metric=metric, view=view, directions=directions, rows=rows, not_covered=missing)


def format_table(result):
    digits = 2 if result["metric"] == "chrf" else 4

    def f(x):
        return "—" if x is None else f"{x:.{digits}f}"

    extra = result.get("published")
    lines = [f"{result['metric']} · {result['view']} · {len(result['directions'])} directions",
             "",
             "| # | System | Kind | Score | Sentences | Passages | n (sentences / passages) | s/item | Peak GiB |"
             + (" Overall | Hard cases |" if extra else ""),
             "| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |" + (" ---: | ---: |" if extra else "")]
    for r in result["rows"]:
        seconds = "—" if r["seconds_per_item"] is None else f"{r['seconds_per_item']:.2f}"
        memory = "—" if r["peak_memory_gib"] is None else f"{r['peak_memory_gib']:.2f}"
        lines.append(f"| {r['rank']} | {r['name']} | {r['kind']} | {f(r['score'])} | {f(r['sentence'])} | "
                     f"{f(r['passage'])} | {r['n']['sentence']} / {r['n']['passage']} | {seconds} | {memory} |"
                     + (f" {fmt(r['overall'], 1)} | {pct(r['hard_cases'])} |" if extra else ""))
    if result["not_covered"]:
        lines.append("")
        lines.append("Not ranked (fewer directions): " + ", ".join(
            f"{r['name']} ({r['directions']}/{len(result['directions'])})" for r in result["not_covered"]))
    lines.append("Local s/item is the mean of the sentence and passage medians of the speed benchmark; peak memory "
                 "is not measured for Apple's systems.")
    if extra:
        lines.append(published_note(result))
    return "\n".join(lines)


def main(root, metric=None, pairs=None, view="overall", kind=None, as_json=False, out=print):
    result = table(root, metric, pairs, view, kind)
    metric = result["metric"]
    text = format_published_table(result) if metric in PUBLISHED_METRICS else \
        format_judge_table(result) if metric in JUDGE_METRICS else format_table(result)
    out(json.dumps(aggregate.rounded(result), indent=1) if as_json else text)
    return result
