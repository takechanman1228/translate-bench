import unittest

from translate_bench import schema


def row(**changes):
    base = dict(id="x/1/en-ja", direction="en-ja", type="sentence", subset=None, doc="d", status="ok", comet22=0.8,
                chrf_stats=[1] * 24, output_sha256="a" * 64)
    base.update(changes)
    return base


class SchemaTest(unittest.TestCase):
    def test_directions(self):
        self.assertEqual(len(schema.DIRECTIONS), 18)
        self.assertEqual(schema.parse_direction("en-zh-Hans"), ("en", "zh-Hans"))
        self.assertEqual(schema.parse_direction("pt-BR-en"), ("pt-BR", "en"))
        with self.assertRaises(ValueError):
            schema.parse_direction("ja-zh-Hans")

    def test_valid_rows(self):
        self.assertEqual(schema.row_problems(row()), [])
        self.assertEqual(schema.row_problems(row(status="failed", comet22=None, chrf_stats=None,
                                                 output_sha256=None, failure="missing")), [])
        self.assertEqual(schema.row_problems(row(comet22=None)), [])  # over the COMET token limit
        self.assertEqual(schema.row_problems(row(type="passage", subset="set-12", metricx24_ref=3.2)), [])

    def test_invalid_rows(self):
        cases = [row(direction="en-xx"), row(type="paragraph"), row(subset="set-8"), row(status="failed"),
                 row(chrf_stats=[1] * 23), row(output_sha256="xyz"), row(metricx24_qe=30.0),
                 row(provenance="v2"), row(unknown=1), {k: v for k, v in row().items() if k != "doc"},
                 row(comet22=float("nan"))]
        for case in cases:
            self.assertTrue(schema.row_problems(case), case)

    def test_duplicates(self):
        problems = schema.rows_problems([row(), row()], "test")
        self.assertTrue(any("duplicate" in p for p in problems))


if __name__ == "__main__":
    unittest.main()


class SpeedSchemaTest(unittest.TestCase):
    def local(self, **changes):
        from tests.fixtures import speed_part

        entry = dict(kind="local", date="2026-11-23", machine="m", runtime={}, load_s=1.0, peak_memory_gib=3.0,
                     memory_measured=True, memory_note="rss", download_bytes=1, start_conditions_met=True,
                     flagged=[False, True, False], sentence=speed_part(0.5),
                     passage=speed_part(1.5), items={})
        entry.update(changes)
        return dict(systems={"x": entry})

    def test_valid(self):
        self.assertEqual(schema.speed_problems(self.local(), {"x": "local"}), [])

    def test_machine_state_is_not_allowed(self):
        problems = schema.speed_problems(self.local(machine_start={"free_memory_pct": 80}), {"x": "local"})
        self.assertTrue(problems)

    def test_ranges(self):
        for change in (dict(peak_memory_gib=40.0), dict(start_conditions_met=False), dict(memory_measured=False),
                       dict(flagged=[False, True]), dict(flagged={"2": ["a reason"]})):
            self.assertTrue(schema.speed_problems(self.local(**change), {"x": "local"}), change)

    def test_cloud_cost_needs_a_note_when_missing(self):
        part = dict(seconds_per_item=1.0, estimated_usd_per_1000_items=None, tokens_per_item=None, directions=6)
        speed = dict(systems={"c": dict(kind="cloud", reference=dict(sentence=part, passage=part))})
        self.assertTrue(schema.speed_problems(speed, {"c": "cloud"}))
        noted = dict(part, cost_note="not estimated")
        speed = dict(systems={"c": dict(kind="cloud", reference=dict(sentence=noted, passage=noted))})
        self.assertEqual(schema.speed_problems(speed, {"c": "cloud"}), [])
