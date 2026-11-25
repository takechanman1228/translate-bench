"""Item assembly, the excerpt rule and the input guard, on made-up upstream files."""

import hashlib
import io
import json
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

from translate_bench import prepare, schema
from translate_bench.datasets import build, selection

LIMITS = dict(characters=dict(cap=360, minimum=28), words=dict(cap=140, minimum=12))


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


class ExcerptTest(unittest.TestCase):
    def test_word_cap_and_minimum(self):
        segments = [(1, "one two three four five six seven", "a"), (2, "eight nine ten eleven twelve", "b"),
                    (3, " ".join(["w"] * 200), "c")]
        ids, source, target = selection.excerpt(segments, "en", LIMITS)
        self.assertEqual(ids, [1, 2])
        self.assertEqual(source, "one two three four five six seven\neight nine ten eleven twelve")
        self.assertEqual(target, "a\nb")
        self.assertIsNone(selection.excerpt(segments[:1], "en", LIMITS))  # 7 words < 12

    def test_characters_and_empty_segment(self):
        segments = [(1, "あ" * 30, "x"), (2, "", "y"), (3, "い" * 30, "z")]
        self.assertEqual(selection.excerpt(segments, "ja", LIMITS)[0], [1])


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        build.ntrex_lines.cache_clear()
        build.wmt24pp_documents.cache_clear()
        build.newstest.cache_clear()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, key, data):
        path = self.base / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return str(path)

    def test_ntrex_line_with_bom(self):
        paths = {build.ntrex_key("en"): self.write(build.ntrex_key("en"), "﻿First line\nSecond line\n".encode()),
                 build.ntrex_key("ko"): self.write(build.ntrex_key("ko"), "첫째\n둘째\n".encode())}
        item = dict(id="ntrex/2/ko-en", direction="ko-en", origin=dict(dataset="ntrex-128", line=2))
        self.assertEqual(build.texts(item, paths), ("둘째", "Second line"))

    def test_wmt24pp_passage_both_directions(self):
        lines = [dict(document_id="doc", segment_id=i, source=f"English {i}", target=f"Deutsch {i}", domain="speech",
                      is_bad_source=False) for i in (3, 1, 2)]
        key = build.wmt24pp_key("de")
        paths = {key: self.write(key, "\n".join(json.dumps(x) for x in lines).encode())}
        origin = dict(dataset="wmt24pp", document="doc", segments=[1, 2])
        out = build.texts(dict(id="a", direction="en-de", origin=origin), paths)
        back = build.texts(dict(id="b", direction="de-en", origin=origin), paths)
        self.assertEqual(out, ("English 1\nEnglish 2", "Deutsch 1\nDeutsch 2"))
        self.assertEqual(back, out[::-1])

    def test_newstest_sgml_with_ampersand(self):
        sgm = {lg: (f'<srcset><doc docid="n/1" origlang="es"><seg id="1">{lg} A &amp; B & C </seg>'
                    f'<seg id="2">{lg} two</seg></doc><doc docid="n/2" origlang="en"><seg id="1">x</seg></doc>'
                    "</srcset>").encode() for lg in ("es", "en")}
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            for lg, data in sgm.items():
                info = tarfile.TarInfo(f"test/newstest2012-src.{lg}.sgm")
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
        paths = {"wmt12/test.tgz": self.write("wmt12/test.tgz", buffer.getvalue())}
        item = dict(id="wmt12/n/1/es-en", direction="es-en", origin=dict(dataset="wmt12", document="n/1",
                                                                       segments=[1, 2]))
        self.assertEqual(build.texts(item, paths), ("es A & B & C\nes two", "en A & B & C\nen two"))

    def test_assemble_checks_digests_and_writes_crlf(self):
        paths = {build.ntrex_key("en"): self.write(build.ntrex_key("en"), b'He said "yes".\n'),
                 build.ntrex_key("fr"): self.write(build.ntrex_key("fr"), "Il a dit « oui ».\n".encode())}
        item = dict(id="ntrex/1/en-fr", direction="en-fr", domain="news", doc="d", origin=dict(dataset="ntrex-128",
                    line=1), source_sha256=sha('He said "yes".'), reference_sha256=sha("Il a dit « oui »."))
        rows = build.assemble([item], paths)
        data = build.tsv_bytes(rows)
        self.assertTrue(data.startswith(b"id\tsrc\ttgt\tsource\treference\tdomain\tdoc\r\n"))
        self.assertIn(b'"He said ""yes""."', data)
        with self.assertRaises(ValueError):
            build.assemble([dict(item, source_sha256="0" * 64)], paths)


class GuardTest(unittest.TestCase):
    def test_output_must_be_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            with self.assertRaises(ValueError):
                prepare.check_location(root / "results", root)
            self.assertEqual(prepare.check_location(root / "private" / "x", root), root / "private" / "x")

    def test_locations_in_a_git_checkout(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as elsewhere:
            root = Path(tmp).resolve()
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            (root / ".gitignore").write_text("private/\nscratch/\n")
            for inside in ("datasets/dl", "results/v1", ".", "tools/cache"):
                with self.assertRaises(ValueError, msg=inside):
                    schema.safe_location(root / inside, root, "--downloads")
            for ignored in ("private/dl", "scratch/x/y"):
                self.assertEqual(schema.safe_location(root / ignored, root, "--downloads"), root / ignored)
            self.assertEqual(schema.safe_location(elsewhere, root, "--downloads"), Path(elsewhere).resolve())
            # prepare refuses before it reads a manifest or opens a connection.
            with self.assertRaises(ValueError) as context:
                prepare.main(root, out=root / "private/in", downloads=root / "datasets/dl", log=lambda m: None)
            self.assertIn("--downloads", str(context.exception))
            with self.assertRaises(ValueError):
                prepare.main(root, out=root / "results/in", log=lambda m: None)

    def test_pairs(self):
        self.assertEqual(prepare.parse_pairs("en-ja,ko"), ["ja", "ko"])
        with self.assertRaises(ValueError):
            prepare.parse_pairs("en-xx")


if __name__ == "__main__":
    unittest.main()
