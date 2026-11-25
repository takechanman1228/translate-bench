"""Check what this repository would publish for test texts, local paths, identities and internal vocabulary.

    python tools/check_public_tree.py [ROOT] [--history] [--deny FILE]

Scans every blob Git would publish: the index (staged), HEAD (committed) and the working copy of
tracked and untracked, not ignored files; with --history, every blob reachable from any ref. It
also checks every commit's author and committer email. It reports file names and rule names only,
never the matched content, and exits with status 1 on any finding.

The denied internal names and subscription plan names are stored as SHA-256 digests of word
tokens and two-word phrases, so this file does not publish them. Words that describe the measuring
machine's state at run time are denied the same way, in every text file, Markdown and JavaScript
included. Historical seed strings that must stay verbatim are recognised by their digests.

`--deny FILE` (or `extra=` of `check`) adds digests to these lists for one run: a JSON object whose
keys are names of LISTS and whose values are lists of SHA-256 digests. The tests use it to plant
made-up names, so the tree never holds a denied name in any form.
"""

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# SHA-256 of denied word tokens: the lab notebook's system ids, view names, package and folder names.
TOKENS = {
    "fe600826cd681ad64b6a2aa635e9ff759dbbf1043b871043f9e0740dd85da850",
    "8d6948358e8e12d37abea68a9df94350e5efa9df33c064ad9ae96343b59abbaa",
    "8a0ec91bf53471ddcb94cc63b047e5da5bf897eac3e7e313c2f0c6d46c85f2e6",
    "9a3e5e0287c81db45de6fc4b98941ab0cf9aadd86b4e9dbe80154cb40377e318",
    "3434166c5909fd1b2edb3af5c3d575da1913611c998f61ed6372d2462cf62d52",
    "42f4f2f8fffc2586ec5b5a23148ba381473894164ae4fd4a4bf045d76ead9d51",
    "c7d3ac01f3d50a8617e851eaa6f341725da3effdcf6778e2c943a92cb13e2d11",
    "89515c9e792505152e4f34e624dd0ec313836546ccb5a7293b1f4db32b717ea5",
    "02db36013741a5b0ca810cc02fc93e85f985d62a442f0c3a9896c0e143092196",
    "c1684a8ccdcc73d9d09fec3dc0eb23486b0295df3d306c1b432d09b874893830",
    "180bae324033de55c12330d0eb0584a47d90f400d037742b9310ed116a4df90c",
    "6a4c975fde037f0f2afd7a7d905d23bca4da9bb94601d832cc35f5b9091f9aa0",
    "cccb56f77a407bbdc1285cdbb2a318cdf0e11343846dd19a938977974ce38f0c",
    "682da9e9b2595c64369c1f18836f4bfe8711b9a9173ecf30b2b9050adb46920b",
    "5b72e85a34a225974caad3d0c8695e16dfc6bc7c3aba8fc4a65594372effe765",
    "052a9504e4000e10eff2a53428d0b1049193548b7fe335a8ee6b8501236b1e17",
    "368d133688c3d92f4a51165948cd848e61d74686598833687c7812d7b6b646be",
    "a7b9a042ed47b2e33c54acf5b92815729f08e700415a38a8d744a7938f773f4c",
    "9ef694485338117e263a0e1f97c5ed1ec3fbfaedb76de7a235492a03507354a8",
    "b5ed6ce7d0c2393ee5e9883b31634bd76e4281cb59aa1cbed31009b8e6ab7af6",
    "92dc6e4146c1568240352fd10f0185545dd52460f74819389736c803cf4bd00b",
    "4207cbf998b296953d96a57ac1beb5a5c0d5e6c7a47981545eeecbda1d0c669f",
    "db7161f97a17a0c9211eec598393705230da575d6d5b7a4252c864a765aaf3aa",
    "456f45fddc2e725c2948d03317e2262c2ec8e86745af28dc7b2221987b858b50",
    "1f92417bcf48abf294ca7881c31ffece458305a0103efeac031b10d1e4fd178a",
    "b6c35dd7dbbeaf0874b575fca89a37b795689f3552888ba218e09e53b33f6ee1",
    "bbc7db099aafbde4a8e2ab12a0e827fe2b3c9f3b7129262fcf2cc106036102a0",
    "6454fd232da1186575363463432e82f42df810478b6b6953d5fc5cb463ad4f85",
    "0ae576f131b01044634d4274b8a6197926c8859dcb63025f5c4ef31cd7f42b01",
    "8889c92c40b0663b27245e99ebb48298b85e506062128fe749de9d33d6643d40",
    "bebfedc0a3c11bc073f937d1a782ff752b209ecdae5249ae014830f51fd4d44c",
    "fa3c844fc85471623265435e902e9deb7d48840a01ee5af4e453ed3219392556",
    "04aa3af5234e66a13aa4f89044e71a14602b47d945787ffff5c8ca9abfd4e396",
    "6819f768ae25aaafabe5d0c47fd39eba0b4f095b68e52147c11c6809d10e2430",
    "63e1849877972f8f8d2dce958a18b4cba82f78bbee9440379db3d1724d4a5062",
    "0d1d3c39bace9fa7918acbb06ef01935bfe851fc1c82f074889d25db4a29222b",
    "c8361f9b468e68c86da024270e0949ce139cb704b8d7cce586681b99f3a7ea56",
}
# SHA-256 of denied two-word phrases (internal stage names).
BIGRAMS = {
    "6c504b3dd0752d18386e9380409342d46fc94bc93e9a5ccc44cbe1ef149ed2f5",
    "5c72ab80931bb7383391b9de913e819081b3a3e1261191d36702c897e53d8dbb",
}
# SHA-256 of denied tokens and two-word phrases compared in lower case: subscription plan and tier names.
TOKENS_FOLDED = {
    "8ca990aad02365585fa352e1330e6f13c33125d482e978304b06a444dc74198c",
}
BIGRAMS_FOLDED = {
    "ca13a02495b57b5467ad522dc40cb3b5f1f8379fc8eeb2deb8ea404e4039b3b7",
    "e305e9e079b463edccbc45d33cf685f497d3c9d2b3996178d5f41e3ead50b045",
    "9763d02b20c6d3f154ceee6a46db229d1f7fc8a3606cd990d9d0b6a631ea37ff",
    "ef645c28621e5f0fa8d744d352a15c57384267c566652933984269067cd5128c",
    "11e37342fdb41ce9417c913f2d1334b5652cd0250b8377d45a21b13820ce2b4d",
    "24b7d2f15b1c184f2fe0dad52c734e208b2d131cd1e307fabde20a7187857204",
}
# SHA-256 of words and two-word phrases that describe the state of the measuring machine at run time (lower case).
# Only the machine's specification may be published, never its observed state.
MACHINE_TOKENS = {
    "da47c2f450a4f9d538d86d600d55149afd39d6672fdd1f30c68ad5be21cadad8",
}
MACHINE_BIGRAMS = {
    "8729f78c31ddfd26549e70bf5ef14df21e4f2e428705ae121fd97554f55babf4",
    "ea93c87a1361e49b5b3e5112d29e12c8db1d7ca97fe5497117e2992b9dddedbf",
    "47d919c894133dfd95ce99e016b1174502244f25784d8e790bd04c97caaf18a6",
    "c975a9f23f1cbc197eb8f6d56e623169f35778d737b002d326ea20e6d8b889cb",
}
# SHA-256 of historical seed strings that define frozen selections; they are published verbatim.
SALTS = {
    "914ca56bd90d8ff616c2a0fa08c4fea5b7c11cdf24f5d592880f53b9e8efc601",
    "1949fab5a7666bed377b93c6edd771fb4e1db84ca082e35b1f8a8eaf9f0b2644",
    "173142c965c12bef33e0c5e31fde6f05316d96ac4d523019dfce0a6eb635fbff",
}
# The hashed lists by name, as `--deny` and `check(extra=...)` address them.
LISTS = {"tokens": TOKENS, "bigrams": BIGRAMS, "tokens_folded": TOKENS_FOLDED, "bigrams_folded": BIGRAMS_FOLDED,
         "machine_tokens": MACHINE_TOKENS, "machine_bigrams": MACHINE_BIGRAMS, "salts": SALTS}
