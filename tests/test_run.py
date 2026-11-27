"""`translate-bench run` against a local fake OpenAI-compatible server, on the synthetic example inputs."""

import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path

from tests.fake_openai import Server
from translate_bench import cli, endpoint, run, schema

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ROOT / "examples/external-predictions/data"
REGISTRY = schema.read_json(ROOT / "configs/systems.json")


def options(*args):
    """Parsed `run` options with no backoff between retries."""
    parsed = cli.build_parser().parse_args(["run", *args])
    parsed.backoff = 0
    return parsed


class RunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "run"
        self.server = Server().__enter__()
        self.logs = []

    def tearDown(self):
        self.server.__exit__()
        self.tmp.cleanup()

    def run_items(self, *extra, model="fake"):
        args = ["--model", model, "--base-url", self.server.base_url, "--inputs", str(INPUTS),
                "--out", str(self.out), *extra]
        return run.main(ROOT, options(*args), log=self.logs.append)

    def journal(self):
        path = self.out / "predictions.jsonl"
        return {r["id"]: r for r in schema.read_jsonl(path)} if path.exists() else {}

    def test_success_and_run_record(self):
        self.assertEqual(self.run_items("--directions", "en-de", "--concurrency", "3"), 0)
        rows = self.journal()
        self.assertEqual(len(rows), 10)
        self.assertTrue(all(r["status"] == "ok" and r["attempts"] == 1 for r in rows.values()))
        row = rows["synthetic/s01/en-de"]
        self.assertEqual(row["translation"], "The new library opens at nine on weekdays.")  # the fake copies
        path, _, body = self.server.requests[0]
        self.assertEqual(path, "/v1/chat/completions")
        self.assertEqual(body["messages"][0]["content"][:43], "Translate from English into German. Return ")
        self.assertEqual((body["temperature"], body["max_tokens"], body["seed"]), (0, 512, 42))
        record = schema.read_json(self.out / "run.json")
        self.assertEqual(record["settings"]["endpoint"], "local endpoint")
        self.assertNotIn(str(self.server.httpd.server_address[1]), (self.out / "run.json").read_text())
        self.assertEqual(len({r["settings_sha256"] for r in rows.values()}), 1)
        self.assertEqual(record["settings"]["prompt"]["profile"], "generic-instruction")
        self.assertEqual(record["counts"], dict(items=10, ok=10, empty=0, timeout=0, error=0, selected_not_run=0))
        self.assertEqual(record["sessions"][0]["directions"], ["en-de"])
        self.assertFalse(record["inputs"]["verified_release_items"])
        self.assertEqual(record["tool"], "translate-bench 1.1.0")

    def test_http_500_then_success(self):
        self.server.script = ["500", "500"]
        self.assertEqual(self.run_items("--directions", "en-ja", "--types", "passage"), 0)
        rows = self.journal()
        self.assertEqual([r["status"] for r in rows.values()], ["ok", "ok"])
        self.assertEqual(rows["synthetic/p01/en-ja"]["attempts"], 3)
        self.server.script = ["500"] * 4  # the first attempt and all three retries
        self.out = Path(self.tmp.name) / "again"
        self.run_items("--directions", "en-ja", "--types", "passage")
        first = self.journal()["synthetic/p01/en-ja"]
        self.assertEqual((first["status"], first["attempts"]), ("error", 4))
        self.assertIn("HTTP 500", first["error"])

    def test_timeout_empty_and_length(self):
        self.server.script = ["timeout", "empty", "length"]
        self.assertEqual(self.run_items("--directions", "en-de", "--types", "passage", "--timeout", "0.5",
                                        "--limit", "1"), 0)
        self.assertEqual(self.journal()["synthetic/p01/en-de"]["status"], "timeout")
        self.run_items("--directions", "en-de", "--types", "passage", "--timeout", "0.5")
        self.assertEqual(self.journal()["synthetic/p02/en-de"]["status"], "empty")
        self.out = Path(self.tmp.name) / "length"
        self.run_items("--directions", "en-de", "--types", "passage", "--timeout", "0.5", "--limit", "1")
        row = self.journal()["synthetic/p01/en-de"]
        self.assertEqual(row["status"], "error")
        self.assertIn("finish_reason 'length'", row["error"])
        self.assertIsNone(row["translation"])

    def test_resume_sends_only_missing_items(self):
        self.assertEqual(self.run_items("--limit", "2"), 0)
        self.assertEqual(len(self.server.requests), 8)  # 2 of each of the four cells
        with (self.out / "predictions.jsonl").open("ab") as stream:
            stream.write(b'{"id": "synthetic/s08/en-de", "sta')  # an interrupted write
        self.assertEqual(self.run_items(), 0)
        self.assertEqual(len(self.server.requests), 20)
        rows = schema.read_jsonl(self.out / "predictions.jsonl")
        self.assertEqual(len(rows), 20)
        self.assertEqual(len({r["id"] for r in rows}), 20)
        record = schema.read_json(self.out / "run.json")
        self.assertEqual(len(record["sessions"]), 2)
        self.assertEqual(self.run_items(), 0)  # nothing left
        self.assertEqual(len(self.server.requests), 20)
        with self.assertRaises(ValueError) as context:
            self.run_items("--temperature", "0.7")
        self.assertIn("other settings (generation)", str(context.exception))

    def test_stop_on_configuration_error_and_refused_connection(self):
        self.server.script = ["404"]
        self.assertEqual(self.run_items("--directions", "en-de", "--types", "passage"), 3)
        self.assertEqual(self.journal(), {})  # the stop journals nothing for the item in hand
        record = schema.read_json(self.out / "run.json")
        self.assertIn("HTTP 404", record["sessions"][0]["stop"])
        self.out = Path(self.tmp.name) / "refused"
        port = self.server.httpd.server_address[1]
        self.server.__exit__()
        self.server = Server().__enter__()  # tearDown closes this one
        args = options("--model", "m", "--base-url", f"http://127.0.0.1:{port}/v1", "--inputs", str(INPUTS),
                       "--out", str(self.out), "--retries", "1")
        self.assertEqual(run.main(ROOT, args, log=self.logs.append), 3)
        self.assertEqual(self.journal(), {})
        self.assertTrue(any("stopped answering" in line for line in self.logs))

    def test_api_key_from_environment_is_sent_and_never_written(self):
        key = "test-key-" + "0123456789abcdef"
        os.environ["TB_TEST_KEY"] = key
        self.addCleanup(os.environ.pop, "TB_TEST_KEY", None)
        self.assertEqual(self.run_items("--api-key-env", "TB_TEST_KEY", "--directions", "en-de", "--limit", "1"), 0)
        headers = self.server.requests[0][1]
        self.assertEqual(headers.get("Authorization"), f"Bearer {key}")
        for path in self.out.iterdir():
            self.assertNotIn(key, path.read_text(encoding="utf-8"), path.name)
        self.assertNotIn(key, "\n".join(self.logs))
        self.assertTrue(schema.read_json(self.out / "run.json")["authenticated"])
        os.environ["TB_TEST_KEY"] = ""
        with self.assertRaises(ValueError):
            self.run_items("--api-key-env", "TB_TEST_KEY")

    def test_out_must_not_be_published(self):
        with self.assertRaises(ValueError):
            run.main(ROOT, options("--model", "m", "--base-url", self.server.base_url, "--inputs", str(INPUTS),
                                   "--out", str(ROOT / "results" / "mine")), log=self.logs.append)

    def test_predictions_feed_score(self):
        from translate_bench import score

        self.assertEqual(self.run_items(), 0)
        out = Path(self.tmp.name) / "score"
        sid, rows, summary = score.main(ROOT, self.out / "predictions.jsonl", INPUTS, "chrf", "fake", out,
                                        log=lambda m: None)
        self.assertEqual((summary["attempted"], summary["scored"]), (20, 20))
        system = schema.read_json(out / "system.json")
        self.assertEqual(system["predictions_sha256"], schema.read_json(self.out / "run.json")["predictions_sha256"])


