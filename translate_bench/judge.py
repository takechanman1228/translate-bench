"""`translate-bench judge`: the judge protocol of Translate Bench v1, on your own predictions.

An optional step for users who have a language model to judge with. It uses the protocol's fixed
sample, its instructions word for word and its aggregation; the judge is reached through an
OpenAI-compatible endpoint, as in `translate-bench run`.

Sample. datasets/judge-sample.json lists 288 items: within each direction and text type, the
release's item IDs sorted by the SHA-256 of "translate-bench/v1/judge-sample/" followed by the ID,
the first 8. The rule uses only the IDs, so it does not depend on any system or output; the tests
recompute it from datasets/items.jsonl.

Error annotation (default). The judge sees a source and one candidate translation, never another
translation of the same source, and counts critical, major and minor errors, ignoring style. One
request holds the items of one direction and text type (at most 8), ordered by the SHA-256 of
"translate-bench/v1/judge-errors/order/", the item ID and the output's SHA-256.

Pairwise (--against-predictions FILE). For each sampled item of your system's directions: if the
two outputs are equal after removing surrounding whitespace, the item is a tie without a judge
("identical"); otherwise the judge sees the source and both outputs as A and B, without the
reference or the names, and returns a winner and the major errors of each. Which output is A
follows the SHA-256 of "translate-bench/v1/judge-pairwise/shown-first/", your system's name, "/"
and the item ID (even first 32 bits: yours); the order of the items follows ".../order/". The
release compared every system with DeepL API, whose output text is not published, so pairwise needs
both prediction files.

An answer is accepted only if it has every requested key and nothing else, with valid values; a
request is sent at most twice per run. Each accepted answer is one line of the journal in --out,
bound by SHA-256 to the prompt, the judge model, the endpoint and the extra request fields; running
again sends only the requests without an answer and refuses a journal made otherwise, so answers from
two endpoints that serve the same model name never mix. The journal and the summary name the
endpoint as `translate-bench run` does ("local endpoint", "private endpoint", or the scheme and host
of a public API; `--record-endpoint` keeps the host and port). The API key is read from the
environment variable --api-key-env names and is never written; error bodies are never read.

Aggregation as in the release: each direction counts equally and its sentences and passages 50:50;
intervals are 95% percentiles of 2,000 paired document-bootstrap draws over the sampled source
documents, within strata of documents that cover the same cells of the release's inputs.

The release's judge ran through subscription command-line clients. A judge reached another way,
or another judge model, is not the release's judge: judge results are comparable only with results
from the same judge model reached the same way.
"""

import hashlib
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from translate_bench import __version__, schema, stats
from translate_bench.endpoint import Endpoint, Failure, Journal, locked, now, run_all
from translate_bench.run import merge

PROTOCOL = "judge-v1"
SCHEMA = "translate-bench/judge@1"
SAMPLE_SALT = "translate-bench/v1/judge-sample/"
PER_CELL = 8
ATTEMPTS = 2  # per request and run
DRAWS = 2000
LEVELS = ("critical", "major", "minor")
VERDICT = {"winner", "major_A", "major_B"}

# The protocol's instructions, word for word (tests pin their SHA-256). --------------------------------------------