DIGEST = re.compile(r"[0-9a-f]{64}")
NOREPLY = re.compile(r"[\w.+-]+@users\.noreply\.github\.com")
RULES = {
    # Character classes keep these patterns from matching their own source text.
    "local path": (r"/[U]sers/|/[h]ome/[a-z]|/[V]olumes/|/private/[v]ar/|/private/[t]mp/|[A-Z]:\\[U]sers"
                   r"|(?<![\w.])~/[\w.]"),
    "email": r"(?<![\w.-])[\w.%+-]+@[\w-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b",
    "credential": r"\b(?:sk-(?:ant-)?[A-Za-z0-9_-]{12,}|AIza[\w-]{20,}|hf_[A-Za-z0-9]{12,}|gh[pousr]_[A-Za-z0-9]{12,}"
                  r"|github_pat_\w{12,}|[\w-]{12,}:fx)\b|\bBearer[ \t]+[A-Za-z0-9]|-----BEGIN [A-Z ]*PRIVATE KEY",
    "lab-notebook path": r"\bresults/v2(?:-sizes)?\b|\brecheck-2026-11-23\b",
}
PATTERNS = {name: re.compile(p) for name, p in RULES.items()}
IDENTITY_FIELD = re.compile(
    r"(?i)^(?:accounts?|account_\w+|\w+_account|plans?|plan_\w+|\w+_plan|user|users|username|user_?id|user_name"
    r"|e?_?mail|email_address|hostname|host_?name|host|serial|serial_number|machine_id|hardware_uuid|uuid"
    r"|session_?id|thread_?id|conversation_?id|api_?key|password|secret|billing|invoice|balance)$")
