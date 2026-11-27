"""The public-tree check on planted violations of every class, in throwaway Git repositories."""

import contextlib
import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("check_public_tree", ROOT / "tools/check_public_tree.py")
check_public_tree = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_public_tree)

NOREPLY = "someone@users.noreply.github.com"
sha = check_public_tree.sha

# Made-up names planted in the throwaway repositories. Their digests are injected into the checker's
# lists for the test only, so neither this file nor the checker holds a denied name in any form.
PLANTED = {
    "tokens": ["zzinternal-name-example"],
    "bigrams": ["Zzstage Zzexample"],
    "tokens_folded": ["zzplan-tier-example"],
    "bigrams_folded": ["zzvendor zztier"],
    "machine_tokens": ["zzmachinestate"],
    "machine_bigrams": ["zzmachine zzstate"],
    "salts": ["zzinternal-name-example/v9/speed/"],
}
EXTRA = {name: [sha(x) for x in values] for name, values in PLANTED.items()}


def join(*parts):
    """Made-up paths and addresses are assembled at run time, so this file itself passes the pattern rules."""
    return "".join(parts)


def git(root, *args, email=NOREPLY):
    env = dict(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL=email, GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL=email,
               HOME=str(root), GIT_CONFIG_NOSYSTEM="1", PATH="/usr/bin:/bin:/usr/local/bin")
    subprocess.run(["git", *args], cwd=root, env=env, check=True, capture_output=True)


