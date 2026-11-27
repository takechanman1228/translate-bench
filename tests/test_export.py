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

    def test_top_table_follows_the_overall_score(self):
        text = readme.top_table(self.facts, "en")
        rows = [line for line in text.splitlines()
                if line.startswith("| ") and not line.startswith(("| System", "| ---"))]
        self.assertEqual(len(rows), readme.TOP_ROWS)
        self.assertTrue(rows[0].startswith("| Claude Fable 5.2 | Cloud | 81.4 | 0.8605 | 96.5% | 61.5% |"), rows[0])
        self.assertIn("| Gemma 4 31B IT | Local | 56.2 |", text)
        self.assertIn("leading group rather than one winner", text)
        self.assertNotIn("winner is", text)

    def test_leading_group_needs_the_uncertainty(self):
        facts = Facts(ROOT)
        scores = dict(facts.overall_data["systems"])
        scores["claude-fable-5-2"] = dict(scores["claude-fable-5-2"], overall=90.0)  # far ahead of the second
        facts.overall_data = dict(facts.overall_data, systems=scores)
        with self.assertRaises(ValueError):
            readme.leading_group(facts, "en")

    def test_findings_check_their_claims(self):
        text = readme.findings(self.facts, "en")
        self.assertIn("Seven cloud systems pass 40% or more of the 208 hard items", text)
        self.assertIn("Every one of the 27 local systems passes fewer than 10%", text)
        self.assertIn("on Overall, Gemma 4 31B IT, is ahead of DeepL API** (56.2 against 53.6)", text)
        facts = Facts(ROOT)
        original = facts.hard

        def harder(sid):  # a local system passing 12% of the hard items
            return 0.12 if sid == "gemma-4-31b-it" else original(sid)
        facts.hard = harder
        with self.assertRaises(ValueError):
            readme.finding_hard(facts, "en")
        facts = Facts(ROOT)
        facts.overall = lambda sid: 50.0 if sid == "gemma-4-31b-it" else facts.overall_data["systems"][sid]["overall"]
        with self.assertRaises(ValueError):
            readme.finding_local_vs_reference(facts, "en")

    def test_overall_section_names_verifiers_and_credit(self):
        for lang in ("en", "ja"):
            text = readme.overall_section(self.facts, lang)
            self.assertIn("Claude Sonnet 5.5", text)
            self.assertIn("Gemini 3.8 Flash", text)
            self.assertIn("arXiv:2609.04173", text)
            self.assertIn("CC BY 4.0", text)
            self.assertIn("97.1%", text)
            self.assertIn("2,080", text)
            self.assertIn("3.4", text)
        self.assertIn("not official LTB leaderboard numbers", readme.overall_section(self.facts, "en"))

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
