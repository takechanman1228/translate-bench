"""`translate-bench validate-submission` on a made-up submission to the synthetic release of tests.fixtures."""

import contextlib
import io
import shutil
import tempfile
import unittest
from pathlib import Path

from tests.fixtures import items, make_release, rows_for
from translate_bench import aggregate, cli, schema, submission
from translate_bench.metrics import chrf, comet, metricx
from translate_bench.score import small_summary

ROOT = Path(__file__).resolve().parents[1]
DIRECTIONS = ["en-ja", "ja-en"]


class SubmissionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = make_release(Path(cls.tmp.name) / "release", with_summary=False)
        (cls.root / "tools").mkdir()
        shutil.copy(ROOT / "tools/check_public_tree.py", cls.root / "tools/check_public_tree.py")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(dir=self.tmp.name))
        self.rows = rows_for(dict(id="new-sys", kind="local", quality=0.82),
                             [i for i in items() if i["direction"] in DIRECTIONS], seed=7)
        self.write()

    def write(self, sid="new-sys", summary=True):
        metrics = ["chrf", "comet22", "metricx24"]
        ok = sum(r["status"] == "ok" for r in self.rows)
        measurement = dict(sacrebleu_signature=chrf.SIGNATURE, comet_model=comet.MODEL, comet_revision=comet.REVISION,
                           comet_checkpoint_sha256=comet.CHECKPOINT_SHA256, tokenizer=comet.TOKENIZER,
                           tokenizer_revision=comet.TOKENIZER_REVISION, **metricx.versions())
        inputs = dict(verified_release_items=True)
        schema.write_jsonl(self.folder / "items" / f"{sid}.jsonl", self.rows)
        schema.write_json(self.folder / "system.json", dict(id=sid, name="New System", kind="submitted",
                                                            metrics=metrics, inputs=inputs, predictions_sha256="a" * 64,
                                                            measurement=measurement))
        if summary:
            schema.write_json(self.folder / "summary.json",
                              aggregate.rounded(dict(system=sid, inputs=inputs, **small_summary(self.rows, metrics))))
        schema.write_json(self.folder / "run.json", dict(
            schema="translate-bench/run@1", settings=dict(model="new-sys", prompt=dict(sha256="b" * 64)),
            counts=dict(items=len(self.rows), ok=ok, selected_not_run=0), predictions_sha256="a" * 64))
        both = dict(sentence=DIRECTIONS, passage=DIRECTIONS)
        schema.write_json(self.folder / "registry-entry.json", dict(
            id=sid, name="New System", developer="Example", kind="local", family="New", directions_attempted=both,
            directions_complete=both, passage_sets_attempted=[], prompt_profile="generic-instruction",
            generation=dict(temperature=0), request_mode=dict(items_per_request=1), runtime=dict(name="llama.cpp"),
            weights=dict(repository="example/new", revision="c" * 40, file="new.gguf", sha256="d" * 64)))

    def problems(self):
        return submission.validate(self.root, self.folder)[0]

    def test_valid_submission(self):
        problems, notes, facts = submission.validate(self.root, self.folder)
        self.assertEqual(problems, [])
        self.assertEqual(facts["directions_both_types"], 2)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["--root", str(self.root), "validate-submission", str(self.folder)])
        self.assertEqual(code, 0, out.getvalue() + err.getvalue())
        self.assertIn("validate-submission: 0 problems", out.getvalue())

    def test_texts_are_refused(self):
        (self.folder / "predictions.jsonl").write_text('{"id": "x", "translation": "y"}\n')
        self.assertTrue(any("not part of a submission" in p for p in self.problems()))

    def test_registry_and_coverage(self):
        entry = schema.read_json(self.folder / "registry-entry.json")
        entry["directions_complete"] = dict(sentence=["en-ja"], passage=DIRECTIONS)
        schema.write_json(self.folder / "registry-entry.json", entry)
        self.assertTrue(any("directions_complete differs" in p for p in self.problems()))
        self.write()
        self.rows = self.rows[1:]
        self.write()
        self.assertTrue(any("has 199 of 200 items" in p for p in self.problems()))

    def test_id_already_in_the_release(self):
        shutil.rmtree(self.folder / "items")
        self.write(sid="fam-1b")
        self.assertTrue(any("already a system of the release" in p for p in self.problems()))

    def test_metric_versions_and_run_record(self):
        system = schema.read_json(self.folder / "system.json")
        system["measurement"]["comet_revision"] = "0" * 40
        schema.write_json(self.folder / "system.json", system)
        self.assertTrue(any("COMET-22 comet_revision differ" in p for p in self.problems()))
        self.write()
        run = schema.read_json(self.folder / "run.json")
        run["predictions_sha256"] = "e" * 64
        schema.write_json(self.folder / "run.json", run)
        self.assertTrue(any("different predictions files" in p for p in self.problems()))
        self.write()
        (self.folder / "run.json").unlink()
        self.assertIn("missing run.json", self.problems())

    def test_listed_metric_without_values_fails(self):
        for r in self.rows:
            r["comet22"] = None
        self.write(summary=False)  # the stale summary.json from setUp is kept
        problems = self.problems()
        self.assertIn("items: COMET-22 is listed in system.json but no row has a COMET-22 score", problems)
        self.assertTrue(any(p.startswith("summary.json differs from the rows") for p in problems), problems)
        self.rows = rows_for(dict(id="new-sys", kind="local", quality=0.82),
                             [i for i in items() if i["direction"] in DIRECTIONS], seed=7)
        self.write()
        for r in self.rows:
            r["metricx24_ref"] = r["metricx24_qe"] = None
        self.write()
        self.assertIn("items: MetricX-24 is listed in system.json but no row has a MetricX-24 score",
                      self.problems())

    def test_scope_is_stated(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.main(["--root", str(self.root), "validate-submission", str(self.folder)])
        self.assertIn("Not checked: that the inputs were the release's and that the scores belong to the outputs",
                      out.getvalue())

    def test_summary_is_recomputed(self):
        summary = schema.read_json(self.folder / "summary.json")
        summary["scored"] += 1
        schema.write_json(self.folder / "summary.json", summary)
        self.assertTrue(any(p.startswith("summary.json differs") for p in self.problems()))


class PipelineTest(unittest.TestCase):
    """run (fake server) -> score -> validate-submission on made-up release items with made-up texts."""

    def test_run_score_validate(self):
        from tests.fake_openai import Server
        from tests.fixtures import release_with_inputs
        from translate_bench import run, score

        with tempfile.TemporaryDirectory() as tmp, Server() as server:
            root = release_with_inputs(Path(tmp) / "release", DIRECTIONS)
            out = root / "private/runs/new-sys"
            parsed = cli.build_parser().parse_args(["run", "--model", "new-sys", "--base-url", server.base_url,
                                                    "--out", str(out), "--concurrency", "4"])
            self.assertEqual(run.main(root, parsed, log=lambda m: None), 0)
            folder = root / "private/submission"
            score.main(root, out / "predictions.jsonl", None, "chrf", "new-sys", folder, log=lambda m: None)
            shutil.copy(out / "run.json", folder / "run.json")
            both = dict(sentence=DIRECTIONS, passage=DIRECTIONS)
            schema.write_json(folder / "registry-entry.json", dict(
                id="new-sys", name="New System", developer="Example", kind="cloud", family="New",
                directions_attempted=both, directions_complete=both, passage_sets_attempted=[],
                prompt_profile="generic-instruction", generation=dict(temperature=0), request_mode={}, runtime={}))
            problems, notes, facts = submission.validate(root, folder)
            self.assertEqual(schema.read_json(folder / "run.json")["settings"]["endpoint"], "local endpoint")
            # The same rows scored again by a maintainer agree; a changed output digest does not.
            again = root / "private/rescored"
            score.main(root, out / "predictions.jsonl", None, "chrf", "new-sys", again, log=lambda m: None)
            self.assertEqual(submission.rescored(folder, again), [])
            rows = schema.read_jsonl(again / "items/new-sys.jsonl")
            rows[0]["output_sha256"] = "f" * 64
            schema.write_jsonl(again / "items/new-sys.jsonl", rows)
            self.assertEqual(submission.rescored(folder, again), ["rescoring: output_sha256 differs on 1 items"])
            # An older run record that named the server's address is refused.
            record = schema.read_json(folder / "run.json")
            record["settings"]["endpoint"] = server.base_url + "/chat/completions"
            schema.write_json(folder / "run.json", record)
            leaked = submission.validate(root, folder)[0]
        self.assertEqual(facts["rows"], 440)
        self.assertEqual(problems, ["system.json: no COMET-22 scores; the release ranks by COMET-22 (score with "
                                    "--metrics chrf,comet22,metricx24)"])
        self.assertTrue(any("run.json names a local or private address" in p for p in leaked))


if __name__ == "__main__":
    unittest.main()
