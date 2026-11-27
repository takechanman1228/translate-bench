"""The Overall score (results/v1.1/overall.json): its rule, its rounding, and verify catching a changed value."""

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from translate_bench import overall, schema
from translate_bench.export import site_data

ROOT = Path(__file__).resolve().parents[1]


def minimal_root(tmp, measured=18, error_free=0.75, judge_dirs=18, passed=52, items=208, covered=None):
    """A checkout with one system and just the three sources of the Overall score. Below 18 directions the
    system misses Indonesian first, then Arabic and so on; `covered` is its hard-case figure then."""
    root = Path(tmp)
    dirs = list(schema.DIRECTIONS)[:measured]
    schema.write_json(root / "configs/systems.json", dict(systems=[dict(id="sys-a", kind="local")]))
    schema.write_json(root / overall.SOURCES["standard"], dict(systems={"sys-a": dict(
        comet22=dict(overall=0.85 if measured == 18 else None, overall_measured=0.85 if measured == 18 else 0.84),
        overall_measured_directions=measured, directions={k: dirs for k in schema.TYPES})}))
    schema.write_json(root / overall.SOURCES["reliability"], dict(errors=[dict(
        system="sys-a", judge=overall.JUDGE, all=dict(error_free=error_free, directions=judge_dirs))]))
    hard = dict(our_directions=dict(items=items, passed=passed))
    if covered:
        hard["covered"] = dict(directions=measured, **covered)
    schema.write_json(root / overall.SOURCES["hard_cases"], dict(
        verifier=dict(model="v"), dataset=dict(our_direction_items=items), systems={"sys-a": hard}))
    return root


class RuleTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name

    def test_mean_of_three_pillars(self):
        data = overall.build(minimal_root(self.tmp))
        entry = data["systems"]["sys-a"]
        self.assertEqual((entry["standard"], entry["reliability"], entry["hard_cases"]), (85.0, 75.0, 25.0))
        self.assertEqual(entry["overall"], 61.7)  # (85 + 75 + 25) / 3 = 61.666...
        self.assertEqual(data["counts"], dict(systems=1, overall=1, full=1, partial=0, without_overall=0))
        self.assertEqual((entry["coverage"], entry["missing_languages"]), (18, []))

    def test_rounds_half_up(self):
        self.assertEqual(overall.one_decimal(0.25), 0.3)
        self.assertEqual(overall.one_decimal(39.05), 39.1)
        self.assertEqual(overall.one_decimal(81.3742), 81.4)

    def test_partial_coverage_is_scored_over_the_covered_directions(self):
        # 16 directions (no Indonesian): COMET-22 and the judge over them, hard cases on the covered items only.
        root = minimal_root(self.tmp, measured=16, judge_dirs=16, covered=dict(items=188, passed=47))
        entry = overall.build(root)["systems"]["sys-a"]
        self.assertEqual((entry["standard"], entry["hard_cases"], entry["hard_cases_items"]), (84.0, 25.0, 188))
        self.assertEqual(entry["overall"], 61.3)  # (84 + 75 + 25) / 3 = 61.333...
        self.assertEqual((entry["coverage"], entry["missing_languages"]), (16, ["id"]))

    def test_coverage_threshold(self):
        self.assertEqual(overall.MIN_DIRECTIONS, 12)
        for measured, judge_dirs, scored in ((12, 12, True), (11, 12, False), (14, 11, False), (5, 5, False)):
            with self.subTest(measured=measured, judge=judge_dirs), tempfile.TemporaryDirectory() as tmp:
                root = minimal_root(tmp, measured=measured, judge_dirs=judge_dirs, covered=dict(items=100, passed=10))
                entry = overall.build(root)["systems"]["sys-a"]
                self.assertEqual(entry["overall"] is not None, scored)
                self.assertIsNotNone(entry["reliability"])  # the pillars it has are kept

    def test_missing_track_gives_no_overall(self):
        root = minimal_root(self.tmp)
        (root / overall.SOURCES["hard_cases"]).unlink()
        entry = overall.build(root)["systems"]["sys-a"]
        self.assertIsNone(entry["overall"])
        self.assertIsNone(entry["hard_cases"])

    def test_check_catches_a_changed_value_and_a_changed_source(self):
        root = minimal_root(self.tmp)
        self.assertEqual(overall.check(root), [])  # absent: nothing to check
        overall.write(root)
        self.assertEqual(overall.check(root), [])
        data = schema.read_json(root / overall.PATH)
        data["systems"]["sys-a"]["overall"] = 61.8
        schema.write_json(root / overall.PATH, data)
        self.assertTrue(any("overall" in f for f in overall.check(root)))
        overall.write(root)
        schema.write_json(root / overall.SOURCES["hard_cases"], dict(
            verifier=dict(model="v"), dataset=dict(our_direction_items=208),
            systems={"sys-a": dict(our_directions=dict(items=208, passed=53))}))
        found = overall.check(root)
        self.assertTrue(any("sources" in f for f in found), found)
        self.assertTrue(any("hard_cases" in f for f in found), found)


