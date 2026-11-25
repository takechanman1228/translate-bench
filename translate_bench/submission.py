"""`translate-bench validate-submission DIR`: the file checks a maintainer runs on a submitted system.

A submission is a directory with:

- items/<system-id>.jsonl: the item rows `translate-bench score --out` writes, in the schema of
  results/v1/items (scores and output SHA-256, no text);
- system.json: written by the same command (metric versions, the input check, the SHA-256 of the
  predictions file);
- run.json: written by `translate-bench run` (model, endpoint label, prompt and its SHA-256, decoding
  settings, counts), or written by hand for translations made another way;
- registry-entry.json: the system's entry for configs/systems.json;
- summary.json (optional): written by `score`; it is recomputed and compared.

What it establishes: the files follow the schema, every attempted cell is complete, the required
metrics have values, and the files agree with each other (rows and registry entry, run record and
scoring record, summary and rows). What it cannot establish: that the inputs were the release's and
that the scores are what the metrics give for the outputs. The submission carries no text, so those
are the contributor's attestation until a maintainer reproduces them, either by scoring the
predictions file the contributor shares privately (`--rescored DIR` then compares every row) or by
running the system again from its weights or endpoint and settings.

Problems block a submission; notes do not. No text belongs in a submission: no predictions,
inputs or references. Every file also goes through the repository's public-tree check, and run.json
must not name a local or private address.
"""

import importlib.util
from pathlib import Path
from urllib.parse import urlsplit

from translate_bench import aggregate, schema
from translate_bench.endpoint import host_kind
from translate_bench.metrics import chrf, comet, metricx

REQUIRED = ("system.json", "run.json", "registry-entry.json")
RUN_KEYS = ("model", "prompt", "generation", "counts")
COMET_PINS = dict(comet_model=comet.MODEL, comet_revision=comet.REVISION,
                  comet_checkpoint_sha256=comet.CHECKPOINT_SHA256, tokenizer=comet.TOKENIZER,
                  tokenizer_revision=comet.TOKENIZER_REVISION)
METRICX_PINS = metricx.versions()
SCOPE = ("Checked: schema, coverage, required metric values, and consistency between the submitted files. Not "
         "checked: that the inputs were the release's and that the scores belong to the outputs; that is the "
         "contributor's attestation until a maintainer reproduces it (CONTRIBUTING.md).")
TOLERANCE = dict(comet22=1e-3, metricx24_ref=1e-2, metricx24_qe=1e-2)


def urls(value):
    """Every string in a JSON value that looks like a URL."""
    if isinstance(value, dict):
        for v in value.values():
            yield from urls(v)
    elif isinstance(value, list):
        for v in value:
            yield from urls(v)
    elif isinstance(value, str) and "://" in value:
        yield value