class ResumeTest(unittest.TestCase):
    """A run killed mid-way, then resumed with other settings or against another endpoint."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "run"
        self.server = Server(delay=0.2).__enter__()

    def tearDown(self):
        self.server.__exit__()
        self.tmp.cleanup()

    def run_items(self, *extra, base_url=None):
        args = ["--model", "fake", "--base-url", base_url or self.server.base_url, "--inputs", str(INPUTS),
                "--out", str(self.out), *extra]
        return run.main(ROOT, options(*args), log=lambda m: None)

    def test_kill_then_resume_with_other_settings_is_refused(self):
        import subprocess
        import sys
        import time

        command = [sys.executable, "-m", "translate_bench.cli", "run", "--model", "fake", "--base-url",
                   self.server.base_url, "--inputs", str(INPUTS), "--out", str(self.out)]
        process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        journal = self.out / "predictions.jsonl"
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not (journal.exists() and journal.read_text().count("\n") >= 3):
            time.sleep(0.05)
        process.kill()  # no chance to write anything at the end
        process.wait()
        kept = schema.read_jsonl(journal)
        self.assertGreaterEqual(len(kept), 3)
        self.assertLess(len(kept), 20)
        record = schema.read_json(self.out / "run.json")  # written before the first request
        self.assertEqual(record["settings"]["generation"]["fields"]["temperature"], 0)
        self.assertIsNone(record["sessions"][-1]["ended"])
        with self.assertRaises(ValueError) as context:
            self.run_items("--temperature", "0.7")
        self.assertIn("other settings (generation)", str(context.exception))
        (self.out / "run.json").unlink()  # the rows alone still refuse other settings
        with self.assertRaises(ValueError) as context:
            self.run_items("--temperature", "0.7")
        self.assertIn("made with other settings or another endpoint", str(context.exception))
        self.assertEqual(self.run_items(), 0)
        rows = schema.read_jsonl(journal)
        self.assertEqual(len(rows), 20)
        self.assertEqual(rows[:len(kept)], kept)
        self.assertEqual(len({r["settings_sha256"] for r in rows}), 1)

    def test_another_endpoint_with_the_same_model_name_is_refused(self):
        self.assertEqual(self.run_items("--limit", "1"), 0)
        with Server() as other:
            with self.assertRaises(ValueError) as context:
                self.run_items(base_url=other.base_url)
            self.assertEqual(other.requests, [])
        self.assertIn("made with other settings or another endpoint", str(context.exception))


class EndpointPrivacyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "run"
        self.server = Server().__enter__()
        self.logs = []
        os.environ["TB_TEST_KEY"] = "test-key-" + "fedcba9876543210"
        self.addCleanup(os.environ.pop, "TB_TEST_KEY", None)

    def tearDown(self):
        self.server.__exit__()
        self.tmp.cleanup()

    def run_items(self, *extra):
        args = ["--model", "fake", "--base-url", self.server.base_url, "--api-key-env", "TB_TEST_KEY",
                "--inputs", str(INPUTS), "--out", str(self.out), "--directions", "en-de", *extra]
        return run.main(ROOT, options(*args), log=self.logs.append)

    def written(self):
        return "\n".join(path.read_text(encoding="utf-8") for path in self.out.iterdir()) + "\n".join(self.logs)

    def test_a_redirect_is_not_followed_with_the_key(self):
        from tests.fake_openai import BODY_MARKER

        with Server() as elsewhere:
            self.server.redirect_to = elsewhere.base_url + "/chat/completions"
            self.server.script = ["redirect"]
            self.assertEqual(self.run_items(), 3)
            self.assertEqual(elsewhere.requests, [])  # the key never reached the other address
        self.assertFalse((self.out / "predictions.jsonl").exists())
        stop = schema.read_json(self.out / "run.json")["sessions"][-1]["stop"]
        self.assertIn("HTTP 307 Temporary Redirect, a redirect; redirects are not followed", stop)
        self.assertNotIn(os.environ["TB_TEST_KEY"], self.written())
        self.assertNotIn(BODY_MARKER, self.written())

    def test_error_bodies_are_not_kept(self):
        from tests.fake_openai import BODY_MARKER

        self.server.script = ["400"] + ["500"] * 4 + ["404"]
        self.assertEqual(self.run_items("--retries", "3", "--concurrency", "1"), 3)
        rows = [r for r in schema.read_jsonl(self.out / "predictions.jsonl")]
        self.assertEqual([r["error"] for r in rows], ["HTTP 400 Bad Request", "HTTP 500 Internal Server Error"])
        stop = schema.read_json(self.out / "run.json")["sessions"][-1]["stop"]
        self.assertTrue(stop.startswith("HTTP 404 Not Found from local endpoint: the URL or model was not found"))
        self.assertNotIn(BODY_MARKER, self.written())

    def test_record_endpoint_is_an_opt_in(self):
        self.assertEqual(self.run_items("--limit", "1", "--record-endpoint"), 0)
        port = self.server.httpd.server_address[1]
        self.assertEqual(schema.read_json(self.out / "run.json")["settings"]["endpoint"], f"http://127.0.0.1:{port}")

    def test_labels(self):
        cases = {"http://127.0.0.1:8080/v1": "local endpoint", "http://localhost:11434/v1": "local endpoint",
                 "http://[::1]:8000/v1": "local endpoint", "http://10.0.0.5:8000/v1": "private endpoint",
                 "http://192.168.1.20/v1": "private endpoint", "http://gpu-box.local:8080/v1": "private endpoint",
                 "http://gpu-box:8080/v1": "private endpoint", "https://llm.corp/v1": "private endpoint",
                 "https://vm.c.example.internal/v1": "private endpoint",
                 "https://box.tail0.ts.net/v1": "private endpoint",
                 "https://api.example.com:8443/v1/chat/completions?k=1": "https://api.example.com",
                 "https://8.8.8.8/v1": "https://8.8.8.8"}
        for url, expected in cases.items():
            self.assertEqual(endpoint.recorded(url), expected, url)
        self.assertEqual(endpoint.recorded("http://gpu-box.local:8080/v1/x", record=True), "http://gpu-box.local:8080")


class InterruptTest(unittest.TestCase):
    def test_ctrl_c_keeps_finished_items_and_sends_nothing_new(self):
        import threading
        import time

        started, committed = [], []
        lock = threading.Lock()

        def work(task):
            with lock:
                started.append(task)
            time.sleep(0.05)
            return task

        def commit(task, result):
            committed.append(task)
            if len(committed) == 1:
                raise KeyboardInterrupt

        result = endpoint.run_all(range(50), work, commit, concurrency=3, log=lambda m: None)
        self.assertTrue(result["interrupted"])
        self.assertLess(len(started), 50)
        self.assertEqual(sorted(committed), sorted(started))  # every request in flight was still committed


class PromptTest(unittest.TestCase):
    def render(self, name, src, tgt, text="Hello there."):
        return run.render(run.load_prompt(REGISTRY, name), src, tgt, text)

    def test_profiles_render_like_the_release(self):
        self.assertEqual(self.render(None, "ja", "en"),
                         ("Translate from Japanese into English. Return only the translation.\n\nHello there.", {}))
        content, fields = self.render("plamo", "en", "zh-Hans")
        self.assertEqual(content, "Hello there.")
        self.assertEqual(fields["chat_template_kwargs"], dict(source_lang="en", target_lang="zh-hans"))
        self.assertEqual(fields["stop"], ["<|plamo:tag|>", "<|plamo:bos|>"])
        self.assertTrue(self.render("hy-mt", "en", "zh-Hans")[0].startswith("将以下文本翻译为简体中文"))
        self.assertTrue(self.render("hy-mt", "en", "ko")[0].startswith("Translate the following text into Korean."))
        self.assertTrue(self.render("index-translate", "ar", "en")[0].startswith("请将以下阿拉伯语文本翻译为英语"))
        content, fields = self.render("translategemma", "zh-Hans", "en", " x ")
        self.assertIn("You are a professional Chinese (zh-Hans) to English (en) translator.", content)
        self.assertTrue(content.endswith("into English:\n\n\nx<end_of_turn>\n<start_of_turn>model\n"))
        self.assertEqual(run.load_prompt(REGISTRY, "translategemma")["kind"], "completions")

    def test_unavailable_profiles_and_prompt_files(self):
        for name in ("seed-x", "cloud-batch-json", "deepl-text", "nope"):
            with self.assertRaises(ValueError):
                run.load_prompt(REGISTRY, name)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prompt.txt"
            path.write_text("Into {target}, please: {text} {\"json\": 1}", encoding="utf-8")
            prompt = run.load_prompt(REGISTRY, prompt_file=path)
            self.assertEqual(run.render(prompt, "en", "de", "Hi")[0], "Into German, please: Hi {\"json\": 1}")
            path.write_text("Into {targte}: {text}", encoding="utf-8")
            with self.assertRaises(ValueError):
                run.load_prompt(REGISTRY, prompt_file=path)

    def test_settings_from_a_release_system(self):
        parsed = options("--model", "m", "--base-url", "http://127.0.0.1:1/v1", "--out", "x",
                         "--settings-from", "gemma-4-e4b-it", "--max-tokens", "256")
        prompt, generation, timeout, source = run.resolve_settings(REGISTRY, parsed)
        content, fields = run.render(prompt, "en", "ja", "Hi")
        body = run.request_body("m", prompt, content, fields, generation)
        self.assertEqual(body["chat_template_kwargs"], {"enable_thinking": False})
        self.assertEqual((body["top_k"], body["top_p"], body["temperature"], body["max_tokens"]), (64, 0.95, 1.0, 256))
        self.assertEqual((prompt["name"], timeout, source["id"]), ("generic-instruction", 120, "gemma-4-e4b-it"))
        parsed.settings_from = "hy-mt2-30b-a3b"
        self.assertEqual(run.resolve_settings(REGISTRY, parsed)[2], 60)
        parsed.settings_from = "seed-x-ppo-7b"
        with self.assertRaises(ValueError):
            run.resolve_settings(REGISTRY, parsed)
        parsed.settings_from, parsed.extra_body, parsed.seed = None, '{"top_k": 5, "seed": 1}', "none"
        prompt, generation, _, _ = run.resolve_settings(REGISTRY, parsed)
        body = run.request_body("m", prompt, "x", {}, generation)
        self.assertEqual((body["top_k"], body["seed"]), (5, 1))
        parsed.extra_body, parsed.temperature, parsed.max_tokens = None, "none", "None"
        body = run.request_body("m", prompt, "x", {}, run.resolve_settings(REGISTRY, parsed)[1])
        self.assertEqual(set(body), {"model", "messages"})
        parsed.temperature = "warm"
        with self.assertRaises(ValueError):
            run.resolve_settings(REGISTRY, parsed)


class LockTest(unittest.TestCase):
    def test_a_second_run_is_refused_and_leaves_the_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            with endpoint.locked(tmp, "run.lock"):
                with self.assertRaises(RuntimeError):
                    with endpoint.locked(tmp, "run.lock"):
                        pass
                self.assertTrue((Path(tmp) / "run.lock").exists())
                with self.assertRaises(RuntimeError):  # still held by the first
                    with endpoint.locked(tmp, "run.lock"):
                        pass
            self.assertFalse((Path(tmp) / "run.lock").exists())
            with endpoint.locked(tmp, "run.lock"):
                pass


class EndpointTest(unittest.TestCase):
    def test_urls_keep_no_credentials_or_query(self):
        user = "https://user:secret" + "@"  # kept apart so the public-tree check does not read an address
        url = endpoint.resolve(user + "api.example.com:8443/v1?api-version=2#frag")
        self.assertEqual(url, user + "api.example.com:8443/v1/chat/completions?api-version=2")
        self.assertEqual(endpoint.public_url(url), "https://api.example.com:8443/v1/chat/completions")
        self.assertEqual(endpoint.resolve("http://127.0.0.1:8080"), "http://127.0.0.1:8080/v1/chat/completions")
        self.assertEqual(endpoint.resolve("http://h/v1/", "completions"), "http://h/v1/completions")
        self.assertEqual(endpoint.resolve("http://h/v1/chat/completions"), "http://h/v1/chat/completions")
        with self.assertRaises(ValueError):
            endpoint.resolve("ftp://h/v1")

    def test_served_model_names_lose_local_paths(self):
        self.assertEqual(run.served("org/model-7b"), "org/model-7b")
        self.assertEqual(run.served("/".join(["", "srv", "models", "m.gguf"])), "m.gguf")
        self.assertEqual(run.served("C:\\models\\m.gguf"), "m.gguf")


class CommandTest(unittest.TestCase):
    def evaluate(self, root, server, *extra):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["--root", str(root), "evaluate", "--model", "fake", "--base-url", server.base_url,
                             "--out", str(root / "private/eval"), *extra])
        return code, out.getvalue(), err.getvalue()

    def test_evaluate_picks_the_view_and_reports_failures(self):
        from tests.fixtures import release_with_inputs

        with tempfile.TemporaryDirectory() as tmp, Server() as server:
            root = release_with_inputs(Path(tmp) / "release", ["en-ja", "ja-en"])
            code, out, err = self.evaluate(root, server, "--types", "sentence", "--concurrency", "4")
            self.assertEqual(code, 0, err)
            header = next(line for line in out.splitlines() if line.startswith("fake: chrf (chosen"))
            self.assertIn(") sentence ", header)  # compared on the sentence view, the one that was run
            self.assertIn("Rank ", out)
            code, out, err = self.evaluate(root, server, "--types", "sentence", "--view", "overall")
            self.assertEqual(code, 2)  # nothing to compare on the overall view
            self.assertIn("translate-bench compare: No complete overall cell", err)
            code, out, err = self.evaluate(root, server, "--types", "sentence", "--metrics", "nope")
            self.assertEqual(code, 2)
            server.script = ["404"]
            code, out, err = self.evaluate(root, server, "--types", "passage")
            self.assertEqual(code, 3)  # the run stopped; nothing was scored

    def test_evaluate_runs_scores_and_compares(self):
        with tempfile.TemporaryDirectory() as tmp, Server() as server:
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli.main(["evaluate", "--model", "fake", "--base-url", server.base_url, "--inputs", str(INPUTS),
                                 "--out", str(Path(tmp) / "eval")])
            self.assertEqual(code, 0, err.getvalue())
            self.assertTrue((Path(tmp) / "eval/score/items/fake.jsonl").is_file())
        self.assertIn("NOT the verified release inputs", out.getvalue())
        self.assertIn("Not comparable with the published results", out.getvalue())


if __name__ == "__main__":
    unittest.main()
