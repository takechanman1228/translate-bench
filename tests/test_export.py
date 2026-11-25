"""The generated README numbers and site data match the results, and drift is caught."""

import json
import unittest
from pathlib import Path

from translate_bench.export import readme, site_data
from translate_bench.export.facts import Facts
from translate_bench.verify import differences

ROOT = Path(__file__).resolve().parents[1]


class ExportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.facts = Facts(ROOT)

    def test_committed_readme_blocks_match(self):
        for rel, kind in readme.FILES.items():
            text = (ROOT / rel).read_text(encoding="utf-8")
            new, names = readme.fill(text, readme.render_file(self.facts, kind))
            self.assertTrue(names, rel)
            self.assertEqual(new, text, f"{rel}: run `make readme`")

    def test_changed_number_is_caught(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        tampered = text.replace("0.8587", "0.8597", 1)
        self.assertNotEqual(tampered, text)
        new, _ = readme.fill(tampered, readme.render_file(self.facts, "en"))
        self.assertNotEqual(readme.blocks(new), readme.blocks(tampered))
        self.assertEqual(new, text)

    def test_claims_follow_the_intervals(self):
        facts = Facts(ROOT)
        facts.paired = lambda a, b, view="overall": dict(delta=-0.01, ci95=[-0.02, -0.005], n=3960)
        with self.assertRaises(ValueError):
            readme.finding_small_models(facts, "en")
        facts.paired = lambda a, b, view="overall": dict(delta=0.0, ci95=[-0.001, 0.001], n=3960)
        text = readme.finding_small_models(facts, "en")
        self.assertIn(" ties ", text)
        self.assertNotIn(" beats ", text)

    def test_site_data_matches_and_drift_is_caught(self):
        published = site_data.parse((ROOT / site_data.OUT).read_text(encoding="utf-8"))
        rebuilt = json.loads(json.dumps(site_data.build(ROOT)))
        self.assertEqual(differences(published, rebuilt), [])
        rebuilt["cells"]["hy-mt2-30b-a3b"]["s:en-ja"][0] += 0.001
        self.assertTrue(differences(published, rebuilt))

    def test_site_data_holds_no_text(self):
        data = site_data.build(ROOT)
        for sid, cells in data["scores"].items():
            for key, values in cells.items():
                self.assertRegex(values, r"^[0-9,]*$", f"{sid} {key}")
        self.assertTrue(all(set(m) <= set("0123456789") for m in data["boot"]["m"]))

    def test_judge_source_is_labelled(self):
        data = site_data.build(ROOT)
        self.assertEqual(data["judge"]["source"], "v1")
        self.assertEqual(data["judge"]["label"], "judge v1")

    def test_judge_v1_claims_follow_the_intervals(self):
        facts = Facts(ROOT)
        text = readme.finding_measures(facts, "en")
        self.assertIn("Nine cloud systems beat DeepL API on the judge", text)
        self.assertIn("No local system does", text)
        self.assertNotIn("separates", text)
        self.assertNotIn("分ける", readme.finding_measures(facts, "ja"))
        original = facts.judge.versus_reference

        def shifted(sid, scope="all"):
            v = dict(original(sid, scope) or {})
            if v and facts.kind(sid) == "local":
                v.update(preferred=0.6, net=0.1, net_95=[0.01, 0.2])  # a local system preferred to DeepL API
            return v or None
        facts.judge.versus_reference = shifted
        with self.assertRaises(ValueError):
            readme.finding_measures(facts, "en")

    def test_metricx_order_claims_need_their_intervals(self):
        facts = Facts(ROOT)
        facts.paired_metricx = lambda a, b, view="overall": dict(delta=-0.1, ci95=[-0.2, 0.01], n=3960)
        with self.assertRaises(ValueError):  # the top local system's MetricX-24 lead would not be resolved
            readme.finding_measures(facts, "en")

    def test_systems_table_covers_the_registry(self):
        text = readme.systems_table(self.facts)
        for s in self.facts.systems.values():
            self.assertIn(f"| {s['name']} |", text)
        self.assertIn("| GPT-6.2 Astra | cloud | Codex CLI | 18 | — | 25 / 5 |", text)

    def test_correlations_include_the_judge(self):
        text = readme.correlations(self.facts)
        self.assertIn("| Judge vs DeepL API |", text)
        self.assertIn("| Error-free |", text)
        self.assertNotIn("dashboard", text)

    def test_site_judge_cells_aggregate_like_the_cli(self):
        """The dashboard's judge over one language pair equals `translate-bench leaderboard` on it."""
        from translate_bench import leaderboard

        data = site_data.build(ROOT)
        pair = ["en-ja", "ja-en"]
        for metric, stage in (("judge_preferred", "pairwise"), ("error_free", "errors")):
            for view, types in (("overall", ["s", "p"]), ("passage", ["p"])):
                table = leaderboard.judge_table(ROOT, metric, pairs="en-ja", view=view)
                for row in table["rows"]:
                    mine = site_data.aggregate_cells(data["judge"][stage][row["system"]], pair, types, stage)
                    self.assertEqual(mine["n"], row["n"], (metric, view, row["system"]))
                    value = mine["preferred"] if stage == "pairwise" else mine["error_free"]
                    self.assertAlmostEqual(value, row["score"], places=4, msg=(metric, view, row["system"]))


if __name__ == "__main__":
    unittest.main()
