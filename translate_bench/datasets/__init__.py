"""The release's test sets: upstream files, item manifests and the frozen selections.

datasets/sources.json lists every upstream file with its URL, revision and SHA-256;
datasets/items.jsonl lists every item with its source document, the upstream segments it is
built from and the SHA-256 of its source and reference texts; datasets/selection.json records
the frozen selection rules and their historical seed strings; datasets/release.json gives the
SHA-256 of the two assembled input files. No text is stored in the repository.
"""

from translate_bench import schema


def manifests(root):
    base = root / "datasets"
    return dict(
        sources=schema.read_json(base / "sources.json")["files"],
        items=schema.read_jsonl(base / "items.jsonl"),
        selection=schema.read_json(base / "selection.json"),
        release=schema.read_json(base / "release.json")["files"],
    )
