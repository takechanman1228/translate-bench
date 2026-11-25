"""`translate-bench score`: score your translations of the prepared inputs like the release.

Predictions are UTF-8 JSONL, one object per line with `id` and `translation` (and optionally
`status`; anything other than "ok" is a failure). Every item of a direction and text type you
submitted at least one translation for is part of your coverage: a missing, empty or failed
translation stays in the denominator.

The inputs are checked against the release: each item's source and reference against the SHA-256
in datasets/items.jsonl, and the two files against datasets/release.json. The result records
whether the inputs were the verified release inputs; `translate-bench compare` ranks and matches
only results that were. Other inputs are scored all the same, as your own test set.

The output directory gets `items/<system>.jsonl` in the schema of results/v1/items, `system.json`
and `summary.json`.
"""

import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from translate_bench import aggregate, schema
from translate_bench.datasets.build import FIELDS
from translate_bench.metrics import chrf as chrf_metric

METRIC_NAMES = ("chrf", "comet22", "metricx24")
FILES = {"sentences.tsv": "sentence", "passages.tsv": "passage"}


def parse_metrics(value):
    names = [x.strip() for x in value.split(",") if x.strip()]
    aliases = {"comet": "comet22", "metricx": "metricx24", "chrf++": "chrf"}
    names = [aliases.get(n, n) for n in names]
    if not names or set(names) - set(METRIC_NAMES) or len(set(names)) != len(names):
        raise ValueError("--metrics takes a comma-separated list of chrf, comet22 and metricx24")
    if "chrf" not in names:
        names.insert(0, "chrf")  # the item rows always carry the chrF++ statistics
    return names


def system_id(name):
    sid = re.sub(r"[^a-z0-9.]+", "-", name.lower()).strip("-.")
    if not sid or not schema.SYSTEM_ID.fullmatch(sid):
        raise ValueError(f"Cannot make a system id from {name!r}; use letters and digits")
    return sid


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_inputs(folder):
    """{id: row} with the file type of each row, and {file: sha256, rows} of the files read."""
    items, files = {}, {}
    for name, kind in FILES.items():
        path = Path(folder) / name
        if not path.is_file():
            continue
        raw = path.read_bytes()
        files[name] = dict(sha256=hashlib.sha256(raw).hexdigest(), rows=0)
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream, delimiter="\t", strict=True)
            if tuple(reader.fieldnames or ()) != FIELDS:
                raise ValueError(f"{path}: expected the columns {', '.join(FIELDS)}")
            for row in reader:
                if row["id"] in items:
                    raise ValueError(f"{path}: duplicate id {row['id']}")
                items[row["id"]] = dict(row, type=kind)
                files[name]["rows"] += 1
    if not files:
        raise ValueError(f"No sentences.tsv or passages.tsv in {folder}; run `translate-bench prepare` first")
    return items, files


def verify_inputs(items, files, manifest, release_files):
    """Whether the inputs are the release's: every item known, with the published text digests."""
    by_id = {i["id"]: i for i in manifest}
    unknown = mismatched = 0
    for sid, row in items.items():
        item = by_id.get(sid)
        if item is None:
            unknown += 1
            continue
        same = (item["direction"] == f"{row['src']}-{row['tgt']}" and item["type"] == row["type"]
                and item["doc"] == row["doc"] and sha(row["source"]) == item["source_sha256"]
                and sha(row["reference"]) == item["reference_sha256"])
        mismatched += not same
    for name, info in files.items():
        expected = release_files.get(name, {})
        info["matches_release_file"] = info["sha256"] == expected.get("sha256")
    return dict(verified_release_items=not unknown and not mismatched, items=len(items), not_in_release=unknown,
                text_or_label_mismatches=mismatched, files=files)


def read_predictions(path, items):
    predictions = {}
    with Path(path).open(encoding="utf-8-sig") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                raise ValueError(f"{path}: invalid JSON at line {number}") from None
            if not isinstance(row, dict) or not isinstance(row.get("id"), str):
                raise ValueError(f"{path}: line {number} needs an object with a string id")
            sid = row["id"]
            if sid not in items:
                raise ValueError(f"{path}: line {number}: {sid!r} is not an item of the prepared inputs")
            if sid in predictions:
                raise ValueError(f"{path}: duplicate id {sid}")
            status = row.get("status", "ok")
            translation = row.get("translation")
            if status == "ok" and not isinstance(translation, str):
                raise ValueError(f"{path}: line {number}: translation must be a string")
            predictions[sid] = (status, translation if status == "ok" else None)
    if not predictions:
        raise ValueError(f"{path}: no predictions")
    return predictions


