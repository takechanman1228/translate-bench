"""A synthetic release in a temporary directory: made-up ids, documents and scores, no real data."""

import random
from pathlib import Path

from translate_bench import schema
from translate_bench.verify import SPEED_SEED

SYSTEMS = (
    dict(id="fam-1b", kind="local", family="Fam", parameters=1_000_000_000, quality=0.80),
    dict(id="fam-2b", kind="local", family="Fam", parameters=2_000_000_000, quality=0.83),
    dict(id="cloud-a", kind="cloud", family="Vendor", parameters=None, quality=0.85),
    dict(id="deepl-api", kind="cloud", family="DeepL", parameters=None, quality=0.84),
)


def items():
    """The frame: 200 sentences from 20 documents and 20 passages per direction."""
    out = []
    for d in schema.DIRECTIONS:
        for i in range(200):
            out.append(dict(id=f"syn-s/{i}/{d}", direction=d, type="sentence", subset=None, doc=f"news-{i % 20}"))
        for j in range(20):
            subset = None if schema.is_core(d) else ("set-8" if j < 8 else "set-12")
            doc = f"core-{j}-{schema.language_of(d)}" if schema.is_core(d) else f"doc-{j}"
            out.append(dict(id=f"syn-p/{j}/{d}", direction=d, type="passage", subset=subset, doc=doc))
    return out


def stats(rng):
    values = []
    for _ in range(8):
        hyp, ref = rng.randint(20, 60), rng.randint(20, 60)
        values += [hyp, ref, rng.randint(0, min(hyp, ref))]
    return values


def rows_for(system, frame, seed, fail_every=0):
    rng = random.Random(seed)
    rows = []
    for n, item in enumerate(frame):
        ok = not (fail_every and n % fail_every == 0)
        rows.append(dict(item, status="ok" if ok else "failed",
                         comet22=round(min(0.99, max(0.3, rng.gauss(system["quality"], 0.05))), 6) if ok else None,
                         chrf_stats=stats(rng) if ok else None,
                         output_sha256=f"{rng.getrandbits(256):064x}" if ok else None,
                         metricx24_ref=round(rng.uniform(1, 6), 4) if ok else None,
                         metricx24_qe=round(rng.uniform(1, 6), 4) if ok else None,
                         provenance="release", execution="serial" if system["kind"] == "local" else "batched"))
    return rows


def make_release(root, with_summary=True):
    root = Path(root)
    frame = items()
    systems = []
    for k, s in enumerate(SYSTEMS):
        everywhere = {t: list(schema.DIRECTIONS) for t in schema.TYPES}
        systems.append(dict(id=s["id"], name=s["id"].upper(), developer="Example", kind=s["kind"], family=s["family"],
                            parameters=s["parameters"], weights=None, directions_attempted=everywhere,
                            directions_complete=everywhere, passage_sets_attempted=["set-12", "set-8"]))
        schema.write_jsonl(root / "results/v1/items" / f"{s['id']}.jsonl",
                           rows_for(s, frame, seed=k, fail_every=97 if k == 1 else 0))
    schema.write_json(root / "configs/systems.json", dict(schema="translate-bench/systems@1", systems=systems))
    schema.write_jsonl(root / "datasets/items.jsonl", [dict(i, domain="news", origin={}) for i in frame])
    speed = dict(selection=dict(seed_string=SPEED_SEED, per_type=4), systems={})
    for s in SYSTEMS:
        if s["kind"] == "local":
            speed["systems"][s["id"]] = dict(
                kind="local", date="2026-11-23", machine="test machine", runtime=dict(name="llama.cpp"), load_s=1.0,
                peak_memory_gib=3.0 if s["id"] == "fam-1b" else 7.5, memory_measured=True, memory_note="rss",
                download_bytes=1, start_conditions_met=True, flagged=[False, False, False],
                sentence=speed_part(0.5), passage=speed_part(1.5), items=None)
        else:
            speed["systems"][s["id"]] = dict(kind="cloud", reference=dict(
                sentence=dict(seconds_per_item=1.0, estimated_usd_per_1000_items=0.5, tokens_per_item=100.0,
                              directions=18),
                passage=dict(seconds_per_item=3.0, estimated_usd_per_1000_items=1.5, tokens_per_item=900.0,
                             directions=18)))
    for sid, entry in speed["systems"].items():
        if entry["kind"] == "local":
            entry["items"] = speed_items(root, sid, speed["selection"])
    schema.write_json(root / "results/v1/speed.json", speed)
    if with_summary:
        from translate_bench import aggregate, verify

        schema.write_json(root / "results/v1/summary.json", verify.build_summary(aggregate.Release(root)))
    return root


def speed_part(median):
    return dict(attempts=12, successful=12, failures=0, median_s=median, p90_s=median * 2,
                repetition_median_s=[median, median, median], repetition_spread_s=0.0,
                median_output_tokens_per_s=None, median_decode_tokens_per_s=None, median_output_chars_per_s=None)


def speed_items(root, sid, selection):
    import hashlib

    rows = schema.read_jsonl(root / "results/v1/items" / f"{sid}.jsonl")
    out = {}
    for kind in schema.TYPES:
        lanes = {}
        for r in rows:
            if r["type"] == kind:
                lanes.setdefault(r["direction"], []).append(r["id"])
        queues = [sorted(v, key=lambda i: hashlib.sha256((selection["seed_string"] + i).encode()).digest())
                  for _, v in sorted(lanes.items())]
        picked, depth = [], 0
        while len(picked) < selection["per_type"]:
            picked += [q[depth] for q in queues if depth < len(q)][: selection["per_type"] - len(picked)]
            depth += 1
        out[kind] = picked
    return out


def release_with_inputs(root, directions):
    """A synthetic release whose items in `directions` have made-up texts, prepared as inputs in private/inputs.

    `score` sees these inputs as the verified release inputs, so `compare` ranks them and
    `validate-submission` accepts them, all without any real text."""
    import csv
    import hashlib
    import json
    import shutil

    from translate_bench.datasets.build import FIELDS

    def sha(text):
        return hashlib.sha256(text.encode()).hexdigest()

    real = Path(__file__).resolve().parents[1]
    root = make_release(root, with_summary=False)
    (root / "tools").mkdir(exist_ok=True)
    shutil.copy(real / "tools/check_public_tree.py", root / "tools/check_public_tree.py")
    registry = schema.read_json(root / "configs/systems.json")
    registry["prompt_profiles"] = json.loads((real / "configs/systems.json").read_text())["prompt_profiles"]
    schema.write_json(root / "configs/systems.json", registry)
    chosen = [i for i in items() if i["direction"] in directions]
    text = {i["id"]: (f"Made-up source of {i['id']}.", f"Made-up reference of {i['id']}.") for i in chosen}
    manifest = [dict(i, domain="news", origin={}, source_sha256=sha(text[i["id"]][0]),
                     reference_sha256=sha(text[i["id"]][1])) for i in chosen]
    schema.write_jsonl(root / "datasets/items.jsonl", manifest)
    schema.write_json(root / "datasets/release.json", dict(files={}))
    inputs = root / "private/inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    for kind, name in (("sentence", "sentences.tsv"), ("passage", "passages.tsv")):
        with (inputs / name).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, FIELDS, delimiter="\t")
            writer.writeheader()
            for i in manifest:
                if i["type"] == kind:
                    src, tgt = schema.parse_direction(i["direction"])
                    writer.writerow(dict(id=i["id"], src=src, tgt=tgt, source=text[i["id"]][0],
                                         reference=text[i["id"]][1], domain="news", doc=i["doc"]))
    return root