def public_tree_checker(root):
    path = root / "tools" / "check_public_tree.py"
    spec = importlib.util.spec_from_file_location("check_public_tree", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate(root, folder):
    """(problems, notes, facts) for a submission directory."""
    folder = Path(folder)
    problems, notes, facts = [], [], {}
    if not folder.is_dir():
        return [f"{folder}: not a directory"], notes, facts
    checker = public_tree_checker(root)
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        relative = path.relative_to(folder).as_posix()
        if path.name.startswith("predictions") or path.suffix in (".tsv", ".txt"):
            problems.append(f"{relative}: translations and texts are not part of a submission")
            continue
        for issue in sorted(checker.inspect(f"submission/{relative}", path.read_bytes())):
            problems.append(f"{relative}: {issue} (public-tree check)")
    files = sorted((folder / "items").glob("*.jsonl"))
    missing = [name for name in REQUIRED if not (folder / name).is_file()]
    if len(files) != 1:
        missing.insert(0, "items/<system-id>.jsonl (exactly one)")
    if missing:
        return problems + [f"missing {name}" for name in missing], notes, facts
    sid = files[0].stem
    facts["system"] = sid
    system = schema.read_json(folder / "system.json")
    run = schema.read_json(folder / "run.json")
    entry = schema.read_json(folder / "registry-entry.json")
    rows = schema.read_jsonl(files[0])
    registry = schema.read_json(root / "configs" / "systems.json")

    # Identity
    if system.get("id") != sid:
        problems.append(f"system.json id {system.get('id')!r} differs from items/{sid}.jsonl")
    if entry.get("id") != sid:
        problems.append(f"registry-entry.json id {entry.get('id')!r} differs from items/{sid}.jsonl")
    if sid in {s["id"] for s in registry["systems"]}:
        problems.append(f"{sid} is already a system of the release; choose another id")

    # Rows: schema, release frame, coverage
    problems += schema.rows_problems(rows, f"items/{sid}")
    frame = {i["id"]: (i["direction"], i["type"], i["subset"], i["doc"])
             for i in schema.read_jsonl(root / "datasets" / "items.jsonl")}
    outside = [r.get("id") for r in rows if frame.get(r.get("id")) != (r.get("direction"), r.get("type"),
                                                                        r.get("subset"), r.get("doc"))]
    if outside:
        problems.append(f"items/{sid}: {len(outside)} rows are not release items with the release's direction, "
                        f"type, set and document (e.g. {outside[0]})")
    if problems and any(p.startswith(f"items/{sid} row") for p in problems):
        return problems, notes, facts
    table = aggregate.Tables(rows)
    for kind, direction, subset, have, size in table.incomplete:
        problems.append(f"items/{sid}: {kind} cell {direction}{' ' + subset if subset else ''} has {have} of {size} "
                        "items; every attempted cell lists every item, failed ones included")
    attempted = {k: sorted({r["direction"] for r in rows if r["type"] == k}, key=schema.DIRECTIONS.index)
                 for k in schema.TYPES}
    complete = {k: table.directions(k) for k in schema.TYPES}
    sets = sorted({r["subset"] for r in rows if r["subset"]})
    ok = sum(r["status"] == "ok" for r in rows)
    scored = sum(r["status"] == "ok" and r["comet22"] is not None for r in rows)
    facts.update(rows=len(rows), ok=ok, comet22_scored=scored, directions_both_types=len(table.directions()),
                 complete=complete)

    # Registry entry
    problems += [p.replace("configs/systems.json", "registry-entry.json")
                 for p in schema.registry_problems(dict(systems=[entry]))]
    if entry.get("directions_attempted") != attempted:
        problems.append("registry-entry.json: directions_attempted differs from the item rows "
                        f"(rows: {attempted})")
    if entry.get("directions_complete") != complete:
        problems.append(f"registry-entry.json: directions_complete differs from the item rows (rows: {complete})")
    if entry.get("passage_sets_attempted") != sets:
        problems.append(f"registry-entry.json: passage_sets_attempted differs from the item rows (rows: {sets})")
    if entry.get("kind") == "local":
        weights = entry.get("weights") or {}
        lacking = [k for k in ("repository", "revision", "file", "sha256") if not weights.get(k)]
        if lacking:
            notes.append(f"registry-entry.json: a local system should record weights {', '.join(lacking)}")
    for key in ("prompt_profile", "generation", "request_mode", "runtime"):
        if entry.get(key) is None:
            notes.append(f"registry-entry.json: no {key}")

    # Scoring: the release's inputs and metric versions
    inputs = system.get("inputs") or {}
    if not inputs.get("verified_release_items"):
        problems.append("system.json: not scored on the verified release inputs (inputs.verified_release_items)")
    metrics = system.get("metrics") or []
    measurement = system.get("measurement") or {}
    if measurement.get("sacrebleu_signature") != chrf.SIGNATURE:
        problems.append(f"system.json: chrF++ signature differs from the release's {chrf.SIGNATURE}")
    if "comet22" not in metrics:
        problems.append("system.json: no COMET-22 scores; the release ranks by COMET-22 (score with "
                        "--metrics chrf,comet22,metricx24)")
    else:
        changed = [k for k, v in COMET_PINS.items() if measurement.get(k) != v]
        if changed:
            problems.append(f"system.json: COMET-22 {', '.join(changed)} differ from the release")
        if ok and not scored:
            problems.append("items: COMET-22 is listed in system.json but no row has a COMET-22 score")
        elif ok and scored < ok:
            notes.append(f"{ok - scored} successful outputs have no COMET-22 score (over the 512-token limit)")
    if "metricx24" in metrics:
        changed = [k for k, v in METRICX_PINS.items() if measurement.get(k) != v]
        if changed:
            problems.append(f"system.json: MetricX-24 {', '.join(changed)} differ from the release")
        if ok and not any(r["status"] == "ok" and r.get("metricx24_ref") is not None for r in rows):
            problems.append("items: MetricX-24 is listed in system.json but no row has a MetricX-24 score")
    else:
        notes.append("no MetricX-24 scores; the release has them for every system (--metrics ...,metricx24)")

    # Run record
    if any(host_kind(urlsplit(u).hostname) != "public" for u in urls(run)):
        problems.append("run.json names a local or private address; `translate-bench run` records it as "
                        "'local endpoint' or 'private endpoint' unless --record-endpoint is given")
    if run.get("schema") != "translate-bench/run@1":
        lacking = [k for k in RUN_KEYS if k not in run]
        if lacking:
            problems.append(f"run.json: not written by `translate-bench run` and lacks {', '.join(lacking)}")
        else:
            notes.append("run.json: written by hand (translations made outside `translate-bench run`)")
    else:
        settings = run.get("settings") or {}
        if run.get("predictions_sha256") != system.get("predictions_sha256"):
            problems.append("run.json and system.json name different predictions files (predictions_sha256); "
                            "score the run's predictions.jsonl as it is")
        elif (run.get("counts") or {}).get("ok") != ok:
            problems.append(f"run.json counts {run['counts'].get('ok')} ok items, the rows {ok}")
        if not settings.get("model") or not settings.get("prompt", {}).get("sha256"):
            problems.append("run.json: settings lack the model or the prompt's SHA-256")
        if (run.get("counts") or {}).get("selected_not_run"):
            notes.append(f"run.json: {run['counts']['selected_not_run']} selected items were not run")

    # The summary score wrote, recomputed
    if (folder / "summary.json").is_file():
        from translate_bench.score import small_summary
        from translate_bench.verify import differences

        published = schema.read_json(folder / "summary.json")
        try:
            recomputed = aggregate.rounded(dict(system=sid, inputs=inputs, **small_summary(rows, metrics)))
        except (TypeError, ValueError, KeyError):
            problems.append("summary.json cannot be recomputed from the rows (a listed metric lacks values)")
        else:
            found = differences(published, recomputed)
            if found:
                problems.append(f"summary.json differs from the rows: {found[0]}")
    else:
        notes.append("no summary.json (optional)")
    return problems, notes, facts


def rescored(folder, other):
    """Problems where a maintainer's rescoring (a `score --out` directory from the shared predictions) differs."""
    mine = {r["id"]: r for r in schema.read_jsonl(next((Path(folder) / "items").glob("*.jsonl")))}
    files = sorted((Path(other) / "items").glob("*.jsonl"))
    if len(files) != 1:
        return [f"--rescored {other}: expected exactly one items/*.jsonl"]
    theirs = {r["id"]: r for r in schema.read_jsonl(files[0])}
    problems = []
    if set(mine) != set(theirs):
        problems.append(f"rescoring: {len(set(mine) ^ set(theirs))} item ids are in only one of the two")
    differ = {}
    for sid in set(mine) & set(theirs):
        a, b = mine[sid], theirs[sid]
        for key in ("status", "output_sha256", "chrf_stats"):
            if a.get(key) != b.get(key):
                differ[key] = differ.get(key, 0) + 1
        for key, tolerance in TOLERANCE.items():
            x, y = a.get(key), b.get(key)
            if (x is None) != (y is None) or (x is not None and abs(x - y) > tolerance):
                differ[key] = differ.get(key, 0) + 1
    for key, n in sorted(differ.items()):
        problems.append(f"rescoring: {key} differs on {n} items")
    return problems


def main(root, folder, out=print, rescoring=None):
    problems, notes, facts = validate(root, folder)
    if rescoring and facts.get("rows"):
        problems += rescored(folder, rescoring)
    if facts.get("rows"):
        c = facts["complete"]
        out(f"{facts['system']}: {facts['rows']:,} item rows, {facts['ok']:,} ok, {facts['comet22_scored']:,} with "
            f"COMET-22; complete directions: {len(c['sentence'])} sentence, {len(c['passage'])} passage, "
            f"{facts['directions_both_types']} with both types")
    for line in problems:
        out(f"problem: {line}")
    for line in notes:
        out(f"note: {line}")
    if rescoring and facts.get("rows"):
        out("rescoring: every row compared with the maintainer's scoring of the shared predictions")
    out(SCOPE)
    out(f"validate-submission: {len(problems)} problems, {len(notes)} notes")
    return 1 if problems else 0