@unittest.skipUnless(overall.exists(ROOT), "no Overall score in this checkout")
class PublishedOverallTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = schema.read_json(ROOT / overall.PATH)

    def test_published_file_recomputes(self):
        self.assertEqual(overall.check(ROOT), [])

    def test_counts_and_leaders(self):
        self.assertEqual(self.data["counts"], dict(systems=40, overall=38, full=31, partial=7, without_overall=2))
        order = overall.ranked(self.data)
        expected = [("claude-fable-5-2", 81.4), ("gemini-4-neon", 79.5), ("gpt-6.2-astra", 77.4),
                    ("gemini-4-argon", 75.6), ("gpt-6.2-sol", 74.9), ("gemini-4-hydrogen", 74.3),
                    ("claude-sonnet-5-5", 73.7), ("claude-opus-5-5", 73.2), ("gpt-6.1-terra", 68.3),
                    ("gpt-6-luna", 59.5), ("gemma-4-31b-it", 56.2), ("deepl-api", 53.6)]
        self.assertEqual([(s, self.data["systems"][s]["overall"]) for s in order[:12]], expected)
        fable = self.data["systems"]["claude-fable-5-2"]
        self.assertEqual((round(fable["standard"], 1), round(fable["reliability"], 1), round(fable["hard_cases"], 1)),
                         (86.1, 96.5, 61.5))

    def test_systems_without_overall_keep_their_pillars(self):
        missing = {s for s, e in self.data["systems"].items() if e["overall"] is None}
        self.assertEqual(missing, {"qwen-mt-lumen", "gemini-3.8-flash"})
        partial = {s: e["coverage"] for s, e in self.data["systems"].items() if e["overall"] is not None
                   and e["coverage"] < 18}
        self.assertEqual(partial, {"plamo-3-translate-0.8b": 16, "plamo-3-translate-2b": 16, "plamo-3-translate-8b": 16,
                                   "plamo-3-translate-31b": 16, "eurollm-22b-instruct-2512": 16,
                                   "apple-foundation-models": 14, "apple-foundation-models-permissive": 14})
        plamo = self.data["systems"]["plamo-3-translate-31b"]
        self.assertEqual((plamo["overall"], plamo["missing_languages"]), (52.7, ["pt-BR"]))
        self.assertEqual(self.data["systems"]["eurollm-22b-instruct-2512"]["hard_cases_items"], 188)
        for sid in missing:
            entry = self.data["systems"][sid]
            self.assertIsNotNone(entry["hard_cases"], sid)
            self.assertLess(min(entry["directions"].values()), 18, sid)

    def test_verify_fails_on_a_changed_overall(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel in ("configs/systems.json", *overall.SOURCES.values(), str(overall.PATH)):
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(ROOT / rel, root / rel)
            self.assertEqual(overall.check(root), [])
            data = copy.deepcopy(self.data)
            data["systems"]["gemma-4-31b-it"]["overall"] = 56.3
            (root / overall.PATH).write_text(json.dumps(data), encoding="utf-8")
            self.assertTrue(any("gemma-4-31b-it" in f for f in overall.check(root)))

    def test_site_data_carries_the_overall_score(self):
        data = site_data.build(ROOT)
        for s in data["systems"]:
            self.assertEqual(s["overall"], self.data["systems"][s["id"]], s["id"])
        self.assertIn(overall.PATH.as_posix(), data["sources"])


    def test_leaderboard_ranks_by_overall_by_default(self):
        from translate_bench import leaderboard

        result = leaderboard.table(ROOT)
        self.assertEqual(result["metric"], "overall")
        self.assertEqual([r["system"] for r in result["rows"][:2]], ["claude-fable-5-2", "gemini-4-neon"])
        self.assertEqual((len(result["rows"]), len(result["not_covered"])), (38, 2))
        text = leaderboard.format_published_table(result)
        self.assertIn("| 1 | Claude Fable 5.2 | cloud | 81.4 | 0.8605 | 96.5% | 61.5% [54.8, 67.8] |", text)
        self.assertIn("| 13 | PLaMo 3 Translate 31B (16/18) | local | 52.7 |", text)
        self.assertIn("Qwen-MT-Lumen (COMET-22 5/18, judge 5/18)", text)
        hard = leaderboard.table(ROOT, "hard_cases")
        self.assertEqual(len(hard["rows"]), 40)
        self.assertEqual(hard["rows"][0]["system"], "claude-fable-5-2")
        self.assertIsNone(next(r for r in hard["rows"] if r["system"] == "gemini-3.8-flash")["overall"])

    def test_leaderboard_other_metrics_carry_the_published_columns(self):
        from translate_bench import leaderboard

        result = leaderboard.table(ROOT, pairs="en-ja")
        self.assertEqual(result["metric"], "comet22")  # a selection falls back to COMET-22
        row = next(r for r in result["rows"] if r["system"] == "gemma-4-31b-it")
        self.assertEqual((row["overall"], round(row["hard_cases"], 4)), (56.2, 0.0865))
        self.assertIn("| Overall | Hard cases |", leaderboard.format_table(result))
        with self.assertRaises(ValueError):
            leaderboard.table(ROOT, "overall", pairs="en-ja")
        with self.assertRaises(ValueError):
            leaderboard.table(ROOT, "hard_cases", view="sentence")


if __name__ == "__main__":
    unittest.main()
