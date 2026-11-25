"""`translate-bench compare`: place a scored system among the release's 40.

The score uses the release's aggregation (sentence and passage cells 50:50 per direction,
directions weighted equally) over the directions the submission covers.

A submission is comparable with the published results only if `translate-bench score` recorded
that it was scored on the verified release inputs. Then:

- it is ranked only on the directions where it scored every item of the compared types, among
  the published systems with those cells; directions with missing items are shown with the
  number missing and left out of the rank;
- it is compared with named systems by paired differences, cell by cell on the items both scored,
  with the release's document draws; n is the number of paired items, and no interval is given
  below 20 source documents;
- a comparison is "matched" only when both systems scored exactly the same items, every item of
  those cells.

Otherwise its scores are printed, labelled as not comparable with the published results, with no
rank and no comparison.
"""

import json
from pathlib import Path
from types import SimpleNamespace

from translate_bench import aggregate, schema

DEFAULT_AGAINST = ("deepl-api", "local-leader", "cloud-leader")
MIN_CLUSTERS = 20


def load_submitted(root, path):
    """(system entry, rows) from a `translate-bench score` output directory or an item-row file.

    Rows scored on the verified release inputs must be release items with the release's direction,
    type, set and document; rows scored on other inputs are reported as not comparable."""
    path = Path(path)
    if path.is_dir():
        files = sorted((path / "items").glob("*.jsonl"))
        if len(files) != 1:
            raise ValueError(f"{path}: expected exactly one items/*.jsonl")
        system_file = path / "system.json"
        system = schema.read_json(system_file) if system_file.is_file() else dict(id=files[0].stem)
        rows = schema.read_jsonl(files[0])
    else:
        rows = schema.read_jsonl(path)
        system = dict(id=path.stem)
    problems = schema.rows_problems(rows, system["id"])
    if problems:
        raise ValueError("; ".join(problems[:5]))
    manifest = {i["id"]: (i["direction"], i["type"], i["subset"], i["doc"])
                for i in schema.read_jsonl(root / "datasets" / "items.jsonl")}
    outside = [r["id"] for r in rows if manifest.get(r["id"]) != (r["direction"], r["type"], r["subset"], r["doc"])]
    system.setdefault("name", system["id"])
    system["kind"] = "submitted"
    system["comparable"] = bool((system.get("inputs") or {}).get("verified_release_items"))
    if outside and system["comparable"]:
        raise ValueError(f"{len(outside)} rows are not release items with the release's direction, type, set and "
                         f"document (e.g. {outside[0]}), although system.json says they were scored on the release "
                         "inputs")
    return system, rows


def unranked(sid, system, rows, metric, why, view):
    """Scores of rows that are not comparable with the release: every cell as submitted, no rank."""
    cells = {}
    for r in rows:
        cells.setdefault((r["type"], r["direction"]), []).append(r)
    items = {key: aggregate.eligible(members, metric) for key, members in cells.items()}
    table = SimpleNamespace(items={metric: items})
    directions = [d for d in schema.DIRECTIONS if all(items.get(k) for k in aggregate.view_keys(view, [d]))]
    listed = [dict(type=k, direction=d, attempted=len(cells[k, d]), scored=len(items[k, d]),
                   score=aggregate.cell_score(items[k, d], metric))
              for d in schema.DIRECTIONS for k in schema.TYPES if (k, d) in cells]
    return dict(system=sid, name=system["name"], metric=metric, metric_choice=why, view=view, comparable=False,
                directions=directions, directions_without_scores=[], missing_items={},
                score=aggregate.score(table, view, directions, metric) if directions else None,
                n={k: sum(len(items[k, d]) for d in directions if (k, d) in items) for k in schema.TYPES},
                rank=None, rank_directions=[], comparisons=[], cells=listed,
                note=("Not comparable with the published results: the rows do not record that they were scored on "
                      "the verified release inputs. Scores per cell as submitted; no rank and no comparison."))


def choose_metric(rows, metric):
    if metric:
        return metric, "requested"
    if any(r["status"] == "ok" and r["comet22"] is not None for r in rows):
        return "comet22", "chosen: the rows have COMET-22 scores"
    return "chrf", "chosen: the rows have no COMET-22 scores"


