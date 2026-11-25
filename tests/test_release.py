"""Aggregation, verify, compare, score and leaderboard on a synthetic release."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from statistics import mean

from tests.fixtures import make_release
from translate_bench import aggregate, cli, compare, schema, verify


def run_cli(*args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(list(args))
    return code, out.getvalue(), err.getvalue()


class ReleaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = make_release(cls.tmp.name)
        cls.release = aggregate.Release(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_overall_is_equal_weighting(self):
        t = self.release.tables["cloud-a"]
        by_direction = []
        for d in schema.DIRECTIONS:
            s = mean(x[1] for x in t.items["comet22"]["sentence", d].values())
            p = mean(x[1] for x in t.items["comet22"]["passage", d].values())
            by_direction.append((s + p) / 2)
        self.assertAlmostEqual(aggregate.score(t, "overall", schema.DIRECTIONS), mean(by_direction), places=12)

    def test_passage_cell_needs_both_sets(self):
        rows = [r for r in self.release.rows["cloud-a"] if not (r["subset"] == "set-8" and r["direction"] == "en-ko")]
        t = aggregate.Tables(rows)
        self.assertNotIn(("passage", "en-ko"), t.counts)
        self.assertIn(("set-12", "en-ko"), t.subsets["comet22"])
        self.assertIn(("passage", "ko-en"), t.counts)

    def test_failed_items_stay_in_coverage(self):
        block = verify.system_block(self.release, "fam-2b")
        self.assertLess(block["completion"]["scored"], block["completion"]["attempted"])
        self.assertEqual(block["completion"]["attempted"], 18 * 220)

    def test_paired_is_antisymmetric(self):
        draws = self.release.draws()
        keys = aggregate.view_keys("overall", schema.DIRECTIONS)
        ab = aggregate.paired(draws, keys, "cloud-a", "fam-1b")
        ba = aggregate.paired(draws, keys, "fam-1b", "cloud-a")
        self.assertAlmostEqual(ab["delta"], -ba["delta"], places=12)
        self.assertAlmostEqual(ab["ci95"][0], -ba["ci95"][1], places=9)
        self.assertGreater(ab["delta"], 0)

    def test_verify_passes_and_detects_tampering(self):
        code, out, _ = run_cli("--root", str(self.root), "verify")
        self.assertEqual(code, 0, out)
        path = self.root / "results/v1/summary.json"
        original = path.read_text()
        data = json.loads(original)
        data["systems"]["cloud-a"]["comet22"]["overall"] += 0.0001
        path.write_text(json.dumps(data))
        try:
            code, out, _ = run_cli("--root", str(self.root), "verify")
            self.assertEqual(code, 1)
            self.assertIn("cloud-a", out)
        finally:
            path.write_text(original)

    def test_verify_rejects_invalid_rows(self):
        path = self.root / "results/v1/items/cloud-a.jsonl"
        original = path.read_text()
        lines = original.splitlines()
        row = json.loads(lines[0])
        row["status"] = "failed"
        path.write_text("\n".join([json.dumps(row)] + lines[1:]) + "\n")
        try:
            code, out, _ = run_cli("--root", str(self.root), "verify")
            self.assertEqual(code, 1)
            self.assertIn("schema", out)
        finally:
            path.write_text(original)

    def test_leaderboard(self):
        code, out, _ = run_cli("--root", str(self.root), "leaderboard")
        self.assertEqual(code, 0)
        self.assertIn("| 1 | CLOUD-A |", out)
        code, out, _ = run_cli("--root", str(self.root), "leaderboard", "--pairs", "en-ko", "--json")
        self.assertEqual(json.loads(out)["directions"], ["en-ko", "ko-en"])

    def submit(self, out, rows, verified=True):
        """A `score` output directory: the rows and a system.json saying whether the inputs were verified."""
        schema.write_jsonl(Path(out) / "items" / "mine.jsonl", rows)
        schema.write_json(Path(out) / "system.json", dict(id="mine", inputs=dict(verified_release_items=verified)))
        return Path(out)

    def failed(self, r):
        r.update(status="failed", comet22=None, chrf_stats=None, output_sha256=None, metricx24_ref=None,
                 metricx24_qe=None, failure="missing")

    def test_compare_partial_coverage(self):
        # Two directions; 5 sentences of the first one are missing, so only ja-en is ranked.
        rows = [dict(r) for r in self.release.rows["cloud-a"] if r["direction"] in ("en-ja", "ja-en")]
        for r in rows[:5]:
            self.failed(r)
        with tempfile.TemporaryDirectory() as out:
            report = compare.run(self.root, self.submit(out, rows), against=["cloud-a", "local-leader"])
        self.assertEqual(report["directions"], ["en-ja", "ja-en"])
        self.assertEqual(report["missing_items"], {"en-ja": 5})
        self.assertEqual(report["rank_directions"], ["ja-en"])
        self.assertIsNotNone(report["rank"])
        by = {c["system"]: c for c in report["comparisons"]}
        self.assertFalse(by["cloud-a"]["matched"])
        gap = by["cloud-a"]["coverage_differences"][0]
        self.assertEqual((gap["only_submitted"], gap["only_other"]), (0, 5))
        # Same outputs on the common items: the difference is exactly zero.
        self.assertAlmostEqual(by["cloud-a"]["delta"], 0.0, places=12)
        self.assertEqual(by["cloud-a"]["paired_items"], 440 - 5)
        self.assertIn("fam-2b", by)
        text = compare.format_report(report)
        self.assertIn("Not matched with cloud-a", text)
        self.assertIn("Missing items, these directions are not ranked: en-ja 5", text)

    def test_one_item_submission_has_no_rank_and_no_interval(self):
        rows = [dict(r) for r in self.release.rows["cloud-a"] if r["direction"] == "en-ja" and r["type"] == "sentence"]
        for r in rows[1:]:
            self.failed(r)
        with tempfile.TemporaryDirectory() as out:
            report = compare.run(self.root, self.submit(out, rows), view="sentence")
        self.assertIsNone(report["rank"])
        self.assertTrue(report["comparisons"])
        self.assertTrue(all(c["ci95"] is None and c["paired_items"] <= 1 for c in report["comparisons"]))
        self.assertIn("No rank", compare.format_report(report))

    def test_unverified_inputs_are_not_comparable(self):
        rows = [r for r in self.release.rows["fam-1b"] if r["direction"] in ("en-ko", "ko-en")]
        with tempfile.TemporaryDirectory() as out:
            report = compare.run(self.root, self.submit(out, rows, verified=False))
            raw = Path(out) / "raw.jsonl"
            schema.write_jsonl(raw, rows)
            code, text, _ = run_cli("--root", str(self.root), "compare", "--results", str(raw))
        self.assertFalse(report["comparable"])
        self.assertIsNone(report["rank"])
        self.assertEqual(report["comparisons"], [])
        self.assertEqual(code, 0)
        self.assertIn("Not comparable with the published results", text)
        self.assertNotIn("Rank", text)

    def test_rows_outside_the_release(self):
        rows = [dict(r) for r in self.release.rows["fam-1b"] if r["direction"] == "en-ko"]
        rows[0]["doc"] = "another-document"
        with tempfile.TemporaryDirectory() as out:
            path = Path(out) / "raw.jsonl"
            schema.write_jsonl(path, rows)
            report = compare.run(self.root, path)  # not recorded as the release inputs: scores, no rank
            with self.assertRaises(ValueError) as context:
                compare.run(self.root, self.submit(out, rows, verified=True))
        self.assertFalse(report["comparable"])
        self.assertEqual(report["directions"], ["en-ko"])
        self.assertEqual({(c["type"], c["attempted"]) for c in report["cells"]}, {("sentence", 200), ("passage", 20)})
        self.assertIn("| en-ko | sentence | 200 / 200 |", compare.format_report(report))
        self.assertIn("not release items", str(context.exception))

    def test_compare_cli_json_matched(self):
        rows = [r for r in self.release.rows["fam-1b"] if r["direction"] in ("en-ko", "ko-en")]
        with tempfile.TemporaryDirectory() as out:
            code, text, err = run_cli("--root", str(self.root), "compare", "--results", str(self.submit(out, rows)),
                                      "--json")
        self.assertEqual(code, 0, err)
        report = json.loads(text)
        self.assertEqual(report["metric"], "comet22")
        matched = {c["system"]: c["matched"] for c in report["comparisons"]}
        # fam-2b, the local leader, failed some items, so only that comparison is not matched.
        self.assertEqual(matched, {"deepl-api": True, "fam-2b": False, "cloud-a": True})

    def test_metric_defaults_to_what_the_rows_have(self):
        rows = [dict(r, comet22=None) for r in self.release.rows["cloud-a"] if r["direction"] in ("en-ko", "ko-en")]
        with tempfile.TemporaryDirectory() as out:
            report = compare.run(self.root, self.submit(out, rows))
        self.assertEqual(report["metric"], "chrf")
        self.assertIn("no COMET-22", report["metric_choice"])

    def test_direction_without_scored_items(self):
        rows = [dict(r) for r in self.release.rows["cloud-a"] if r["direction"] in ("en-ko", "ko-en")]
        for r in rows:
            if r["direction"] == "en-ko":
                self.failed(r)
        with tempfile.TemporaryDirectory() as out:
            report = compare.run(self.root, self.submit(out, rows))
            self.assertEqual(report["directions"], ["ko-en"])
            self.assertEqual(report["directions_without_scores"], ["en-ko"])
            for r in rows:
                self.failed(r)
            with self.assertRaises(ValueError):
                compare.run(self.root, self.submit(out, rows))

    def test_compare_refuses_missing_cells(self):
        rows = [r for r in self.release.rows["cloud-a"] if r["type"] == "sentence" and r["direction"] == "en-ja"]
        with tempfile.TemporaryDirectory() as out:
            path = self.submit(out, rows)
            with self.assertRaises(ValueError):
                compare.run(self.root, path)
            report = compare.run(self.root, path, view="sentence", metric="chrf")
        self.assertEqual(report["directions"], ["en-ja"])

    def test_score_summary_has_metricx_aggregates(self):
        from translate_bench import score

        rows = [r for r in self.release.rows["cloud-a"] if r["direction"] in ("en-ko", "ko-en")]
        summary = score.small_summary(rows, ["chrf", "metricx24"])
        self.assertEqual(summary["metricx24"], verify.metricx(rows))
        self.assertEqual(summary["metricx24"]["directions"], 2)
        self.assertIsNone(score.small_summary(rows, ["chrf"])["metricx24"])

    def test_speed_tampering_changes_the_summary(self):
        path = self.root / "results/v1/speed.json"
        original = path.read_text()
        data = json.loads(original)
        data["systems"]["fam-1b"]["peak_memory_gib"] = 5.0  # no longer within 4 GiB
        path.write_text(json.dumps(data))
        try:
            code, out, _ = run_cli("--root", str(self.root), "verify")
            self.assertEqual(code, 1)
            self.assertIn("choices", out)
            data["systems"]["fam-1b"]["peak_memory_gib"] = 64.0  # beyond the machine's memory
            path.write_text(json.dumps(data))
            code, out, _ = run_cli("--root", str(self.root), "verify")
            self.assertEqual(code, 1)
            self.assertIn("schema", out)
        finally:
            path.write_text(original)

    def test_reserved_commands_are_not_parsers(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli.main(["run"])


if __name__ == "__main__":
    unittest.main()