PAIRWISE = (
    "You are an expert bilingual reviewer of {source} to {target} translation. For each item you get the source text "
    "and two candidate translations, A and B, from anonymous systems. "
    "Decide which candidate is the better translation for a careful reader of the target language. Weigh accuracy "
    "first (mistranslation, omission, addition, wrong names or numbers), then fluency, naturalness and register. "
    "A more literal rendering is not better by itself, and a freer rendering is not better by itself; judge what a "
    "professional reviser would prefer. Answer \"tie\" only when neither is preferable. "
    "Do not use tools, files or web search. Return only one JSON object mapping every key to an object "
    "{{\"winner\": \"A\" | \"B\" | \"tie\", \"major_A\": <count of major accuracy errors in A>, "
    "\"major_B\": <count in B>}}.\n\n"
)
ERROR_DEFINITIONS = (
    "Count only errors: mistranslation, omission, addition, wrong or garbled names, numbers or terms, untranslated "
    "text, wrong-script characters, and ungrammatical or unintelligible target text. "
    "Do not count style: a literal rendering and a free rendering are both correct if they carry the meaning in "
    "acceptable target language, and awkward-but-correct wording is not an error. "
)
SEVERITY = (
    "Severity: critical = changes the meaning in a way a reader would be misled about a key fact; major = a clear "
    "meaning or name/number error; minor = a small inaccuracy or a clear grammar/spelling slip. "
)
ERRORS = (
    "You are an expert bilingual reviewer annotating {source} to {target} translations in the MQM style. For each "
    "item you get the source text and one candidate translation from an anonymous system. "
    "Count translation errors in the candidate against the source. "
    + ERROR_DEFINITIONS
    + "Annotate each item on its own. "
    + SEVERITY
    + "Do not use tools, files or web search. Return only one JSON object mapping every key to "
    "{{\"critical\": n, \"major\": n, \"minor\": n}}.\n\n"
)


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def seeded(purpose, *parts):
    """A fixed order key: SHA-256 of 'translate-bench/v1/<purpose>/' followed by the parts joined by '/'."""
    return digest(f"translate-bench/v1/{purpose}/" + "/".join(parts))


def output_key(text):
    """Two outputs are the same translation when they are equal after strip()."""
    return digest(text.strip())


def instruction(template, direction, payload):
    src, tgt = schema.parse_direction(direction)
    names = dict(source=schema.LANGUAGE_NAMES[src], target=schema.LANGUAGE_NAMES[tgt])
    return template.format(**names) + json.dumps(payload, ensure_ascii=False, indent=2)


# Sample ----------------------------------------------------------------------------------------------------------

def draw_sample(manifest):
    """The first 8 item IDs of each (direction, type) by SHA-256 of the salt and the ID, in frame order."""
    cells = defaultdict(list)
    for item in manifest:
        cells[item["direction"], item["type"]].append(item)
    chosen = []
    for d in schema.DIRECTIONS:
        for kind in schema.TYPES:
            ranked = sorted(cells[d, kind], key=lambda i: digest(SAMPLE_SALT + i["id"]))[:PER_CELL]
            chosen += [{k: i[k] for k in ("id", "direction", "type", "subset", "doc")} for i in ranked]
    return chosen


def load_sample(root):
    stored = schema.read_json(root / "datasets" / "judge-sample.json")
    if stored["items"] != draw_sample(schema.read_jsonl(root / "datasets" / "items.jsonl")):
        raise ValueError("datasets/judge-sample.json differs from its rule")
    return stored["items"]


# Requests --------------------------------------------------------------------------------------------------------

class Request:
    def __init__(self, name, direction, kind, items):
        self.name, self.direction, self.type = name, direction, kind
        self.items = [dict(it, key=f"Q{n:02d}") for n, it in enumerate(items, 1)]
        self.prompt, self.bound = "", []


def plan_errors(sample, system, sources, outputs):
    """(settled rows, requests): missing items, and one request per direction and type."""
    settled, cells = [], defaultdict(list)
    for it in sample:
        if it["direction"] not in system["directions"]:
            continue
        text = outputs.get(it["id"])
        if text is None:
            settled.append(dict(it, status="missing", reason=system["missing"].get(it["id"], "not run")))
            continue
        cells[it["direction"], it["type"]].append(dict(it, output=output_key(text), text=text.strip()))
    requests = []
    for (direction, kind), items in sorted(cells.items(), key=lambda x: frame_key(*x[0])):
        items.sort(key=lambda u: seeded("judge-errors/order", u["id"], u["output"]))
        request = Request(f"{direction} {kind} 01", direction, kind, items)
        request.prompt = instruction(ERRORS, direction, {it["key"]: dict(source=sources[it["id"]], candidate=it["text"])
                                                         for it in request.items})
        request.bound = [[it["key"], it["id"], it["output"]] for it in request.items]
        requests.append(request)
    return settled, requests


