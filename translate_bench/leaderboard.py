"""`translate-bench leaderboard`: the release's table, computed from the item rows.

Systems that cover every selected cell are ranked by the release's aggregation; the others are
listed below with their coverage. MetricX-24 uses plain cell means (lower is better).

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
METRICS = ("comet22", "chrf", "metricx24_ref", "metricx24_qe", *JUDGE_METRICS)


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
    head = ("| # | System | Kind | Preferred | Net [95%] | Wins / losses / ties (identical) | n |"
            if pairwise else "| # | System | Kind | Error-free [95%] | n |")
    lines = [f"{result['metric']} · {result['view']} · {len(result['directions'])} directions · judge "
             f"{result['judge']} (judge v1)", "", head, "| ---: | --- | --- |" + " ---: |" * (head.count("|") - 4)]
    for r in result["rows"]:
        if pairwise:
            preferred = "—" if r["preferred"] is None else f"{r['preferred']:.3f}"
            net = "—" if r["net"] is None else f"{r['net']:+.3f}"
            ci = "" if not r["net_95"] or None in r["net_95"] else f" [{r['net_95'][0]:+.3f}, {r['net_95'][1]:+.3f}]"
            lines.append(f"| {r['rank'] or '—'} | {r['name']} | {r['kind']} | {preferred} | {net}{ci} | {r['wins']} / "
                         f"{r['losses']} / {r['ties']} ({r['identical']}) | {r['n']} |")
        else:
            score = "—" if r["score"] is None else f"{r['score']:.3f}"
            ci = "" if not r["ci95"] or None in r["ci95"] else f" [{r['ci95'][0]:.3f}, {r['ci95'][1]:.3f}]"
            lines.append(f"| {r['rank'] or '—'} | {r['name']} | {r['kind']} | {score}{ci} | {r['n']} |")
    if result["not_covered"]:
        lines.append("")
        lines.append("Not ranked (fewer directions): " + ", ".join(
            f"{r['name']} ({r['directions']}/{len(result['directions'])})" for r in result["not_covered"]))
    lines.append(("Preferred: the share of decided (non-tied) items on which the judge preferred the system to "
                  f"{result['reference']}; net: wins minus losses over all items, weighted; " if pairwise else
                  "Error-free: the weighted share of the system's items in which the judge counted no error; ")
                 + "each direction counts equally and its sentences and passages 50:50. One language-model judge, "
                   "not human ratings.")
    return "\n".join(lines)


def table(root, metric="comet22", pairs=None, view="overall", kind=None):
    if metric in JUDGE_METRICS:
        return judge_table(root, metric, pairs, view, kind)
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

    lines = [f"{result['metric']} · {result['view']} · {len(result['directions'])} directions",
             "",
             "| # | System | Kind | Score | Sentences | Passages | n (sentences / passages) | s/item | Peak GiB |",
             "| ---: | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |"]
    for r in result["rows"]:
        seconds = "—" if r["seconds_per_item"] is None else f"{r['seconds_per_item']:.2f}"
        memory = "—" if r["peak_memory_gib"] is None else f"{r['peak_memory_gib']:.2f}"
        lines.append(f"| {r['rank']} | {r['name']} | {r['kind']} | {f(r['score'])} | {f(r['sentence'])} | "
                     f"{f(r['passage'])} | {r['n']['sentence']} / {r['n']['passage']} | {seconds} | {memory} |")
    if result["not_covered"]:
        lines.append("")
        lines.append("Not ranked (fewer directions): " + ", ".join(
            f"{r['name']} ({r['directions']}/{len(result['directions'])})" for r in result["not_covered"]))
    lines.append("Local s/item is the mean of the sentence and passage medians of the speed benchmark; peak memory "
                 "is not measured for Apple's systems.")
    return "\n".join(lines)


def main(root, metric="comet22", pairs=None, view="overall", kind=None, as_json=False, out=print):
    result = table(root, metric, pairs, view, kind)
    text = format_judge_table(result) if metric in JUDGE_METRICS else format_table(result)
    out(json.dumps(aggregate.rounded(result), indent=1) if as_json else text)
    return result
