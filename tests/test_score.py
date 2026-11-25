"""`translate-bench score` with chrF++ on a tiny made-up set."""

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from sacrebleu.metrics import CHRF

from translate_bench import schema, score
from translate_bench.datasets.build import FIELDS


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


PAIRS = [
    ("The bridge reopened after repairs.", "Die Brücke wurde nach Reparaturen wieder geöffnet.",
     "Die Brücke ist nach den Reparaturen wieder offen."),
    ("A new library opens downtown.", "In der Innenstadt öffnet eine neue Bibliothek.",
     "Eine neue Bibliothek öffnet in der Innenstadt."),
    ("Tickets sold out within an hour.", "Die Karten waren innerhalb einer Stunde ausverkauft.",
     "Die Tickets waren in einer Stunde ausverkauft."),
]


class ScoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "configs").mkdir()
        (self.root / "configs/systems.json").write_text('{"systems": []}')
        (self.root / "results/v1").mkdir(parents=True)
        manifest = [dict(id=f"made-up/{i}/en-de", direction="en-de", type="sentence", subset=None, doc=f"d{i % 2}",
                         domain="news", origin={}, source_sha256=sha(src), reference_sha256=sha(ref))
                    for i, (src, ref, _) in enumerate(PAIRS)]
        schema.write_jsonl(self.root / "datasets/items.jsonl", manifest)
        self.inputs = self.root / "private/inputs"
        self.write_inputs(self.inputs, [(src, ref) for src, ref, _ in PAIRS])
        digest = hashlib.sha256((self.inputs / "sentences.tsv").read_bytes()).hexdigest()
        schema.write_json(self.root / "datasets/release.json",
                          dict(files={"sentences.tsv": dict(sha256=digest, rows=3)}))

    def write_inputs(self, folder, pairs):
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / "sentences.tsv").open("w", encoding="utf-8", newline="") as stream:
            w = csv.DictWriter(stream, FIELDS, delimiter="\t")
            w.writeheader()
            for i, (src, ref) in enumerate(pairs):
                w.writerow(dict(id=f"made-up/{i}/en-de", src="en", tgt="de", source=src, reference=ref,
                                domain="news", doc=f"d{i % 2}"))

    def tearDown(self):
        self.tmp.cleanup()

    def predictions(self, rows):
        path = self.root / "private/predictions.jsonl"
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        return path

    def test_chrf_matches_sacrebleu_and_writes_rows(self):
        path = self.predictions([dict(id=f"made-up/{i}/en-de", translation=hyp) for i, (_, _, hyp) in enumerate(PAIRS)])
        out = self.root / "private/out"
        sid, rows, summary = score.main(self.root, path, self.inputs, "chrf", "My System", out, log=lambda m: None)
        self.assertEqual(sid, "my-system")
        self.assertEqual(schema.rows_problems(rows, sid), [])
        expected = CHRF(word_order=2).corpus_score([h for *_, h in PAIRS], [[r for _, r, _ in PAIRS]]).score
        self.assertAlmostEqual(summary["cells"]["en-de"]["sentence"]["chrf"], expected, places=9)
        self.assertTrue((out / "items/my-system.jsonl").is_file())
        self.assertNotIn("Brücke", (out / "items/my-system.jsonl").read_text(encoding="utf-8"))

    def test_inputs_are_verified_against_the_release(self):
        path = self.predictions([dict(id=f"made-up/{i}/en-de", translation=hyp) for i, (_, _, hyp) in enumerate(PAIRS)])
        out = self.root / "private/out"
        score.main(self.root, path, self.inputs, "chrf", "verified", out, log=lambda m: None)
        inputs = json.loads((out / "system.json").read_text())["inputs"]
        self.assertTrue(inputs["verified_release_items"])
        self.assertTrue(inputs["files"]["sentences.tsv"]["matches_release_file"])
        # The same ids with the references of two items swapped: scored, but not the release inputs.
        swapped = [(PAIRS[0][0], PAIRS[1][1]), (PAIRS[1][0], PAIRS[0][1]), PAIRS[2][:2]]
        other = self.root / "private/swapped"
        self.write_inputs(other, swapped)
        logs = []
        score.main(self.root, path, other, "chrf", "swapped", out, log=logs.append)
        inputs = json.loads((out / "system.json").read_text())["inputs"]
        self.assertFalse(inputs["verified_release_items"])
        self.assertEqual(inputs["text_or_label_mismatches"], 2)
        self.assertTrue(any("NOT the verified release inputs" in line for line in logs))

    def test_out_must_not_be_published(self):
        path = self.predictions([dict(id="made-up/0/en-de", translation="x")])
        with self.assertRaises(ValueError):
            score.main(self.root, path, self.inputs, "chrf", "x", self.root / "results/mine", log=lambda m: None)

    def test_missing_and_failed_items_count(self):
        path = self.predictions([dict(id="made-up/0/en-de", translation=PAIRS[0][2]),
                                 dict(id="made-up/1/en-de", status="error", translation=None)])
        _, rows, summary = score.main(self.root, path, self.inputs, "chrf", "partial", None, log=lambda m: None)
        self.assertEqual([r["status"] for r in rows], ["ok", "failed", "failed"])
        self.assertEqual([r.get("failure") for r in rows], [None, "error", "missing"])
        self.assertEqual((summary["attempted"], summary["scored"]), (3, 1))

    def test_unknown_and_duplicate_ids(self):
        with self.assertRaises(ValueError):
            score.main(self.root, self.predictions([dict(id="nope", translation="x")]), self.inputs, "chrf", "x",
                       None, log=lambda m: None)
        with self.assertRaises(ValueError):
            score.main(self.root, self.predictions([dict(id="made-up/0/en-de", translation="x")] * 2), self.inputs,
                       "chrf", "x", None, log=lambda m: None)

    def test_optional_metrics_report_missing_extra(self):
        from translate_bench.metrics import MissingDependency, require

        with self.assertRaises(MissingDependency) as context:
            require(["surely_not_installed_module"], "comet")
        self.assertIn(".[comet]", str(context.exception))


if __name__ == "__main__":
    unittest.main()