def frame(items, manifest):
    """Item descriptions for the inputs: the release manifest where the id is a release item, else the TSV."""
    by_id = {i["id"]: i for i in manifest}
    out = {}
    for sid, row in items.items():
        item = by_id.get(sid)
        direction = f"{row['src']}-{row['tgt']}"
        schema.parse_direction(direction)
        if item is not None and (item["direction"], item["type"]) == (direction, row["type"]):
            out[sid] = dict(id=sid, direction=direction, type=row["type"], subset=item["subset"], doc=item["doc"])
        else:
            out[sid] = dict(id=sid, direction=direction, type=row["type"], subset=None, doc=row["doc"] or sid)
    return out


def build_rows(items, predictions, described, metrics, log):
    """Item rows for every input in a submitted (type, direction) cell, in input order."""
    submitted = {(described[sid]["type"], described[sid]["direction"]) for sid in predictions}
    chrf = chrf_metric.metric()
    rows, texts = [], []
    for sid, item in described.items():
        if (item["type"], item["direction"]) not in submitted:
            continue
        status, translation = predictions.get(sid, ("missing", None))
        failure = status if status != "ok" else ("empty" if not translation.strip() else None)
        row = dict(item, status="ok" if failure is None else "failed", comet22=None, chrf_stats=None,
                   output_sha256=None)
        if failure is None:
            source, reference = items[sid]["source"], items[sid]["reference"]
            row["chrf_stats"] = chrf_metric.statistics(chrf, translation, reference)
            row["output_sha256"] = chrf_metric.output_sha256(translation)
            texts.append((len(rows), source, reference, translation))
        else:
            row["failure"] = failure
        rows.append(row)
    measurement = dict(sacrebleu_signature=chrf_metric.signature())
    if "comet22" in metrics:
        from translate_bench.metrics import comet

        keep = comet.eligible([t[1:] for t in texts])
        log(f"COMET-22: {len(keep)} of {len(texts)} translations within the {comet.MAX_TOKENS}-token limit")
        for i, value in zip(keep, comet.scores([texts[i][1:] for i in keep])):
            rows[texts[i][0]]["comet22"] = value
        measurement.update(comet.versions())
    if "metricx24" in metrics:
        from translate_bench.metrics import metricx

        ref = metricx.scores([(s, t, r) for _, s, r, t in texts], with_reference=True)
        qe = metricx.scores([(s, t) for _, s, r, t in texts], with_reference=False)
        for (index, *_), a, b in zip(texts, ref, qe):
            rows[index]["metricx24_ref"] = round(a, 4)
            rows[index]["metricx24_qe"] = round(b, 4)
        measurement.update(metricx.versions())
    return rows, measurement


def small_summary(rows, metrics):
    """Coverage and scores of the user's cells, aggregated like the release."""
    from translate_bench.verify import metricx as metricx_summary

    table = aggregate.Tables(rows)
    metric = "comet22" if "comet22" in metrics else "chrf"
    cells = defaultdict(dict)
    groups = defaultdict(list)
    for r in rows:
        groups[r["type"], r["direction"]].append(r)
    for (kind, d), members in sorted(groups.items(), key=lambda x: (schema.DIRECTIONS.index(x[0][1]), x[0][0])):
        items = aggregate.eligible(members, metric)
        cells[d][kind] = dict(
            attempted=len(members), ok=sum(r["status"] == "ok" for r in members), scored=len(items),
            complete=(kind, d) in table.counts,
            comet22=aggregate.cell_score(items, "comet22") if metric == "comet22" else None,
            chrf=aggregate.cell_score(aggregate.eligible(members, "chrf"), "chrf"))
    scores = {}
    for view in aggregate.VIEWS:
        directions = [d for d in table.directions(None if view == "overall" else view)
                      if all(table.items[metric].get(k) for k in aggregate.view_keys(view, [d]))]
        scores[view] = dict(directions=len(directions), **{
            m: aggregate.score(table, view, directions, m) if directions else None
            for m in (("comet22", "chrf") if metric == "comet22" else ("chrf",))})
    attempted = len(rows)
    scored = sum(r["status"] == "ok" and (metric != "comet22" or r["comet22"] is not None) for r in rows)
    return dict(attempted=attempted, scored=scored, completion_rate=scored / attempted if attempted else None,
                scores=scores, metricx24=metricx_summary(rows) if "metricx24" in metrics else None,
                cells=cells, incomplete_cells=[list(x) for x in table.incomplete])