# JSON keys whose values are documentation written for this repository (not test text).
DOC_KEYS = {"description", "rule", "note", "method", "caveats", "basis", "memory_note", "support_note", "exception",
            "aggregation", "message", "message_chinese", "prompt", "payload", "invocation", "name", "helper", "machine"}
PRIVATE_FILES = re.compile(r"(?:^|/)(?:private|\.cache)/|\.(?:tsv|gguf|safetensors|ckpt|bin)$|(?:^|/)\.env")
BINARY_OK = (".png",)
# The self-written synthetic example set (CC0) may hold text, under ids that start with "synthetic/" only.
SYNTHETIC = re.compile(r"^examples/external-predictions/data/(?:sentences\.tsv|passages\.tsv|predictions\.jsonl)$")
WORD = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_-]*")
SALT_CANDIDATE = re.compile(r"[\w.-]+(?:/[\w.-]+)+/")


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def deny_lists(extra=None):
    """The shipped hashed lists, each extended by the digests that `extra` gives under the same name."""
    extra = extra or {}
    unknown = set(extra) - set(LISTS)
    if unknown:
        raise ValueError(f"Unknown deny lists: {', '.join(sorted(unknown))}")
    lists = {}
    for name, shipped in LISTS.items():
        added = set(extra.get(name, ()))
        if any(not isinstance(d, str) or not DIGEST.fullmatch(d) for d in added):
            raise ValueError(f"Deny list {name}: every entry must be a lower-case SHA-256 hex digest")
        lists[name] = frozenset(shipped) | added
    return lists


def git(root, *args, data=None):
    return subprocess.run(["git", *args], cwd=root, input=data, capture_output=True, check=True).stdout


def blobs(root, history=False):
    """{(path, object id or None): bytes} for everything Git would publish."""
    found = {}
    if not (root / ".git").exists():
        for p in root.rglob("*"):
            if p.is_file() and ".git" not in p.parts:
                found[p.relative_to(root).as_posix(), None] = p.read_bytes()
        return found
    ids = {}
    for line in git(root, "ls-files", "-s", "-z").split(b"\0"):
        if line:
            meta, path = line.split(b"\t", 1)
            ids[path.decode(), meta.split()[1].decode()] = None
    if _has_head(root):
        for line in git(root, "ls-tree", "-r", "-z", "HEAD").split(b"\0"):
            if line:
                meta, path = line.split(b"\t", 1)
                ids[path.decode(), meta.split()[2].decode()] = None
    if history:
        for line in git(root, "rev-list", "--objects", "--all").decode().splitlines():
            parts = line.split(" ", 1)
            if len(parts) == 2:
                ids[parts[1], parts[0]] = None
    objects = list(ids)
    if objects:
        out = git(root, "cat-file", "--batch", data="".join(f"{oid}\n" for _, oid in objects).encode())
        position = 0
        for path, oid in objects:
            header_end = out.index(b"\n", position)
            header = out[position:header_end].split()
            if header[1] != b"blob":
                position = header_end + 1 + int(header[2]) + 1 if len(header) > 2 else header_end + 1
                continue
            size = int(header[2])
            found[path, oid] = out[header_end + 1:header_end + 1 + size]
            position = header_end + 1 + size + 1
    tracked = {path for path, _ in ids}
    for line in git(root, "ls-files", "-z", "--others", "--exclude-standard", "--cached").split(b"\0"):
        path = line.decode()
        if path and (root / path).is_file() and not (root / path).is_symlink():
            data = (root / path).read_bytes()
            if path not in tracked or data not in {v for (p, _), v in found.items() if p == path}:
                found[path, "working copy"] = data
    return found


def _has_head(root):
    return subprocess.run(["git", "rev-parse", "--verify", "-q", "HEAD"], cwd=root, capture_output=True).returncode == 0


def identity_problems(root):
    if not (root / ".git").exists() or not _has_head(root):
        return []
    problems = []
    for line in git(root, "log", "--all", "--format=%H %ae %ce").decode().splitlines():
        commit, *emails = line.split()
        if any(not NOREPLY.fullmatch(e) for e in emails):
            problems.append((f"commit {commit[:12]}", "commit email is not a GitHub noreply address"))
    return problems


def natural(value):
    """Natural-language text of some length: what a test text, a reference or an output looks like."""
    if not isinstance(value, str):
        return False
    text = value.strip()
    if re.fullmatch(r"https?://\S+|[0-9a-f]{32,128}|[A-Za-z0-9_./+-]+", text):
        return False
    letters = sum(c.isalpha() for c in text)
    wide = sum(c.isalpha() and ord(c) > 0x024F for c in text)
    return letters >= 12 and (len(text.split()) >= 5 or wide >= 6)