def coverage(release, sid, view, metric):
    """Directions with complete cells, those with every item scored, and missing counts per direction."""
    table = release.tables[sid]
    complete = table.directions(None if view == "overall" else view)
    missing, scored = {}, []
    for d in complete:
        keys = aggregate.view_keys(view, [d])
        gap = sum(table.counts[k][0] - len(table.items[metric][k]) for k in keys)
        if gap:
            missing[d] = gap
        if all(table.items[metric][k] for k in keys):
            scored.append(d)
    full = [d for d in complete if d not in missing]
    return complete, scored, full, missing


def clusters(release, keys, a, b, metric):
    docs = set()
    for key in keys:
        common = set(release.tables[a].items[metric][key]) & set(release.tables[b].items[metric][key])
        docs |= {release.tables[a].items[metric][key][i][0] for i in common}
    return len(docs)


def gaps(release, keys, a, b, metric):
    out = []
    for key in keys:
        sa, sb = set(release.tables[a].items[metric][key]), set(release.tables[b].items[metric][key])
        if sa != sb:
            out.append(dict(type=key[0], direction=key[1], only_submitted=len(sa - sb), only_other=len(sb - sa),
                            common=len(sa & sb)))
    return out


def run(root, results, against=None, metric=None, view="overall"):
    release = aggregate.Release(root)
    system, rows = load_submitted(root, results)
    metric, why = choose_metric(rows, metric)
    sid = system["id"] if system["id"] not in release.systems else system["id"] + "-submitted"
    if not system["comparable"]:
        return unranked(sid, system, rows, metric, why, view)
    release.add(sid, system, rows)
    table = release.tables[sid]
    complete, scored, full, missing = coverage(release, sid, view, metric)
    if not complete:
        have = ", ".join(f"{k}: {len(table.directions(k))}" for k in schema.TYPES)
        raise ValueError(f"No complete {view} cell (complete directions {have}); try --view sentence or passage")
    if not scored:
        raise ValueError(f"No scored item for {metric} in the {view} cells; check --metric")
    report = dict(system=sid, metric=metric, metric_choice=why, view=view, comparable=system["comparable"],
                  directions=scored, directions_without_scores=[d for d in complete if d not in scored],
                  missing_items=missing, score=aggregate.score(table, view, scored, metric),
                  n={k: sum(len(table.items[metric][(k, d)]) for d in scored if (k, d) in table.items[metric])
                     for k in schema.TYPES},
                  rank=None, rank_directions=[], comparisons=[],
                  incomplete_cells=[list(x) for x in table.incomplete])
    if full:
        keys = aggregate.view_keys(view, full)
        members = aggregate.covering(release, keys)
        values = {s: aggregate.score(release.tables[s], view, full, metric) for s in members}
        values[sid] = aggregate.score(table, view, full, metric)
        order = sorted(values, key=lambda s: (-values[s], s))
        report.update(rank=order.index(sid) + 1, ranked=len(order), rank_directions=full, rank_score=values[sid],
                      rank_by_kind={k: [s for s in order if s == sid or release.kind(s) == k].index(sid) + 1
                                    for k in schema.KINDS})
    keys = aggregate.view_keys(view, scored)
    members = aggregate.covering(release, keys)
    values = {s: aggregate.score(release.tables[s], view, scored, metric) for s in members}
    leaders = {k: min((s for s in members if release.kind(s) == k), key=lambda s: (-values[s], s), default=None)
               for k in schema.KINDS}
    targets = []
    for name in against or DEFAULT_AGAINST:
        target = {"local-leader": leaders["local"], "cloud-leader": leaders["cloud"]}.get(name, name)
        if target is None or target not in release.published:
            raise ValueError(f"Unknown system {name!r}; see configs/systems.json")
        if target not in members:
            raise ValueError(f"{target} does not cover the {len(scored)} directions of the submission")
        if target not in targets:
            targets.append(target)
    draws = release.draws(metric)
    for other in targets:
        result = aggregate.paired(draws, keys, sid, other, metric)
        n_docs = clusters(release, keys, sid, other, metric)
        differences = gaps(release, keys, sid, other, metric)
        entry = dict(system=other, name=release.systems[other]["name"], kind=release.kind(other), score=values[other],
                     delta=result and result["delta"], paired_items=result["n"] if result else 0, documents=n_docs,
                     ci95=None, matched=not differences and not missing, coverage_differences=differences)
        if result and n_docs >= MIN_CLUSTERS:
            entry["ci95"] = result["ci95"]
        elif result:
            entry["ci_note"] = f"no interval: {n_docs} source documents, fewer than {MIN_CLUSTERS}"
        report["comparisons"].append(entry)
    report["note"] = ("Ranks use point estimates on the fully covered directions; differences are paired on common "
                      "items with 95% intervals from 2,000 document draws, not adjusted for multiple comparisons.")
    return report