def main(root, predictions, inputs=None, metrics="chrf", system_name=None, out=None, log=print):
    metrics = parse_metrics(metrics)
    sid = system_id(system_name or Path(predictions).stem)
    if out:
        out = schema.safe_location(out, root, "--out")
    inputs = Path(inputs) if inputs else root / "private" / "inputs"
    items, files = read_inputs(inputs)
    manifest = schema.read_jsonl(root / "datasets" / "items.jsonl")
    release_files = schema.read_json(root / "datasets" / "release.json")["files"]
    check = verify_inputs(items, files, manifest, release_files)
    preds = read_predictions(predictions, items)
    rows, measurement = build_rows(items, preds, frame(items, manifest), metrics, log)
    problems = schema.rows_problems(rows, sid)
    if problems:
        raise ValueError("; ".join(problems[:5]))
    summary = small_summary(rows, metrics)
    raw = Path(predictions).read_bytes()
    system = dict(id=sid, name=system_name or sid, kind="submitted", metrics=metrics, inputs=check,
                  predictions_sha256=hashlib.sha256(raw).hexdigest(), measurement=measurement)
    if out:
        schema.write_jsonl(out / "items" / f"{sid}.jsonl", rows)
        schema.write_json(out / "system.json", system)
        schema.write_json(out / "summary.json", aggregate.rounded(dict(system=sid, inputs=check, **summary)))
    print_table(sid, summary, metrics, measurement, check, log)
    return sid, rows, summary


def print_table(sid, summary, metrics, measurement, check, log):
    use_comet = "comet22" in metrics
    head = ["Direction", "Type", "Scored / items"] + (["COMET-22"] if use_comet else []) + ["chrF++"]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for d, kinds in summary["cells"].items():
        for kind, c in kinds.items():
            partial = check["verified_release_items"] and not c["complete"]  # fewer items than the release cell
            cells = [d, kind, f"{c['scored']} / {c['attempted']}" + (" (partial)" if partial else "")]
            if use_comet:
                cells.append("—" if c["comet22"] is None else f"{c['comet22']:.4f}")
            cells.append("—" if c["chrf"] is None else f"{c['chrf']:.2f}")
            lines.append("| " + " | ".join(cells) + " |")
    log(f"{sid}: {summary['scored']:,} of {summary['attempted']:,} items scored "
        f"(completion {summary['completion_rate']:.3f})")
    if check["verified_release_items"]:
        log("Inputs: the verified release inputs (every source and reference matches datasets/items.jsonl).")
    else:
        log(f"Inputs: NOT the verified release inputs ({check['not_in_release']} items not in the release, "
            f"{check['text_or_label_mismatches']} with other texts or labels); the scores are not comparable with "
            "the published results.")
    log("\n".join(lines))
    for view, s in summary["scores"].items():
        if s["directions"]:
            values = [f"{k} {v:.4f}" if k == "comet22" else f"{k} {v:.2f}" for k, v in s.items()
                      if k != "directions" and v is not None]
            log(f"{view}: {', '.join(values)} over {s['directions']} direction(s), release weighting")
    if summary["metricx24"]:
        m = summary["metricx24"]
        log(f"MetricX-24 (lower is better): with reference {m['metricx24_ref']:.4f}, without {m['metricx24_qe']:.4f} "
            f"over {m['directions']} direction(s)")
    log(f"chrF++: sacreBLEU {measurement['sacrebleu_signature']}")
    if use_comet:
        log(f"COMET-22: {measurement['comet_model']}@{measurement['comet_revision']}")
