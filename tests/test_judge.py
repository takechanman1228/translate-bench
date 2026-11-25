"""`translate-bench judge`: the fixed sample, the instructions, and a run against a fake server on made-up inputs."""

import csv
import hashlib
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from tests.fake_openai import Server
from tests.fixtures import items as frame
from translate_bench import cli, judge, schema
from translate_bench.datasets.build import FIELDS

ROOT = Path(__file__).resolve().parents[1]
# SHA-256 of the protocol's two instruction templates, as in the lab's judge protocol v1 of November 25, 2026.
PAIRWISE_SHA256 = "ee7e3ad42313771c97bc7a8b383bbe3deff947e34c74ab22eb272550673dc09d"
ERRORS_SHA256 = "571c0216c394894614945dc46839b52195c9c3ef1f6e84a0a406687653dec577"


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


class SampleTest(unittest.TestCase):
    def test_sample_is_the_rule_over_the_release_items(self):
        stored = schema.read_json(ROOT / "datasets/judge-sample.json")
        manifest = schema.read_jsonl(ROOT / "datasets/items.jsonl")
        self.assertEqual(stored["seed_string"], "translate-bench/v1/judge-sample/")
        recomputed = []
        for d in schema.DIRECTIONS:
            for kind in schema.TYPES:
                cell = [i for i in manifest if (i["direction"], i["type"]) == (d, kind)]
                self.assertEqual(len(cell), schema.CELL_SIZE[kind])
                ranked = sorted(cell, key=lambda i: sha("translate-bench/v1/judge-sample/" + i["id"]))[:8]
                recomputed += [{k: i[k] for k in ("id", "direction", "type", "subset", "doc")} for i in ranked]
        self.assertEqual(stored["items"], recomputed)
        self.assertEqual(judge.load_sample(ROOT), recomputed)
        self.assertEqual(len(recomputed), 288)
        self.assertEqual(len({i["doc"] for i in recomputed}), 111)
        self.assertEqual(Counter(i["subset"] for i in recomputed), {None: 192, "set-12": 55, "set-8": 41})

    def test_instructions_are_the_protocols(self):
        self.assertEqual(sha(judge.PAIRWISE), PAIRWISE_SHA256)
        self.assertEqual(sha(judge.ERRORS), ERRORS_SHA256)
        text = judge.instruction(judge.ERRORS, "zh-Hans-en", {"Q01": {"source": "s", "candidate": "c"}})
        self.assertTrue(text.startswith("You are an expert bilingual reviewer annotating Simplified Chinese to "
                                        "English translations"))
        self.assertTrue(text.endswith('{"critical": n, "major": n, "minor": n}.\n\n{\n  "Q01": {\n    "source": "s",\n'
                                      '    "candidate": "c"\n  }\n}'))

    def test_weights_keep_directions_and_types_equal(self):
        cells = [("en-ja", "sentence")] * 8 + [("en-ja", "passage")] * 2 + [("en-de", "sentence")] * 4
        w = judge.weights(cells)
        self.assertAlmostEqual(w.sum(), 1)
        self.assertAlmostEqual(w[:8].sum(), 0.25)
        self.assertAlmostEqual(w[8:10].sum(), 0.25)
        self.assertAlmostEqual(w[10:].sum(), 0.5)