def format_report(r):
    chrf = r["metric"] == "chrf"

    def fmt(x):
        return "—" if x is None else f"{x:.2f}" if chrf else f"{x:.4f}"

    def sign(x):
        return "—" if x is None else f"{x:+.2f}" if chrf else f"{x:+.4f}"

    total_missing = sum(n for d, n in r["missing_items"].items() if d in r["directions"])
    lines = [f"{r['system']}: {r['metric']} ({r['metric_choice']}) {r['view']} {fmt(r['score'])} over "
             f"{len(r['directions'])} direction(s) ({', '.join(r['directions'])})"
             + (f", {total_missing} items without a score" if total_missing else "")]
    if r["directions_without_scores"]:
        lines.append("No scored item, left out: " + ", ".join(r["directions_without_scores"]))
    if not r["comparable"]:
        if not r["directions"]:
            lines[0] = f"{r['system']}: {r['metric']} ({r['metric_choice']}); no direction has every {r['view']} cell"
        lines += ["", "| Direction | Type | Scored / items | Score |", "| --- | --- | --- | --- |"]
        lines += [f"| {c['direction']} | {c['type']} | {c['scored']} / {c['attempted']} | {fmt(c['score'])} |"
                  for c in r["cells"]]
        lines.append(r["note"])
        return "\n".join(lines)
    if r["rank"]:
        lines.append(f"Rank {r['rank']} of {r['ranked']} on {len(r['rank_directions'])} fully covered direction(s) "
                     f"({fmt(r['rank_score'])}; among local systems {r['rank_by_kind']['local']}, among cloud systems "
                     f"{r['rank_by_kind']['cloud']}, counting it).")
    else:
        lines.append("No rank: no direction has every item scored.")
    partial = {d: n for d, n in r["missing_items"].items() if d in r["directions"]}
    if partial:
        listed = ", ".join(f"{d} {n}" for d, n in partial.items())
        lines.append(f"Missing items, these directions are not ranked: {listed}")
    lines += ["", "| Against | Score | Submitted − other [95%] | Paired items (documents) | Matched |",
              "| --- | --- | --- | --- | --- |"]
    for c in r["comparisons"]:
        ci = f" [{sign(c['ci95'][0])}, {sign(c['ci95'][1])}]" if c["ci95"] else " (no interval)"
        lines.append(f"| {c['name']} ({c['system']}) | {fmt(c['score'])} | {sign(c['delta'])}{ci} | "
                     f"{c['paired_items']} ({c['documents']}) | {'yes' if c['matched'] else 'no'} |")
    for c in r["comparisons"]:
        if c.get("ci_note"):
            lines.append(f"{c['system']}: {c['ci_note']}.")
        if c["coverage_differences"]:
            parts = [f"{g['direction']} {g['type']}: {g['only_submitted']} only submitted, {g['only_other']} only "
                     f"{c['system']}" for g in c["coverage_differences"]]
            lines.append(f"Not matched with {c['system']}, the difference uses common items only: " + "; ".join(parts))
    lines.append(r["note"])
    return "\n".join(lines)


