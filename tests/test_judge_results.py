"""The published judge v1 results: verify recomputes them from the rows and catches tampering."""

import copy
import unittest
from pathlib import Path

from translate_bench import judge_results
from translate_bench.verify import differences

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(judge_results.exists(ROOT), "no judge results in this checkout")
class JudgeResultsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary, cls.files = judge_results.load(ROOT)

    def test_published_results_recompute(self):
        self.assertEqual(judge_results.check(ROOT), [])

    def test_complete_sample_has_equal_weights(self):
        e = judge_results.entry(self.summary, "pairwise", "gpt-6.1-terra")
        self.assertEqual(e["n"], 288)
        self.assertAlmostEqual(e["net"], (e["wins"] - e["losses"]) / e["n"], places=4)
        self.assertAlmostEqual(e["preferred"], e["wins"] / (e["wins"] + e["losses"]), places=4)

    def test_a_changed_verdict_changes_the_aggregates(self):
        files = copy.deepcopy(self.files)
        rows = files["pairwise"]["hy-mt2-30b-a3b"]["rows"]
        row = next(r for r in rows if r["winner"] == "against")
        row["winner"] = "system"
        again = judge_results.aggregate(ROOT, files)
        self.assertTrue(differences(self.summary["pairwise"], again["pairwise"]))

    def test_a_changed_error_count_changes_the_aggregates(self):
        files = copy.deepcopy(self.files)
        row = next(r for r in files["errors"]["deepl-api"]["rows"] if r["status"] == "annotated")
        row["critical"] += 1
        again = judge_results.aggregate(ROOT, files)
        self.assertTrue(differences(self.summary["errors"], again["errors"]))

    def test_row_problems(self):
        files = copy.deepcopy(self.files)
        files["pairwise"]["gpt-6.1-terra"]["rows"][0]["winner"] = "deepl"
        self.assertTrue(judge_results.row_problems(ROOT, files, self.summary))
        files = copy.deepcopy(self.files)
        files["errors"]["gpt-6.1-terra"]["rows"].pop()
        self.assertTrue(judge_results.row_problems(ROOT, files, self.summary))

    def test_leaderboard_judge_metrics(self):
        from translate_bench import leaderboard

        table = leaderboard.table(ROOT, "error_free")
        best = max((e for e in self.summary["errors"] if e["all"]["directions"] == 18),
                   key=lambda e: e["all"]["error_free"])
        self.assertEqual(table["rows"][0]["score"], best["all"]["error_free"])
        table = leaderboard.table(ROOT, "judge_preferred", pairs="en-ja", view="passage")
        # A language pair is two directions: 8 sampled passages each, minus failed items.
        self.assertTrue(all(0 < r["n"] <= 16 for r in table["rows"]))
        self.assertEqual(max(r["n"] for r in table["rows"]), 16)
        self.assertNotIn("deepl-api", {r["system"] for r in table["rows"]})

    def test_compare_places_a_judge_run_beside_the_published_values(self):
        import json
        import tempfile

        from translate_bench import compare

        result = dict(n=288, directions=18, draws=2000, error_free=0.5, error_free_95=[0.4, 0.6], critical_major=0.1,
                      critical_major_95=[0.0, 0.2], minor=0.3, minor_95=[0.2, 0.4], penalty=1.0, penalty_95=[0.5, 1.5])
        mine = dict(schema="translate-bench/judge@1", protocol="judge-v1", stage="errors", system="mine",
                    against=None, judge=dict(model="some-judge"), complete=True, results=dict(all=result))
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "errors.json").write_text(json.dumps(mine))
            section = compare.judge_section(ROOT, tmp)
        self.assertEqual(section["errors"]["result"]["error_free"], 0.5)
        self.assertIsNone(section["pairwise"])
        published = {r["system"]: r for r in section["published"]}
        self.assertIn("deepl-api", published)
        self.assertEqual(published["deepl-api"]["error_free"],
                         judge_results.entry(self.summary, "errors", "deepl-api")["error_free"])
        text = compare.format_judge_section(section)
        self.assertIn("another judge model", text)
        self.assertIn("error-free 0.500", text)

    def test_compare_reports_a_pairwise_run_without_decided_items(self):
        """Every output identical to the other file's: the preferred share is undefined, not a crash."""
        import json
        import tempfile

        from translate_bench import compare, judge, schema

        sample = judge.load_sample(ROOT)
        documents = judge.Documents(sample, schema.read_jsonl(ROOT / "datasets" / "items.jsonl"))
        rows = [dict(it, status="identical", winner="tie") for it in sample]
        results = judge.pairwise_stats(rows, documents)
        self.assertIsNone(results["all"]["preferred"])
        results["passage"]["net_95"] = None  # an interval the bootstrap could not give
        mine = dict(schema="translate-bench/judge@1", protocol="judge-v1", stage="pairwise", system="mine",
                    against="deepl-api", judge=dict(model="some-judge"), complete=True, results=results)
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "pairwise.json").write_text(json.dumps(mine))
            texts = [compare.format_judge_section(compare.judge_section(ROOT, tmp, view)) for view in
                     ("overall", "sentence", "passage")]
        self.assertIn("preferred —, net +0.000 [+0.000, +0.000], wins 0 / losses 0 / ties 0 / identical 288 of n 288",
                      texts[0])
        self.assertIn("preferred —, net +0.000, wins 0", texts[2])
        lines = []
        judge.print_summary(dict(system="mine", against="deepl-api", judge=dict(model="some-judge"), stage="pairwise",
                                 complete=True, results=results, note="note"), lines.append)
        self.assertIn("preferred – of decided items", lines[1])


if __name__ == "__main__":
    unittest.main()