class PublicTreeTest(unittest.TestCase):
    def repo(self, files, commit=True, email=NOREPLY):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        git(root, "init", "-q", "-b", "main")
        (root / ".gitignore").write_text("private/\n")
        for name, content in files.items():
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text(content, encoding="utf-8")
        git(root, "add", "-A")
        if commit:
            git(root, "commit", "-q", "-m", "x", email=email)
        return root

    def issues(self, root, history=False, extra=EXTRA):
        return {issue for _, issue in check_public_tree.check(root, history, extra)}

    def test_clean_repository(self):
        root = self.repo({"a.md": "Hy-MT2 30B-A3B (hy-mt2-30b-a3b), qwen-mt-lumen and DeepL API.\n",
                          "private/inputs.tsv": "ignored by Git\n"})
        self.assertEqual(self.issues(root), set())

    def test_shipped_lists_are_well_formed(self):
        for name, digests in check_public_tree.LISTS.items():
            self.assertTrue(digests, name)
            self.assertTrue(all(check_public_tree.DIGEST.fullmatch(d) for d in digests), name)
        self.assertEqual(set(PLANTED), set(check_public_tree.LISTS))
        with self.assertRaises(ValueError):
            check_public_tree.deny_lists({"tokens": ["not a digest"]})
        with self.assertRaises(ValueError):
            check_public_tree.deny_lists({"no-such-list": []})

    def test_planted_names_need_the_injected_digests(self):
        text = "via " + " and ".join(v for name, values in PLANTED.items() if name != "salts" for v in values) + "\n"
        root = self.repo({"a.md": text})
        self.assertEqual(self.issues(root, extra=None), set())
        self.assertEqual(self.issues(root), {"internal name", "machine state"})

    def test_internal_names(self):
        for text in ("the zzinternal-name-example run", "from Zzstage Zzexample on", "mod.zzinternal-name-example"):
            self.assertIn("internal name", self.issues(self.repo({"a.md": text + "\n"})), text)
        # Exact tokens and two-word phrases: case matters, and a word that merely contains the token passes.
        for text in ("the ZZINTERNAL-NAME-EXAMPLE run", "zzstage zzexample", "zzinternal-name-examples"):
            self.assertNotIn("internal name", self.issues(self.repo({"a.md": text + "\n"})), text)

    def test_plan_names_in_any_case(self):
        for text in ("zzplan-tier-example", "ZZPlan-Tier-Example", "Zzvendor Zztier", "ZZVENDOR ZZTIER"):
            self.assertIn("internal name", self.issues(self.repo({"a.md": f"via {text}\n"})), text)

    def test_machine_state(self):
        for text in ("the zzmachinestate was fine", "a ZZMachine ZZState note"):
            for name in ("a.md", "site/app.js", "b.json"):
                content = json.dumps({"note": text}) if name.endswith(".json") else text + "\n"
                self.assertIn("machine state", self.issues(self.repo({name: content})), (name, text))
        clean = "Each system was measured alone; a repetition that missed the conditions is flagged. Items swapped.\n"
        self.assertNotIn("machine state", self.issues(self.repo({"a.md": clean})))

    def test_machine_state_in_old_history_only(self):
        root = self.repo({"a.md": "zzmachinestate\n"})
        (root / "a.md").write_text("fine\n")
        git(root, "commit", "-q", "-am", "clean")
        self.assertNotIn("machine state", self.issues(root, history=True))

    def test_historical_salt_is_allowed(self):
        salt = PLANTED["salts"][0]
        self.assertEqual(self.issues(self.repo({"a.md": f"seed `{salt}`\n"})), set())
        self.assertIn("internal name", self.issues(self.repo({"a.md": f"seed `{salt}x/`\n"})))

    def test_deny_file_on_the_command_line(self):
        root = self.repo({"a.md": "via zzplan-tier-example\n"})
        deny = root.parent / (root.name + "-deny.json")
        deny.write_text(json.dumps(EXTRA))
        self.addCleanup(deny.unlink)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(check_public_tree.main([str(root), "--deny", str(deny)]), 1)
        self.assertIn("a.md: internal name", out.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(check_public_tree.main([str(root)]), 0)

    def test_paths(self):
        for text in (join("/", "Users/someone/x"), join("/", "Volumes/disk/x"), join("/", "home/someone"),
                     join("~", "/.cache/x"), join("C:", "\\", "Users\\x")):
            self.assertIn("local path", self.issues(self.repo({"a.md": f"see {text}\n"})), text)

    def test_emails_and_credentials(self):
        self.assertIn("email", self.issues(self.repo({"a.md": join("mail ", "someone", "@", "example.com\n")})))
        self.assertEqual(self.issues(self.repo({"a.md": f"mail {NOREPLY}\n"})), set())
        self.assertIn("credential", self.issues(self.repo({"a.md": join("token hf", "_abcdefghijklmnop\n")})))

    def test_commit_email_must_be_noreply(self):
        root = self.repo({"a.md": "fine\n"}, email=join("someone", "@", "example.com"))
        self.assertIn("commit email is not a GitHub noreply address", self.issues(root))

    def test_identity_fields(self):
        for key in ("account", "account_id", "plan", "billing_plan", "hostname", "serial_number", "username"):
            root = self.repo({"a.json": json.dumps({"x": {key: "abc"}})})
            self.assertIn("account, plan or identity field", self.issues(root), key)

    def test_natural_language_under_any_key(self):
        text = "The minister said the bridge would reopen next week after the repairs."
        cjk = "政府は来週の会議で新しい計画を発表する予定です"
        self.assertIn("natural-language text in a data field",
                      self.issues(self.repo({"rows.jsonl": json.dumps({"comment": text}) + "\n"})))
        self.assertIn("natural-language text in a data field",
                      self.issues(self.repo({"rows.jsonl": json.dumps({"x": cjk}, ensure_ascii=False) + "\n"})))
        self.assertIn("natural-language text in a data field",
                      self.issues(self.repo({"a.json": json.dumps({"label": text})})))
        # Documentation fields of configuration files may hold prose, item-row files may not.
        self.assertEqual(self.issues(self.repo({"a.json": json.dumps({"description": text})})), set())
        self.assertIn("natural-language text in a data field",
                      self.issues(self.repo({"results/v1/items/x.json": json.dumps({"description": text})})))

    def test_hard_cases_allow_list(self):
        label = {"source_label": "French (Switzerland, Canton of Vaud)", "target_label": "English"}
        row = {"id": 1, "pass": False, "verdicts": [False], "status": "ok", "translation_sha256": "0" * 64}
        clean = {"results/ltb-v1/items.jsonl": json.dumps(dict(label, id=1, rules=1)) + "\n",
                 "results/ltb-v1/rows/sys-a.jsonl": json.dumps(row) + "\n"}
        self.assertEqual(self.issues(self.repo(clean)), set())
        self.assertIn("field outside the hard-cases allow-list", self.issues(self.repo(
            {"results/ltb-v1/rows/sys-a.jsonl": json.dumps(dict(row, translation="ok")) + "\n"})))
        self.assertIn("file outside the hard-cases allow-list",
                      self.issues(self.repo({"results/ltb-v1/notes.txt": "x\n"})))
        self.assertIn("language label too long or missing", self.issues(self.repo(
            {"results/ltb-v1/items.jsonl": json.dumps({"id": 1, "source_label": "x" * 60}) + "\n"})))

    def test_overall_and_second_verifier_allow_list(self):
        overall = json.dumps({"schema": "translate-bench/overall@1", "systems": {"sys-a": {"overall": 50.0}}})
        second = json.dumps({"verifier": {"name": "X", "setting": "no reasoning-effort setting"},
                             "systems": {"sys-a": {"items": 2, "passed": {"a": 1, "b": 1}, "agreed": 2}}})
        clean = {"results/v1.1/overall.json": overall, "results/ltb-v1/second-verifier.json": second}
        self.assertEqual(self.issues(self.repo(clean)), set())
        self.assertIn("file outside the Overall-score allow-list",
                      self.issues(self.repo({"results/v1.1/notes.json": "{}"})))
        self.assertIn("file outside the hard-cases allow-list",
                      self.issues(self.repo({"results/ltb-v1/third-verifier.json": "{}"})))

    def test_input_files_are_never_published(self):
        self.assertIn("private or input file", self.issues(self.repo({"inputs.tsv": "id\tsource\n"})))

    def test_staged_and_committed_blobs(self):
        bad = join("see /", "Users/someone\n")
        root = self.repo({"a.md": bad})
        (root / "a.md").write_text("fine\n")  # the working copy is clean, the commit is not
        self.assertIn("local path", self.issues(root))
        root = self.repo({"a.md": "fine\n"})
        (root / "b.md").write_text(bad)
        git(root, "add", "b.md")
        (root / "b.md").write_text("fine\n")  # staged blob differs from the working copy
        self.assertIn("local path", self.issues(root))

    def test_history_scan(self):
        root = self.repo({"a.md": join("see /", "Users/someone\n")})
        (root / "a.md").write_text("fine\n")
        git(root, "commit", "-q", "-am", "clean")
        self.assertEqual(self.issues(root), set())
        self.assertIn("local path", self.issues(root, history=True))

    def test_synthetic_example_files(self):
        folder = "examples/external-predictions/data/"
        text = "The minister said the bridge would reopen next week after the repairs."
        tsv = f"id\tsrc\ttgt\tsource\treference\tdomain\tdoc\r\nsynthetic/s01/en-de\ten\tde\t{text}\tx\ts\td\r\n"
        jsonl = json.dumps({"id": "synthetic/s01/en-de", "translation": text}) + "\n"
        clean = self.repo({folder + "sentences.tsv": tsv, folder + "predictions.jsonl": jsonl})
        self.assertEqual(self.issues(clean), set())
        other = tsv.replace("synthetic/s01", "ntrex/1984")
        self.assertIn("synthetic example with an id outside synthetic/",
                      self.issues(self.repo({folder + "passages.tsv": other})))
        self.assertIn("private or input file", self.issues(self.repo({folder + "more.tsv": tsv})))
        self.assertIn("private or input file", self.issues(self.repo({"examples/sentences.tsv": tsv})))
        self.assertIn("natural-language text in a data field",
                      self.issues(self.repo({"examples/predictions.jsonl": jsonl})))


if __name__ == "__main__":
    unittest.main()