def judge_section(root, folder, view="overall", against=None):
    """A user's `translate-bench judge` results beside the published judge v1 results, in the same terms.

    `folder` is the --out folder of `translate-bench judge`: errors.json (error annotation of the user's
    translations) and, when the user judged against a second prediction file, pairwise.json."""
    from translate_bench import judge_results

    folder = Path(folder)
    if not judge_results.exists(root):
        raise ValueError("results/v1/judge/ is missing; nothing to compare the judge results with")
    published, _ = judge_results.load(root)
    names = {s["id"]: s["name"] for s in schema.read_json(root / "configs" / "systems.json")["systems"]}
    scope = "all" if view == "overall" else view
    section = dict(scope=scope, published_judge=published["judge"]["system"], reference=published["reference"],
                   errors=None, pairwise=None, published=[])
    for stage in ("errors", "pairwise"):
        path = folder / f"{stage}.json"
        if path.is_file():
            mine = schema.read_json(path)
            section[stage] = dict(system=mine["system"], against=mine.get("against"), judge=mine["judge"]["model"],
                                  complete=mine["complete"], result=mine["results"].get(scope))
    if not section["errors"] and not section["pairwise"]:
        raise ValueError(f"{folder}: no errors.json or pairwise.json from `translate-bench judge`")
    error_free = {e["system"]: e.get(scope) for e in published["errors"]}
    kinds = {e["system"]: e["kind"] for e in published["errors"]}
    leaders = {k: max((s for s in error_free if kinds[s] == k and error_free[s]
                       and error_free[s].get("error_free") is not None),
                      key=lambda s: error_free[s]["error_free"], default=None) for k in schema.KINDS}
    wanted = [published["reference"], leaders["local"], leaders["cloud"], *(against or [])]
    for sid in dict.fromkeys(w for w in wanted if w in error_free):
        pair = judge_results.entry(published, "pairwise", sid, scope)
        e = error_free[sid]
        section["published"].append(dict(system=sid, name=names.get(sid, sid), error_free=(e or {}).get("error_free"),
                                          error_free_95=(e or {}).get("error_free_95"), n=(e or {}).get("n"),
                                          preferred=(pair or {}).get("preferred"), net=(pair or {}).get("net")))
    same = all(x is None or x["judge"] == section["published_judge"] for x in (section["errors"], section["pairwise"]))
    reference = names.get(section["reference"], section["reference"])
    section["note"] = (f"The published values come from {section['published_judge']} through its vendor's "
                       "command-line client; results are on the same scale only with the same judge model reached the "
                       "same way" + ("" if same else ", and this run used another judge model") + ". Pairwise "
                       f"preferred shares are comparable only when the other predictions are {reference}'s "
                       "translations of the release inputs.")
    return section


def judge_value(x, spec=".3f"):
    """A judge aggregate, or a dash when it is undefined (no decided items, no interval)."""
    return "—" if x is None else format(x, spec)


def judge_interval(ci, spec=".3f"):
    return "" if not ci or None in ci else f" [{format(ci[0], spec)}, {format(ci[1], spec)}]"


def format_judge_section(j):
    lines = ["", f"Judge protocol v1 ({j['scope']}): error-free is the weighted share of items with no error counted; "
                 "preferred is the share of decided (non-tied) items on which the judge preferred the system "
                 "(undefined when every item is a tie)."]
    if j["errors"]:
        e = j["errors"]["result"]
        lines.append(f"Your run ({j['errors']['system']}, judge {j['errors']['judge']}"
                     + ("" if j["errors"]["complete"] else ", incomplete") + "): "
                     + ("no items in this scope" if e is None else
                        f"error-free {judge_value(e.get('error_free'))}{judge_interval(e.get('error_free_95'))}, "
                        f"n {e['n']}"))
    if j["pairwise"]:
        p = j["pairwise"]["result"]
        lines.append(f"Your pairwise run ({j['pairwise']['system']} against {j['pairwise']['against']}, judge "
                     f"{j['pairwise']['judge']}): " + ("no items in this scope" if p is None else
                                                      f"preferred {judge_value(p.get('preferred'))}, net "
                                                      f"{judge_value(p.get('net'), '+.3f')}"
                                                      f"{judge_interval(p.get('net_95'), '+.3f')}, wins "
                                                      f"{p['wins']} / losses {p['losses']} / ties {p['ties']} / "
                                                      f"identical {p.get('identical', 0)} of n {p['n']}"))
    lines += ["", f"| Published ({j['published_judge']}) | Error-free [95%] | n | Preferred to the reference | Net |",
              "| --- | --- | --- | --- | --- |"]
    for r in j["published"]:
        ef = judge_value(r["error_free"]) + ("" if r["error_free"] is None else judge_interval(r["error_free_95"]))
        preferred = "reference" if r["system"] == j["reference"] else judge_value(r["preferred"])
        lines.append(f"| {r['name']} ({r['system']}) | {ef} | {r['n'] or '—'} | {preferred} | "
                     f"{judge_value(r['net'], '+.3f')} |")
    lines.append(j["note"])
    return "\n".join(lines)


def main(root, results, against=None, metric=None, view="overall", as_json=False, out=print, judge=None):
    report = run(root, results, against, metric, view)
    if judge:
        report["judge"] = judge_section(root, judge, view, against)
    text = format_report(report) + (format_judge_section(report["judge"]) if judge else "")
    out(json.dumps(aggregate.rounded(report), indent=1) if as_json else text)
    return report