def system_first(system, item_id):
    """Whether the system's output is shown as A."""
    return int(seeded("judge-pairwise/shown-first", system, item_id)[:8], 16) % 2 == 0


def plan_pairwise(sample, system, other, sources, ours, theirs):
    settled, cells = [], defaultdict(list)
    for it in sample:
        if it["direction"] not in system["directions"]:
            continue
        mine, yours = ours.get(it["id"]), theirs.get(it["id"])
        if mine is None:
            settled.append(dict(it, status="missing", reason=system["missing"].get(it["id"], "not run")))
        elif yours is None:
            settled.append(dict(it, status="missing",
                                reason=f"{other['id']} " + other["missing"].get(it["id"], "not run")))
        elif mine.strip() == yours.strip():
            settled.append(dict(it, status="identical", winner="tie"))
        else:
            cells[it["direction"], it["type"]].append(dict(
                it, system_first=system_first(system["id"], it["id"]), system_output=output_key(mine),
                against_output=output_key(yours), texts=(mine.strip(), yours.strip())))
    requests = []
    for (direction, kind), items in sorted(cells.items(), key=lambda x: frame_key(*x[0])):
        items.sort(key=lambda x: seeded("judge-pairwise/order", system["id"], x["id"]))
        request = Request(f"{system['id']} {direction} {kind}", direction, kind, items)
        payload = {}
        for it in request.items:
            a, b = it["texts"] if it["system_first"] else it["texts"][::-1]
            payload[it["key"]] = dict(source=sources[it["id"]], A=a, B=b)
        request.prompt = instruction(PAIRWISE, direction, payload)
        request.bound = [[it["key"], it["id"], it["system_first"], it["system_output"], it["against_output"]]
                         for it in request.items]
        requests.append(request)
    return settled, requests


def frame_key(direction, kind):
    return schema.DIRECTIONS.index(direction), schema.TYPES.index(kind)


