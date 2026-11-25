"""`translate-bench prepare`: download the test sets and assemble the benchmark inputs.

Downloads each upstream file from its publisher (NTREX-128 from Microsoft Translator on GitHub,
WMT12/13 from statmt.org, WMT23 from the WMT conference repository, WMT24++ from Google's Hugging
Face dataset), verifies its SHA-256, rebuilds every item's source and reference, verifies their
SHA-256 against datasets/items.jsonl and writes sentences.tsv and passages.tsv. A full prepare
also recomputes the frozen selections and checks the two files against datasets/release.json.

No release test set needs registration or an access agreement. The texts stay in the output and
download directories; inside a checkout, both must be in a directory Git ignores.
"""

import hashlib
import json
import os
import sys
from pathlib import Path

from translate_bench import schema
from translate_bench.datasets import build, manifests, selection, sources

SCOPES = {"all": ("sentence", "passage"), "sentences": ("sentence",), "passages": ("passage",)}
NAMES = {"sentence": "sentences.tsv", "passage": "passages.tsv"}


def parse_pairs(value):
    if value in (None, "all"):
        return list(schema.LANGUAGES)
    pairs = []
    for part in value.split(","):
        part = part.strip()
        language = part[3:] if part.startswith("en-") else part
        if language not in schema.LANGUAGES:
            raise ValueError(f"Unknown language pair {part!r}; expected one of "
                             + ", ".join(f"en-{k}" for k in schema.LANGUAGES))
        pairs.append(language)
    return pairs


def check_location(path, root, option="--out"):
    return schema.safe_location(path, root, option)


def main(root, out=None, pairs=None, scope="all", downloads=None, check_selection=None, log=None):
    log = log or (lambda m: print(m, file=sys.stderr, flush=True))
    out = check_location(Path(out) if out else root / "private" / "inputs", root, "--out")
    cache = check_location(Path(downloads) if downloads else out / "downloads", root, "--downloads")
    out.mkdir(parents=True, exist_ok=True)
    data = manifests(root)
    languages = parse_pairs(pairs)
    types = SCOPES[scope]
    full = set(languages) == set(schema.LANGUAGES) and types == SCOPES["all"]
    chosen = [i for i in data["items"] if i["type"] in types and schema.language_of(i["direction"]) in languages]
    keys = sorted({k for i in chosen for k in build.files_for(i)})
    check_selection = full if check_selection is None else check_selection
    if check_selection:
        keys = sorted(set(keys) | set(selection.needed()))
    paths = sources.fetch_all(keys, data["sources"], cache, log)
    paths = {k: str(v) for k, v in paths.items()}
    if check_selection:
        problems = selection.check(data["selection"], data["items"], paths)
        if problems:
            raise ValueError("Selection check failed: " + "; ".join(problems))
        log("Recomputed every frozen selection from the upstream files: no difference.")
    written = {}
    for kind in types:
        rows = build.assemble([i for i in chosen if i["type"] == kind], paths)
        content = build.tsv_bytes(rows)
        digest = hashlib.sha256(content).hexdigest()
        if full:
            expected = data["release"][NAMES[kind]]
            if (digest, len(rows)) != (expected["sha256"], expected["rows"]):
                raise ValueError(f"{NAMES[kind]} differs from datasets/release.json")
        target = out / NAMES[kind]
        temporary = target.with_suffix(".tmp")
        temporary.write_bytes(content)
        os.replace(temporary, target)
        written[NAMES[kind]] = dict(rows=len(rows), sha256=digest)
        log(f"Wrote {target} ({len(rows):,} items, every source and reference SHA-256 verified)")
    manifest = dict(release=schema.RELEASE, languages=languages, scope=scope, complete=full, files=written)
    (out / "inputs.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    if full:
        log("Both files match datasets/release.json byte for byte.")
    return out, written
