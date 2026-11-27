"""The hard-cases track (results/ltb-v1/): verify recomputes it, catches tampering and skips it when absent."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from translate_bench import ltb, schema
from translate_bench.export import site_data

ROOT = Path(__file__).resolve().parents[1]


def item(i, direction, rules, ours):
    source, target = direction.split("-")
    return dict(id=i, direction=direction, source_iso=source, target_iso=target, source_label=source,
                target_label=target, source_sha256=f"{i:064x}", rules=rules, ours=ours)


def row(i, verdicts, status="ok"):
    return {"id": i, "pass": all(v is True for v in verdicts), "verdicts": verdicts, "status": status,
            "translation_sha256": None if status != "ok" else f"{i + 100:064x}"}


ITEMS = [item(1, "eng-jpn", 2, True), item(2, "eng-jpn", 1, True), item(3, "ita-eng", 1, False),
         item(4, "deu-gsw", 3, False), item(5, "jpn-eng", 1, True)]
ROWS = {
    "sys-a": [row(1, [True, True]), row(2, [False]), row(3, [True]), row(4, [True, False, "skipped"]), row(5, [True])],
    "sys-b": [row(1, [False, "skipped"]), row(2, [True]), row(3, [False], "unsupported"),
              row(4, [False, False, False], "empty"), row(5, [False])],
}


def write_track(root, items=ITEMS, rows=ROWS, incomplete=()):
    base = root / ltb.BASE
    schema.write_jsonl(base / "items.jsonl", items)
    for sid, rs in rows.items():
        schema.write_jsonl(base / "rows" / f"{sid}.jsonl", rs)
    summary = dict(schema=ltb.SUMMARY_SCHEMA,
                   dataset=dict(items=len(items), our_direction_items=sum(it["ours"] for it in items),
                                rules=sum(it["rules"] for it in items)),
                   bootstrap=dict(draws=ltb.DRAWS, seed_string=ltb.SEED),
                   systems=ltb.systems(items, rows, coverage=ltb.coverage(root)), incomplete=list(incomplete),
                   pending=[])
    schema.write_json(base / "summary.json", summary)
    return summary


class TrackTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def test_absent_track_is_skipped(self):
        self.assertFalse(ltb.exists(self.root))
        self.assertEqual(ltb.check(self.root), [])
        self.assertEqual(site_data.hard_cases(self.root), {})

    def test_recomputes_and_counts(self):
        summary = write_track(self.root)
        self.assertEqual(ltb.check(self.root), [])
        a, b = summary["systems"]["sys-a"], summary["systems"]["sys-b"]
        self.assertEqual((a["all"]["passed"], a["all"]["pass_rate"]), (3, 0.6))
        self.assertEqual((a["our_directions"]["items"], a["our_directions"]["passed"]), (3, 2))
        self.assertEqual((b["unsupported"], b["empty"], b["unscored"]), (1, 1, 0))
        self.assertEqual(a["by_pair"]["eng-jpn"], dict(items=2, passed=1, pass_rate=0.5))
        low, high = a["all"]["ci95"]
        self.assertTrue(0 <= low <= 0.6 <= high <= 1)
        # Fixed seed: the same rows give the same intervals.
        self.assertEqual(ltb.systems(ITEMS, ROWS), summary["systems"])

    def test_changed_verdict_is_caught(self):
        write_track(self.root)
        rows = copy.deepcopy(ROWS)
        rows["sys-b"][4] = row(5, [True])
        schema.write_jsonl(self.root / ltb.BASE / "rows" / "sys-b.jsonl", rows["sys-b"])
        found = ltb.check(self.root)
        self.assertTrue(any("sys-b" in f and "pass_rate" in f for f in found), found)

    def test_changed_interval_is_caught(self):
        summary = write_track(self.root)
        summary["systems"]["sys-a"]["all"]["ci95"][0] += 0.01
        schema.write_json(self.root / ltb.BASE / "summary.json", summary)
        self.assertTrue(ltb.check(self.root))

    def test_row_problems(self):
        cases = [
            ("sys-a", 0, dict(pass_=False)),  # pass differs from the verdicts
            ("sys-a", 1, dict(verdicts=[False, False])),  # wrong number of rules
            ("sys-a", 3, dict(verdicts=[True, "skipped", "skipped"])),  # skipped without a failed rule
            ("sys-b", 2, dict(translation_sha256="0" * 64)),  # unsupported item with a translation
            ("sys-a", 2, dict(status="unscored")),
            ("sys-a", 2, dict(translation="text")),  # a field outside the row schema
        ]
        for sid, index, change in cases:
            rows = copy.deepcopy(ROWS)
            for key, value in change.items():
                rows[sid][index][key.rstrip("_")] = value
            with self.subTest(change=change):
                summary = dict(systems={s: None for s in rows}, incomplete=[], pending=[])
                self.assertTrue(ltb.row_problems(ITEMS, rows, summary))

    def test_covered_items_of_a_partial_system(self):
        # sys-b covers only en-ja in v1: its covered figure counts items 1 and 2 (eng-jpn), not 5 (jpn-eng).
        full = {k: list(schema.DIRECTIONS) for k in schema.TYPES}
        schema.write_json(self.root / "results/v1/summary.json", dict(systems={
            "sys-a": dict(directions=full), "sys-b": dict(directions={k: ["en-ja"] for k in schema.TYPES})}))
        summary = write_track(self.root)
        self.assertNotIn("covered", summary["systems"]["sys-a"])
        covered = summary["systems"]["sys-b"]["covered"]
        self.assertEqual((covered["directions"], covered["items"], covered["passed"], covered["left_out"]),
                         (1, 2, 1, 1))
        self.assertEqual(covered["pass_rate"], 0.5)
        self.assertEqual(ltb.check(self.root), [])
        summary["systems"]["sys-b"]["covered"]["passed"] = 2
        schema.write_json(self.root / ltb.BASE / "summary.json", summary)
        self.assertTrue(any("covered" in f for f in ltb.check(self.root)))

    def test_release_directions_of_items(self):
        self.assertEqual(ltb.release_direction(item(1, "eng-jpn", 1, True)), "en-ja")
        self.assertEqual(ltb.release_direction(item(1, "zho-eng", 1, True)), "zh-Hans-en")
        self.assertIsNone(ltb.release_direction(item(1, "deu-gsw", 1, False)))
        self.assertIsNone(ltb.release_direction(item(1, "fra-deu", 1, False)))

    def test_incomplete_system_has_no_rows(self):
        write_track(self.root, incomplete=[dict(system="sys-b", items=5, decided=4)])
        self.assertTrue(any("incomplete" in f for f in ltb.check(self.root)))

    def test_site_metric(self):
        summary = write_track(self.root)
        hard = site_data.hard_cases(self.root)
        self.assertEqual(set(hard), {"sys-a", "sys-b"})
        ours = summary["systems"]["sys-a"]["our_directions"]
        self.assertEqual(hard["sys-a"], dict(rate=round(2 / 3, 6), ci=ours["ci95"], passed=2, items=3, directions=18))

    def test_second_verifier_counts(self):
        summary = write_track(self.root)
        summary["verifier"] = dict(model="primary-v")
        good = dict(schema=ltb.SECOND_SCHEMA, primary="primary-v", verifier=dict(model="second-v"),
                    systems={"sys-a": dict(items=3, passed={"primary-v": 2, "second-v": 1}, agreed=2),
                             "sys-b": dict(items=3, passed={"primary-v": 1, "second-v": 1}, agreed=3)},
                    total=dict(items=6, agreed=5))
        self.assertEqual(ltb.second_problems(summary, good), [])
        cases = [
            ("sys-a", dict(passed={"primary-v": 3, "second-v": 1})),  # differs from the rows' passes
            ("sys-a", dict(agreed=3)),  # agreement impossible with one pass apart
            ("sys-b", dict(agreed=2)),  # one disagreement cannot leave the passes equal
            ("sys-b", dict(items=4)),
        ]
        for sid, change in cases:
            bad = copy.deepcopy(good)
            bad["systems"][sid].update(change)
            bad["total"] = dict(items=sum(e["items"] for e in bad["systems"].values()),
                                agreed=sum(e["agreed"] for e in bad["systems"].values()))
            with self.subTest(change=change):
                self.assertTrue(ltb.second_problems(summary, bad))
        bad = copy.deepcopy(good)
        bad["total"]["agreed"] = 6
        self.assertTrue(ltb.second_problems(summary, bad))
        extra = dict(good, systems={**good["systems"], "sys-c": good["systems"]["sys-a"]})
        schema.write_json(self.root / ltb.SECOND, extra)
        summary_path = self.root / ltb.BASE / "summary.json"
        schema.write_json(summary_path, summary)
        self.assertTrue(any("sys-c" in f for f in ltb.check(self.root)))


@unittest.skipUnless(ltb.exists(ROOT), "no hard-cases track in this checkout")
class PublishedTrackTest(unittest.TestCase):
    def test_published_track_recomputes(self):
        self.assertEqual(ltb.check(ROOT), [])

    def test_site_data_carries_the_pass_rate(self):
        summary = schema.read_json(ROOT / ltb.BASE / "summary.json")
        data = site_data.build(ROOT)
        for s in data["systems"]:
            entry = summary["systems"].get(s["id"])
            if entry is None:
                self.assertIsNone(s["ltb"], s["id"])
            else:
                ours = entry["our_directions"]
                pillar = entry["covered"] if s["overall"]["directions"]["hard_cases"] < 18 else ours
                self.assertEqual({k: s["ltb"][k] for k in ("rate", "ci", "passed", "items")},
                                 dict(rate=pillar["pass_rate"], ci=pillar["ci95"], passed=pillar["passed"],
                                      items=pillar["items"]))
                self.assertEqual("all" in s["ltb"], pillar is not ours)
        self.assertEqual(data["hard_cases"]["items"], 208)
        self.assertIn("results/ltb-v1/summary.json", data["sources"])

    def test_covered_figures_of_partial_systems(self):
        summary = schema.read_json(ROOT / ltb.BASE / "summary.json")["systems"]
        covered = {s: e["covered"] for s, e in summary.items() if "covered" in e}
        self.assertEqual((covered["eurollm-22b-instruct-2512"]["items"], covered["apple-foundation-models"]["items"],
                          covered["plamo-3-translate-31b"]["items"]), (188, 170, 208))
        self.assertEqual(covered["plamo-3-translate-31b"]["unsupported_inside"], 1)
        self.assertEqual(covered["gemini-3.8-flash"]["items"], 0)
        self.assertNotIn("deepl-api", covered)

    def test_second_verifier_is_checked(self):
        second = ltb.second_verifier(ROOT)
        self.assertIsNotNone(second)
        self.assertEqual(len(second["systems"]), 10)
        self.assertEqual(second["total"]["items"], 2080)

    def test_items_hold_no_text(self):
        items, rows = ltb.load(ROOT)
        self.assertEqual(len(items), 911)
        self.assertEqual(sum(it["ours"] for it in items), 208)
        self.assertTrue(all(set(it) == set(ltb.ITEMS_SCHEMA_FIELDS) for it in items))
        self.assertTrue(all(set(r) == set(ltb.ROW_FIELDS) for rs in rows.values() for r in rs))
        self.assertEqual(json.dumps(items).count("source_text"), 0)