class JudgeRunTest(unittest.TestCase):
    """A made-up release (ids, documents, sources) in a temporary directory, judged through the fake server."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = root = Path(self.tmp.name)
        manifest = [dict(i, source_sha256=sha(f"Made-up source of {i['id']}."),
                         reference_sha256=sha(f"ref {i['id']}")) for i in frame()]
        schema.write_jsonl(root / "datasets/items.jsonl", manifest)
        schema.write_json(root / "datasets/judge-sample.json", dict(items=judge.draw_sample(manifest)))
        (root / "configs").mkdir()
        schema.write_json(root / "configs/systems.json", dict(systems=[]))
        (root / "results/v1").mkdir(parents=True)
        self.inputs = root / "inputs"
        self.inputs.mkdir()
        for kind, name in (("sentence", "sentences.tsv"), ("passage", "passages.tsv")):
            with (self.inputs / name).open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, FIELDS, delimiter="\t")
                writer.writeheader()
                for i in manifest:
                    if i["type"] == kind:
                        src, tgt = schema.parse_direction(i["direction"])
                        writer.writerow(dict(id=i["id"], src=src, tgt=tgt, source=f"Made-up source of {i['id']}.",
                                             reference=f"ref {i['id']}", domain="news", doc=i["doc"]))
        self.directions = ("en-ja", "ja-en")
        chosen = [i for i in manifest if i["direction"] in self.directions]
        self.a = self.predictions("a.jsonl", {i["id"]: f"Output {i['id']}" for i in chosen})
        sample = {i["id"] for i in judge.draw_sample(manifest)}
        self.dropped = next(i["id"] for i in chosen if i["id"] in sample)
        self.b = self.predictions("b.jsonl", {i["id"]: (f"Output {i['id']}" if n % 3 == 0 else f"OUTPUT {i['id']}")
                                              for n, i in enumerate(chosen) if i["id"] != self.dropped})
        self.server = Server().__enter__()

    def tearDown(self):
        self.server.__exit__()
        self.tmp.cleanup()

    def predictions(self, name, texts):
        path = self.root / name
        path.write_text("".join(json.dumps(dict(id=k, translation=v)) + "\n" for k, v in texts.items()))
        return path

    def judge(self, *extra, model="fake-judge", out="private/judged", base_url=None):
        parsed = cli.build_parser().parse_args(
            ["judge", "--predictions", str(self.a), "--system-name", "mine", "--judge-model", model,
             "--base-url", base_url or self.server.base_url, "--inputs", str(self.inputs), "--out",
             str(self.root / out), *extra])
        parsed.backoff = 0
        logs = []
        return judge.main(self.root, parsed, log=logs.append), logs

    def test_errors_one_candidate_at_a_time(self):
        self.server.script = ["garbage"]  # the first answer is not JSON; the request is sent again
        code, logs = self.judge()
        self.assertEqual(code, 0, logs)
        prompts = [body["messages"][0]["content"] for _, _, body in self.server.requests]
        self.assertEqual(len(prompts), 4 + 1)  # one request per direction and type, plus the retry
        self.assertTrue(all(p.startswith(judge.ERRORS.format(source="English", target="Japanese")[:60])
                            or "Japanese to English" in p for p in prompts))
        summary = schema.read_json(self.root / "private/judged/errors.json")
        self.assertTrue(summary["complete"])
        self.assertEqual(summary["items"], dict(sample=32, missing=0, identical=0, waiting=0))
        # The fake gives major = len(candidate) % 2 and minor = len(candidate) % 3.
        lengths = [len(f"Output {i['id']}") for i in judge.load_sample(self.root) if i["direction"] in self.directions]
        free = sum(n % 2 == 0 and n % 3 == 0 for n in lengths) / len(lengths)
        self.assertAlmostEqual(summary["results"]["all"]["error_free"], round(free, 4))
        self.assertEqual(summary["results"]["all"]["n"], 32)
        records = schema.read_jsonl(self.root / "private/judged/errors.jsonl")
        self.assertEqual(len(records), 4)
        self.assertNotIn("Made-up source", (self.root / "private/judged/errors.jsonl").read_text())
        code, _ = self.judge()  # resume: nothing to send
        self.assertEqual((code, len(self.server.requests)), (0, 5))
        with self.assertRaises(ValueError):
            self.judge(model="another-judge")  # the journal was answered by another judge

    def test_pairwise_maps_a_and_b_back(self):
        code, logs = self.judge("--against-predictions", str(self.b), "--against-name", "theirs")
        self.assertEqual(code, 0, logs)
        summary = schema.read_json(self.root / "private/judged/pairwise.json")
        rows = summary["results"]["all"]
        sample = [i for i in judge.load_sample(self.root) if i["direction"] in self.directions]
        self.assertEqual(summary["items"]["missing"], 1)  # the item the other system has no output for
        self.assertEqual(rows["n"], 31)
        self.assertEqual(rows["wins"] + rows["losses"] + rows["ties"] + rows["identical"], 31)
        # Equal lengths: the fake always prefers A, so the system wins exactly where it was shown first.
        judged = [i for i in sample if i["id"] != self.dropped]
        b = {r["id"]: r["translation"] for r in schema.read_jsonl(self.b)}
        outcome = {i["id"]: "identical" if b[i["id"]] == f"Output {i['id']}" else
                   "win" if judge.system_first("mine", i["id"]) else "loss" for i in judged}
        expected = Counter(outcome.values())
        self.assertEqual((rows["wins"], rows["losses"], rows["identical"]),
                         (expected["win"], expected["loss"], expected["identical"]))
        # Net keeps each direction and type at its share although one cell has 7 items: mean of cell means.
        cells = {}
        for i in judged:
            cells.setdefault((i["direction"], i["type"]), []).append({"win": 1, "loss": -1}.get(outcome[i["id"]], 0))
        means = [sum(v) / len(v) for v in cells.values()]
        self.assertEqual(len(cells), 4)
        self.assertAlmostEqual(rows["net"], sum(means) / 4, places=4)

    def test_sample_needs_the_release_inputs(self):
        tsv = self.inputs / "sentences.tsv"
        tsv.write_text(tsv.read_text(encoding="utf-8").replace("Made-up source of syn-s", "Other source of syn-s"),
                       encoding="utf-8")
        with self.assertRaises(ValueError) as context:
            self.judge()
        self.assertIn("release inputs", str(context.exception))

    def test_two_endpoints_with_one_model_name_do_not_share_a_journal(self):
        from tests.fake_openai import BODY_MARKER

        self.server.script = ["400", "400"]  # both attempts of one request fail; the error body is not kept
        code, logs = self.judge("--limit", "2", "--concurrency", "1")
        self.assertEqual(code, 3)
        self.assertNotIn(BODY_MARKER, "\n".join(logs))
        self.assertEqual(len(schema.read_jsonl(self.root / "private/judged/errors.jsonl")), 1)
        with Server() as other:
            with self.assertRaises(ValueError) as context:
                self.judge(base_url=other.base_url)
            self.assertEqual(other.requests, [])
        self.assertIn("another prompt, output, judge, endpoint or request fields", str(context.exception))
        code, logs = self.judge()  # the first endpoint again: only the missing requests are sent
        self.assertEqual(code, 0, logs)
        summary = schema.read_json(self.root / "private/judged/errors.json")
        self.assertEqual(summary["judge"]["endpoint"], "local endpoint")
        self.assertTrue(summary["complete"])
        text = (self.root / "private/judged/errors.jsonl").read_text() + json.dumps(summary)
        self.assertNotIn(str(self.server.httpd.server_address[1]), text)

    def test_dry_run_sends_nothing(self):
        code, logs = self.judge("--dry-run")
        self.assertEqual((code, self.server.requests), (0, []))
        self.assertTrue(any("4 to send" in line for line in logs), logs)


if __name__ == "__main__":
    unittest.main()