def denied_words(text, lists=None):
    lists = lists or deny_lists()
    for salt in set(SALT_CANDIDATE.findall(text)):
        if sha(salt) in lists["salts"]:
            text = text.replace(salt, " ")
    words = {w.rstrip("-") for w in WORD.findall(text)}
    if any(sha(w) in lists["tokens"] or sha(w.lower()) in lists["tokens_folded"] for w in words):
        return True
    plain = re.findall(r"[A-Za-z0-9_]+", text)
    pairs = {f"{a} {b}" for a, b in zip(plain, plain[1:])}
    return any(sha(pair) in lists["bigrams"] or sha(pair.lower()) in lists["bigrams_folded"] for pair in pairs)


def machine_state(text, lists=None):
    lists = lists or deny_lists()
    words = {w.lower() for w in re.findall(r"[A-Za-z0-9_]+", text)}
    if any(sha(w) in lists["machine_tokens"] for w in words):
        return True
    plain = [w.lower() for w in re.findall(r"[A-Za-z0-9_]+", text)]
    return any(sha(f"{a} {b}") in lists["machine_bigrams"] for a, b in zip(plain, plain[1:]))


def walk(value, key, path, problems, rows_file):
    if isinstance(value, dict):
        for k, v in value.items():
            if IDENTITY_FIELD.match(k):
                problems.add("account, plan or identity field")
            walk(v, k, path, problems, rows_file)
    elif isinstance(value, list):
        for v in value:
            walk(v, key, path, problems, rows_file)
    elif natural(value) and (rows_file or key not in DOC_KEYS):
        problems.add("natural-language text in a data field")


def synthetic_ids(path, text):
    """Whether every row of a synthetic example file has an id under synthetic/."""
    import csv
    import io

    try:
        if path.endswith(".tsv"):
            ids = [row[0] for row in list(csv.reader(io.StringIO(text), delimiter="\t"))[1:] if row]
        else:
            ids = [json.loads(line)["id"] for line in text.splitlines() if line.strip()]
    except (ValueError, KeyError, TypeError, csv.Error):
        return False
    return all(isinstance(i, str) and i.startswith("synthetic/") for i in ids)


def inspect(path, data, lists=None):
    lists = lists or deny_lists()
    problems = set()
    synthetic = bool(SYNTHETIC.match(path))
    if PRIVATE_FILES.search(path) and not synthetic:
        return {"private or input file"}
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return set() if path.endswith(BINARY_OK) else {"unexpected binary file"}
    for name, pattern in PATTERNS.items():
        for match in pattern.finditer(text):
            if name == "email" and NOREPLY.fullmatch(match.group(0)):
                continue
            problems.add(name)
            break
    if denied_words(text, lists):
        problems.add("internal name")
    if machine_state(text, lists):
        problems.add("machine state")
    if synthetic:
        if not synthetic_ids(path, text):
            problems.add("synthetic example with an id outside synthetic/")
        return problems
    try:
        if path.endswith(".jsonl"):
            values = [json.loads(line) for line in text.splitlines() if line.strip()]
            for value in values:
                walk(value, "", path, problems, rows_file=True)
        elif path.endswith(".json"):
            rows = "/items/" in path or re.search(r"/judge/(?:pairwise|errors)/", path)
            walk(json.loads(text), "", path, problems, rows_file=bool(rows))
    except ValueError:
        problems.add("invalid JSON")
    return problems


def check(root, history=False, extra=None):
    """Sorted (name, issue) findings; `extra` adds digests to the hashed lists (see deny_lists)."""
    lists = deny_lists(extra)
    findings = set(identity_problems(root))
    found = blobs(root, history)
    # The machine-state rule came after the first commits, whose history is squashed before publication;
    # it applies to everything the tree publishes now (index, HEAD, working copy), not to older blobs.
    current = set(blobs(root, False)) if history else set(found)
    for key, data in found.items():
        for issue in inspect(key[0], data, lists):
            if issue == "machine state" and key not in current:
                continue
            findings.add((key[0], issue))
    return sorted(findings)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", nargs="?", type=Path, default=ROOT)
    parser.add_argument("--history", action="store_true", help="also scan every blob reachable from any ref")
    parser.add_argument("--deny", type=Path, help="JSON object of additional digests per list name (see LISTS)")
    args = parser.parse_args(argv)
    extra = json.loads(args.deny.read_text(encoding="utf-8")) if args.deny else None
    findings = check(args.root.resolve(), args.history, extra)
    for name, issue in findings:
        print(f"{name}: {issue}")
    print(f"Public-tree check: {len(findings)} findings.")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
