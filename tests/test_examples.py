"""The synthetic example set: it is not release text, and `score` then `compare` work on it from the CLI."""

import contextlib
import csv
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from sacrebleu.metrics import CHRF

from translate_bench import cli, schema

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "examples/external-predictions/data"


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def rows():
    out = []
    for name in ("sentences.tsv", "passages.tsv"):
        with (DATA / name).open(encoding="utf-8", newline="") as stream:
            out += list(csv.DictReader(stream, delimiter="\t"))
    return out


def run_cli(*args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(list(args))
    return code, out.getvalue(), err.getvalue()


class SyntheticSetTest(unittest.TestCase):
    def test_not_release_items_or_texts(self):
        manifest = schema.read_jsonl(ROOT / "datasets/items.jsonl")
        ids = {i["id"] for i in manifest}
        digests = {i["source_sha256"] for i in manifest} | {i["reference_sha256"] for i in manifest}
        synthetic = rows()
        self.assertEqual(len(synthetic), 20)
        for row in synthetic:
            self.assertTrue(row["id"].startswith("synthetic/"))
            self.assertNotIn(row["id"], ids)
            self.assertNotIn(sha(row["source"]), digests)
            self.assertNotIn(sha(row["reference"]), digests)
            self.assertEqual(row["domain"], "synthetic")
        predictions = schema.read_jsonl(DATA / "predictions.jsonl")
        self.assertTrue(all(p["id"].startswith("synthetic/") for p in predictions))

    def test_score_then_compare(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "score"
            code, text, err = run_cli("score", "--predictions", str(DATA / "predictions.jsonl"), "--inputs", str(DATA),
                                      "--system-name", "example", "--out", str(out))
            self.assertEqual(code, 0, err)
            self.assertIn("19 of 20 items scored", text)
            self.assertIn("NOT the verified release inputs", text)
            self.assertNotIn("(partial)", text)
            summary = json.loads((out / "summary.json").read_text())
            self.assertFalse(summary["inputs"]["verified_release_items"])
            hyps = {p["id"]: p["translation"] for p in schema.read_jsonl(DATA / "predictions.jsonl")}
            cell = [r for r in rows() if r["tgt"] == "de" and r["id"].startswith("synthetic/s")]
            expected = CHRF(word_order=2).corpus_score([hyps[r["id"]] for r in cell], [[r["reference"] for r in cell]])
            self.assertAlmostEqual(summary["cells"]["en-de"]["sentence"]["chrf"], expected.score, places=5)
            code, text, err = run_cli("compare", "--results", str(out))
            self.assertEqual(code, 0, err)
            self.assertIn("Not comparable with the published results", text)
            self.assertIn("| en-ja | sentence | 7 / 8 |", text)
            self.assertNotIn("Rank", text)
            code, text, err = run_cli("compare", "--results", str(out), "--json")
            self.assertFalse(json.loads(text)["comparable"])


if __name__ == "__main__":
    unittest.main()