def counts_ok(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def exact_object(answer, keys):
    if not isinstance(answer, dict):
        raise ValueError("the answer is not a JSON object")
    if set(answer) != set(keys):
        raise ValueError(f"answer keys differ: {len(set(keys) - set(answer))} missing, "
                         f"{len(set(answer) - set(keys))} not requested")


def parse_errors(request, answer):
    exact_object(answer, [it["key"] for it in request.items])
    rows = []
    for it in request.items:
        counts = answer[it["key"]]
        if not isinstance(counts, dict) or set(counts) != set(LEVELS):
            raise ValueError(f"{it['key']}: fields differ")
        if not all(counts_ok(counts[level]) for level in LEVELS):
            raise ValueError(f"{it['key']}: invalid count")
        rows.append(dict(key=it["key"], id=it["id"], direction=it["direction"], type=it["type"], output=it["output"],
                         **{level: counts[level] for level in LEVELS}))
    return rows


def parse_pairwise(request, answer):
    exact_object(answer, [it["key"] for it in request.items])
    rows = []
    for it in request.items:
        verdict = answer[it["key"]]
        if not isinstance(verdict, dict) or set(verdict) != VERDICT:
            raise ValueError(f"{it['key']}: fields differ")
        if verdict["winner"] not in ("A", "B", "tie") or not all(counts_ok(verdict[k]) for k in ("major_A", "major_B")):
            raise ValueError(f"{it['key']}: invalid value")
        side = {"A": "system" if it["system_first"] else "against", "B": "against" if it["system_first"] else "system"}
        majors = {side["A"]: verdict["major_A"], side["B"]: verdict["major_B"]}
        rows.append(dict(key=it["key"], id=it["id"], direction=it["direction"], type=it["type"],
                         winner=side.get(verdict["winner"], "tie"),
                         shown_first="system" if it["system_first"] else "against",
                         major_system=majors["system"], major_against=majors["against"],
                         system_output=it["system_output"], against_output=it["against_output"]))
    return rows


def first_object(text):
    """The outermost {...} span of the reply, parsed as JSON (as the release read its judges' replies)."""
    match = re.search(r"\{.*\}", text or "", re.S)
    if match is None:
        raise ValueError("no JSON object in the reply")
    return json.loads(match.group(0))


def binding(request, judge):
    return digest(json.dumps([digest(request.prompt), judge["model"], judge["via"], judge["extra_body"],
                              judge["endpoint"], request.bound], ensure_ascii=False, sort_keys=True))


def answered(requests, records, judge):
    """Names of the planned requests the journal answers for exactly the request as planned now."""
    planned = {r.name: r for r in requests}
    done, problems = set(), []
    for record in records:
        request = planned.get(record.get("request"))
        if request is None:
            problems.append(f"{record.get('request')}: not a request of the current plan")
        elif record.get("binding") != binding(request, judge):
            problems.append(f"{request.name}: answered for another prompt, output, judge, endpoint or request "
                            "fields")
        elif [(x["key"], x["id"]) for x in record.get("items", [])] != [(x["key"], x["id"]) for x in request.items]:
            problems.append(f"{request.name}: the saved answer does not cover the request's items")
        elif request.name in done:
            problems.append(f"{request.name}: answered twice")
        else:
            done.add(request.name)
    if problems:
        raise ValueError("The journal does not match the requests as planned now; nothing was sent: "
                         + "; ".join(problems[:4]) + " (use a new --out for another judge or other predictions)")
    return done


# Aggregation -----------------------------------------------------------------------------------------------------

def weights(cells):
    """Equal directions, equal types within a direction, equal items within a cell; they sum to 1."""
    count = Counter(cells)
    types = defaultdict(set)
    for direction, kind in count:
        types[direction].add(kind)
    return np.array([1 / (len(types) * len(types[d]) * count[d, t]) for d, t in cells])


class Documents:
    """Paired document-bootstrap draws over the sampled source documents, shared by every system and stage.

    Documents are drawn within strata of documents that cover the same cells of the release's full input
    set. Cell labels use the arrow form of the directions ("sentence/en→ja") so the strata come in the
    protocol's order."""

    def __init__(self, sample, manifest, draws=DRAWS, seed="translate-bench/v1/judge-bootstrap"):
        cells = defaultdict(set)
        for it in manifest:
            src, tgt = schema.parse_direction(it["direction"])
            cells[it["doc"]].add(f"{it['type']}/{src}→{tgt}")
        coverage = {it["doc"]: dict.fromkeys(sorted(cells[it["doc"]]), True) for it in sample}
        self.count = {}
        for docs, picks in stats.document_draws(coverage, seed, draws):
            for j, doc in enumerate(docs):
                self.count[doc] = (picks == j).sum(axis=1)

    def interval(self, values, cells, docs):
        values = np.asarray(values, dtype=float)
        counts = np.stack([self.count[d] for d in docs], axis=1).astype(float)
        members = defaultdict(list)
        for i, cell in enumerate(cells):
            members[cell].append(i)
        by_direction = defaultdict(list)
        with np.errstate(invalid="ignore", divide="ignore"):
            for (direction, _), idx in members.items():
                m = counts[:, idx]
                by_direction[direction].append((m * values[idx]).sum(axis=1) / m.sum(axis=1))
            draws = np.mean([np.mean(v, axis=0) for v in by_direction.values()], axis=0)
        valid = np.isfinite(draws)
        return [float(np.quantile(draws[valid], q)) for q in (0.025, 0.975)], int(valid.sum())


def scopes(rows):
    """'all': rows in the directions with both text types; 'sentence' / 'passage': every row of that type."""
    present = defaultdict(set)
    for r in rows:
        present[r["direction"]].add(r["type"])
    full = {d for d, kinds in present.items() if len(kinds) == len(schema.TYPES)}
    out = {}
    if full:
        out["all"] = [r for r in rows if r["direction"] in full]
    for kind in schema.TYPES:
        if any(r["type"] == kind for r in rows):
            out[kind] = [r for r in rows if r["type"] == kind]
    return out


def describe(rows, metrics, documents):
    cells = [(r["direction"], r["type"]) for r in rows]
    docs = [r["doc"] for r in rows]
    entry = dict(n=len(rows), directions=len({d for d, _ in cells}))
    for name, values in metrics.items():
        entry[name] = round(float(np.dot(weights(cells), np.asarray(values, dtype=float))), 4)
        (lo, hi), entry["draws"] = documents.interval(values, cells, docs)
        entry[name + "_95"] = [round(lo, 4), round(hi, 4)]
    return entry


def error_stats(rows, documents):
    out = {}
    for scope, x in scopes(rows).items():
        c, M, m = (np.array([r[level] for r in x], dtype=float) for level in LEVELS)
        metrics = dict(error_free=((c + M + m) == 0).astype(float), critical_major=c + M, minor=m,
                       penalty=25 * c + 5 * M + m)
        out[scope] = describe(x, metrics, documents)
    return out


def pairwise_stats(rows, documents):
    out = {}
    for scope, x in scopes(rows).items():
        v = np.array([{"system": 1, "against": -1, "tie": 0}[r["winner"]] for r in x])
        entry = describe(x, {"net": v}, documents)
        w = weights([(r["direction"], r["type"]) for r in x])
        decided = w[v != 0].sum()
        entry.update(wins=int((v == 1).sum()), losses=int((v == -1).sum()),
                     ties=int(sum(r["winner"] == "tie" and r["status"] == "judged" for r in x)),
                     identical=int(sum(r["status"] == "identical" for r in x)),
                     preferred=round(float(w[v == 1].sum() / decided), 4) if decided else None)
        out[scope] = entry
    return out


# Command ---------------------------------------------------------------------------------------------------------

def add_arguments(p):
    p.add_argument("--predictions", type=Path, required=True, help="your predictions (JSONL with id and translation)")
    p.add_argument("--system-name", help="a name for your system (default: the file name); it orders A and B")
    p.add_argument("--against-predictions", type=Path, metavar="FILE",
                   help="judge pairwise against these predictions instead of annotating errors")
    p.add_argument("--against-name", help="a name for the other system (default: its file name)")
    p.add_argument("--judge-model", required=True, help="the judge model's name at the endpoint")
    p.add_argument("--base-url", required=True, help="OpenAI-compatible base URL of the judge, e.g. "
                                                     "https://api.example.com/v1 or http://127.0.0.1:8080/v1")
    p.add_argument("--api-key-env", metavar="VAR", help="environment variable holding the API key (never written)")
    p.add_argument("--record-endpoint", action="store_true",
                   help="record the judge endpoint's host and port even when it is a local or private address")
    p.add_argument("--extra-body", metavar="JSON", help='extra request fields, e.g. \'{"temperature": 0}\'')
    p.add_argument("--inputs", type=Path, help="prepared inputs (default: private/inputs in the checkout)")
    p.add_argument("--out", type=Path, required=True,
                   help="directory for the journal and the summary; outside the checkout or Git-ignored")
    p.add_argument("--timeout", type=float, default=600, help="seconds to wait for one reply (default 600)")
    p.add_argument("--retries", type=int, default=3, help="retries of a transient error (default 3)")
    p.add_argument("--concurrency", type=int, default=2, help="requests in flight at once (default 2)")
    p.add_argument("--limit", type=int, metavar="N", help="send at most N requests")
    p.add_argument("--dry-run", action="store_true", help="print the plan and stop")


def read_outputs(path, items):
    """{id: text} of the ok translations, the directions submitted and the reason of each failed item."""
    from translate_bench.score import read_predictions

    predictions = read_predictions(path, items)
    outputs = {sid: t for sid, (status, t) in predictions.items() if status == "ok" and t and t.strip()}
    missing = {sid: ("empty" if status == "ok" else status) for sid, (status, _) in predictions.items()
               if sid not in outputs}
    directions = {f"{items[sid]['src']}-{items[sid]['tgt']}" for sid in predictions}
    return outputs, directions, missing


def name_of(value, path):
    from translate_bench.score import system_id

    return system_id(value or Path(path).stem)


def main(root, options, log=None):
    log = log or print
    from translate_bench.score import read_inputs

    out = schema.safe_location(options.out, root, "--out")
    sample = load_sample(root)
    manifest = schema.read_jsonl(root / "datasets" / "items.jsonl")
    items, _ = read_inputs(Path(options.inputs) if options.inputs else root / "private" / "inputs")
    ours, directions, missing = read_outputs(options.predictions, items)
    system = dict(id=name_of(options.system_name, options.predictions), directions=directions, missing=missing)
    by_id = {i["id"]: i for i in manifest}
    needed = [it["id"] for it in sample if it["direction"] in directions]
    unverified = [i for i in needed if i not in items or digest(items[i]["source"]) != by_id[i]["source_sha256"]]
    if not needed or unverified:
        raise ValueError(f"{len(unverified)} of {len(needed)} sampled items of the predicted directions are missing "
                         "from --inputs or have other source texts" + (f" (e.g. {unverified[0]})" if unverified else "")
                         + "; the judge sample needs the release inputs (`translate-bench prepare`)")
    sources = {i: items[i]["source"] for i in needed}
    extra = json.loads(options.extra_body) if options.extra_body else {}
    if not isinstance(extra, dict):
        raise ValueError("--extra-body must be a JSON object")
    endpoint = Endpoint(options.base_url, "chat", options.api_key_env, options.timeout, options.retries,
                        getattr(options, "backoff", 1.0), getattr(options, "record_endpoint", False))
    judge = dict(model=options.judge_model, via="openai-compatible", extra_body=extra, endpoint=endpoint.identity)
    if options.against_predictions:
        stage = "pairwise"
        theirs, their_directions, their_missing = read_outputs(options.against_predictions, items)
        other = dict(id=name_of(options.against_name, options.against_predictions), directions=their_directions,
                     missing=their_missing)
        if other["id"] == system["id"]:
            raise ValueError("--system-name and --against-name must differ")
        settled, requests = plan_pairwise(sample, system, other, sources, ours, theirs)
        parse = parse_pairwise
    else:
        stage, other = "errors", None
        settled, requests = plan_errors(sample, system, sources, ours)
        parse = parse_errors
    journal = Journal(out / f"{stage}.jsonl")
    summary_path = out / f"{stage}.json"
    status = Counter(r["status"] for r in settled)
    log(f"Judge sample: {len(settled) + sum(len(r.items) for r in requests)} items in {len(system['directions'])} "
        f"directions of {system['id']}" + (f" against {other['id']}" if other else "")
        + f"; missing {status['missing']}" + (f", identical {status['identical']}" if other else "")
        + f"; {sum(len(r.items) for r in requests)} to judge in {len(requests)} requests")
    if options.dry_run:
        done = answered(requests, journal.read() if journal.path.exists() else [], judge)
        log(f"Dry run: {len(done)} requests answered, {len(requests) - len(done)} to send; nothing was sent.")
        return 0
    with locked(out, f"{stage}.lock"):
        done = answered(requests, journal.read(), judge)
        left = [r for r in requests if r.name not in done]
        left = left[:options.limit] if options.limit is not None else left
        log(f"This run: {len(left)} requests to {options.judge_model} via {endpoint.public} (recorded as "
            f"{endpoint.recorded})")
        failed = []

        def work(request):
            body = merge(dict(model=options.judge_model, messages=[dict(role="user", content=request.prompt)]), extra)
            error = None
            for attempt in range(1, ATTEMPTS + 1):
                started = time.monotonic()
                try:
                    reply, _, _ = endpoint.post(body)
                    text = reply["choices"][0]["message"]["content"]
                    return dict(rows=parse(request, first_object(text)), attempt=attempt,
                                seconds=round(time.monotonic() - started, 1))
                except Failure as exc:
                    error = f"{exc.status}: {exc}"
                except (ValueError, KeyError, IndexError, TypeError) as exc:
                    error = endpoint.mask(f"invalid answer: {exc}")
            return dict(error=error)

        def commit(request, result):
            if "error" in result:
                failed.append(request.name)
                log(f"FAIL {request.name}: {result['error']}")
                return
            journal.append(dict(request=request.name, binding=binding(request, judge),
                                prompt_sha256=digest(request.prompt), judge=judge["model"], via=judge["via"],
                                endpoint=endpoint.recorded, attempt=result["attempt"], seconds=result["seconds"],
                                at=now(), items=result["rows"]))
            log(f"ok {request.name}: {len(result['rows'])} items in {result['seconds']:.0f} s")

        result = run_all(left, work, commit, options.concurrency, log) if left else dict(stop=None, interrupted=False)
        records = journal.read()
    done = answered(requests, records, judge)
    rows = list(settled)
    verdicts = {row["id"]: row for r in records if r["request"] in done for row in r["items"]}
    waiting = 0
    for request in requests:
        for it in request.items:
            v = verdicts.get(it["id"])
            if v is None:
                waiting += 1
                continue
            base = {k: it[k] for k in ("id", "direction", "type", "subset", "doc")}
            if stage == "errors":
                rows.append(dict(base, status="annotated", **{level: v[level] for level in LEVELS}))
            else:
                rows.append(dict(base, status="judged", winner=v["winner"], shown_first=v["shown_first"],
                                 major_system=v["major_system"], major_against=v["major_against"]))
    documents = Documents(sample, manifest)
    scored = [r for r in rows if r["status"] != "missing"]
    results = (error_stats if stage == "errors" else pairwise_stats)(scored, documents) if scored else {}
    summary = dict(schema=SCHEMA, protocol=PROTOCOL, stage=stage, tool=f"translate-bench {__version__}",
                   system=system["id"], against=other["id"] if other else None,
                   judge=dict(model=judge["model"], via=judge["via"], endpoint=endpoint.recorded, extra_body=extra),
                   items=dict(sample=len(rows) + waiting, missing=sum(r["status"] == "missing" for r in rows),
                              identical=sum(r["status"] == "identical" for r in rows), waiting=waiting),
                   requests=dict(total=len(requests), answered=len(done)), complete=waiting == 0, results=results,
                   note=("Not the release's judge unless the same judge model was reached the same way; judge "
                         "results are comparable only with results from the same judge model."))
    schema.write_json(summary_path, summary)
    print_summary(summary, log)
    if result.get("stop") or result.get("interrupted") or failed or waiting:
        log(f"{waiting} items still without an answer; run the same command again to continue.")
        return 3 if result.get("stop") or failed else 130 if result.get("interrupted") else 0
    return 0


def print_summary(summary, log):
    head = f"{summary['system']}" + (f" against {summary['against']}" if summary["against"] else "")
    log(f"{head}, judge {summary['judge']['model']} ({summary['stage']}); "
        + ("complete." if summary["complete"] else f"{summary['items']['waiting']} items waiting."))
    value = lambda x, spec: "–" if x is None else format(x, spec)  # noqa: E731
    span = lambda ci, spec: "" if not ci or None in ci else f" [{format(ci[0], spec)}, {format(ci[1], spec)}]"  # noqa: E731
    for scope, e in summary["results"].items():
        if summary["stage"] == "errors":
            log(f"  {scope:8} n={e['n']:3} directions={e['directions']:2}  error-free "
                f"{value(e.get('error_free'), '.2f')}{span(e.get('error_free_95'), '.2f')}  critical+major/item "
                f"{value(e.get('critical_major'), '.2f')}  minor/item {value(e.get('minor'), '.2f')}  penalty/item "
                f"{value(e.get('penalty'), '.2f')}")
        else:
            preferred = "–" if e["preferred"] is None else f"{e['preferred']:.0%}"
            log(f"  {scope:8} n={e['n']:3} directions={e['directions']:2}  wins {e['wins']} losses {e['losses']} "
                f"ties {e['ties']} identical {e['identical']}  preferred {preferred} of decided items  "
                f"net {value(e.get('net'), '+.3f')}{span(e.get('net_95'), '+.3f')}")
    log(summary["note"])


if __name__ == "__main__":
    sys.exit("Run `translate-bench judge`.")
