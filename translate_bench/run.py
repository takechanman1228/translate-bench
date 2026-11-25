"""`translate-bench run`: translate the prepared inputs through an OpenAI-compatible endpoint.

Works with any server that speaks the OpenAI chat-completions API: llama.cpp's llama-server,
Ollama, LM Studio, vLLM and hosted APIs. One item per request, as the release ran every local
system. The default prompt is the release's generic instruction (`generic-instruction` in
configs/systems.json), which the release used for general chat models; the other release
profiles that run over HTTP can be chosen by name, or a prompt can be read from a file.
`--settings-from SYSTEM_ID` takes the prompt profile, decoding settings and deadline of a
system the release ran on llama-server, to reproduce it.

Output, in --out:

- predictions.jsonl: one line per finished item, in the format `translate-bench score` reads
  (id, status, translation), with the seconds, attempts and finish reason of the request. It is
  also the run's journal: running the same command again sends only the items not in it. Every
  line carries `settings_sha256`, the SHA-256 of the settings and the endpoint it was made with, and
  a run with other settings or another endpoint refuses to add to it.
- run.json: what is needed to reproduce the run (model, the endpoint as "local endpoint", "private
  endpoint" or the scheme and host of a public API, prompt and its SHA-256, decoding settings, tool
  version), the counts and the wall time. It is written before the first request and again at the
  end of every session. `--record-endpoint` records the host and port even when they are private.

The API key is read from the environment variable --api-key-env names and is never written.

Status of an item: ok; empty (the reply had no text); timeout; error (an HTTP error, a reply
without text choices, or a finish other than "stop", for example the --max-tokens limit). As in
the release, failed items stay failures and count in the coverage denominator.

predictions.jsonl holds model outputs, so --out must be outside the checkout or in a directory
Git ignores.
"""

import hashlib
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path
from statistics import median

from translate_bench import __version__, schema
from translate_bench.endpoint import Endpoint, Failure, Journal, locked, now, run_all

SCHEMA = "translate-bench/run@1"
DEFAULT_PROFILE = "generic-instruction"
# Release profiles that run over HTTP. Not available: seed-x (token IDs from the base model's tokenizer),
# qwen-mt-lumen (MLX, with its own language names), the Apple frameworks, the batched cloud prompt and DeepL API.
PROFILES = ("generic-instruction", "hy-mt", "index-translate", "plamo", "translategemma")
STATUSES = ("ok", "empty", "timeout", "error")
DEFAULTS = dict(temperature=0, max_tokens=512, seed=42)
# Decoding settings of the registry's llama-server systems, sent as request fields.
REQUEST_FIELDS = ("temperature", "top_p", "top_k", "min_p", "repeat_penalty", "presence_penalty", "seed",
                  "max_tokens", "cache_prompt")
TIMEOUT = 120
PLACEHOLDER = re.compile(r"\{(\w+)\}")
NAMES = ("source", "target", "source_code", "target_code", "source_zh", "target_zh", "text", "text_stripped")
TYPE_NAMES = {"sentence": "sentence", "sentences": "sentence", "passage": "passage", "passages": "passage"}


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# Prompts ---------------------------------------------------------------------------------------------------------

def load_prompt(registry, profile=None, prompt_file=None):
    """The prompt as a dict: name, kind (chat or completions), spec (the registry entry) and sha256."""
    profiles = registry["prompt_profiles"]
    chinese = profiles["index-translate"]["language_names_zh"]
    if prompt_file:
        text = Path(prompt_file).read_text(encoding="utf-8")
        unknown = sorted(set(PLACEHOLDER.findall(text)) - set(NAMES))
        if unknown:
            raise ValueError(f"--prompt-file: unknown placeholder {{{unknown[0]}}}; use "
                             + ", ".join(f"{{{n}}}" for n in NAMES))
        if "{text}" not in text and "{text_stripped}" not in text:
            raise ValueError("--prompt-file: the prompt must contain {text}, where the source text goes")
        return dict(name="file", kind="chat", spec=dict(message=text), sha256=sha(text), chinese=chinese)
    name = profile or DEFAULT_PROFILE
    if name not in PROFILES:
        known = ", ".join(PROFILES)
        reason = " (not an HTTP chat or completion prompt)" if name in profiles else ""
        raise ValueError(f"--prompt-profile {name}: not available for run{reason}; choose one of {known}")
    spec = profiles[name]
    kind = "completions" if spec.get("endpoint") == "/v1/completions" else "chat"
    digest = sha(json.dumps({name: spec}, ensure_ascii=False, sort_keys=True))
    return dict(name=name, kind=kind, spec=spec, sha256=digest, chinese=chinese)


def fill(template, values):
    return PLACEHOLDER.sub(lambda m: values[m.group(1)] if m.group(1) in values else m.group(0), template)


def render(prompt, src, tgt, text):
    """(content, request fields) of one item: the user message or raw prompt, and stop or template arguments."""
    names = dict(schema.LANGUAGE_NAMES)
    if prompt["name"] == "translategemma":
        names["zh-Hans"] = "Chinese"  # the registry: "Chinese is named 'Chinese' with code zh-Hans"
    values = dict(source=names[src], target=names[tgt], source_code=src, target_code=tgt,
                  source_zh=prompt["chinese"].get(src, ""), target_zh=prompt["chinese"].get(tgt, ""), text=text,
                  text_stripped=text.strip())
    spec = prompt["spec"]
    if "message_chinese" in spec and "zh-Hans" in (src, tgt):
        template = spec["message_chinese"]
    else:
        template = spec["message"] if prompt["kind"] == "chat" else spec["prompt"]
    fields = {}
    if spec.get("stop"):
        fields["stop"] = list(spec["stop"])
    if spec.get("template_arguments"):
        # The registry: the template "receives the lower-case source and target language codes".
        lower = dict(values, source_code=src.lower(), target_code=tgt.lower())
        fields["chat_template_kwargs"] = {k: fill(v, lower) for k, v in spec["template_arguments"].items()}
    return fill(template, values), fields


def prompt_record(prompt):
    record = dict(profile=prompt["name"], kind=prompt["kind"], sha256=prompt["sha256"])
    for key in ("message", "message_chinese", "prompt", "stop", "template_arguments"):
        if key in prompt["spec"]:
            record[key] = prompt["spec"][key]
    return record


# Settings --------------------------------------------------------------------------------------------------------

def optional(value, cast, flag):
    """None when not given, "none" to send no such field, else the value."""
    if value is None or str(value).lower() == "none":
        return value and "none"
    try:
        return cast(value)
    except ValueError:
        raise ValueError(f"{flag} takes a {cast.__name__} or none") from None


def resolve_settings(registry, options):
    """(prompt, generation, timeout, release system or None) from the options and --settings-from."""
    fields, template, profile, timeout, source = dict(DEFAULTS), {}, None, TIMEOUT, None
    if options.settings_from:
        source = next((s for s in registry["systems"] if s["id"] == options.settings_from), None)
        if source is None:
            raise ValueError(f"--settings-from {options.settings_from}: not a system of configs/systems.json")
        runtime = source.get("runtime") or {}
        if runtime.get("endpoint") != "llama-server" or source.get("prompt_profile") not in PROFILES:
            raise ValueError(f"--settings-from {source['id']}: only systems the release ran on llama-server with "
                             f"one of the profiles {', '.join(PROFILES)}")
        generation = dict(source["generation"])
        if "enable_thinking" in generation:
            template["enable_thinking"] = generation.pop("enable_thinking")
        unknown = sorted(set(generation) - set(REQUEST_FIELDS))
        if unknown:
            raise ValueError(f"--settings-from {source['id']}: generation fields {unknown} have no request field")
        fields, profile = generation, source["prompt_profile"]
        timeout = runtime.get("request_timeout_s") or TIMEOUT
    for name, cast in (("temperature", float), ("max_tokens", int), ("seed", int)):
        value = optional(getattr(options, name), cast, "--" + name.replace("_", "-"))
        if value == "none":
            fields.pop(name, None)  # some hosted APIs reject the field
        elif value is not None:
            fields[name] = value
    extra = {}
    if options.extra_body:
        try:
            extra = json.loads(options.extra_body)
        except ValueError:
            raise ValueError("--extra-body must be a JSON object") from None
        if not isinstance(extra, dict):
            raise ValueError("--extra-body must be a JSON object")
    if options.prompt_profile and profile and options.prompt_profile != profile:
        print(f"Note: the release ran {source['id']} with the {profile} profile; using {options.prompt_profile}.",
              file=sys.stderr)
    prompt = load_prompt(registry, options.prompt_profile or (None if options.prompt_file else profile),
                         options.prompt_file)
    if options.timeout is not None:
        timeout = options.timeout
    generation = dict(fields=fields, chat_template_kwargs=template, extra_body=extra)
    return prompt, generation, timeout, source


def merge(base, extra):
    out = dict(base)
    for key, value in extra.items():
        out[key] = merge(out[key], value) if isinstance(value, dict) and isinstance(out.get(key), dict) else value
    return out


def request_body(model, prompt, content, fields, generation):
    body = dict(model=model)
    if prompt["kind"] == "chat":
        body["messages"] = [dict(role="user", content=content)]
    else:
        body["prompt"] = content
    body.update(generation["fields"])
    kwargs = {**fields.pop("chat_template_kwargs", {}), **generation["chat_template_kwargs"]}
    body.update(fields)
    if kwargs:
        body["chat_template_kwargs"] = kwargs
    return merge(body, generation["extra_body"])


# Items -----------------------------------------------------------------------------------------------------------

def parse_directions(pairs=None, directions=None):
    if pairs:
        from translate_bench.prepare import parse_pairs

        return [d for k in parse_pairs(pairs) for d in (f"en-{k}", f"{k}-en")]
    if directions:
        chosen = [d.strip() for d in directions.split(",") if d.strip()]
        for d in chosen:
            if d not in schema.DIRECTIONS:
                raise ValueError(f"--directions: unknown direction {d!r}; e.g. en-ja, ja-en, zh-Hans-en")
        return chosen
    return list(schema.DIRECTIONS)


def parse_types(value):
    names = [TYPE_NAMES.get(x.strip()) for x in (value or "sentence,passage").split(",") if x.strip()]
    if not names or None in names:
        raise ValueError("--types takes sentence, passage or both, comma-separated")
    return [t for t in schema.TYPES if t in names]


def select(items, directions, types, limit=None):
    """Input items of the chosen directions and types in input order; with `limit`, the first N of each cell."""
    chosen, taken = [], Counter()
    for row in items.values():
        cell = (row["type"], f"{row['src']}-{row['tgt']}")
        if cell[1] not in directions or cell[0] not in types:
            continue
        if limit is not None and taken[cell] >= limit:
            continue
        taken[cell] += 1
        chosen.append(row)
    return chosen


def parse_reply(reply, kind):
    """(text, finish reason) of a reply; raises Failure for a reply without a usable choice."""
    try:
        choice = reply["choices"][0]
    except (KeyError, IndexError, TypeError):
        raise Failure("error", "the reply has no choices") from None
    if not isinstance(choice, dict):
        raise Failure("error", "the reply has no choices")
    if kind == "chat":
        content = (choice.get("message") or {}).get("content")
        if isinstance(content, list):  # content parts
            content = "".join(p.get("text") or "" for p in content if isinstance(p, dict))
    else:
        content = choice.get("text")
    if content is not None and not isinstance(content, str):
        raise Failure("error", "the reply's content is not text")
    finish = choice.get("finish_reason")
    if finish != "stop":
        hint = " (the output reached --max-tokens)" if finish == "length" else ""
        raise Failure("error", f"finish_reason {finish!r}{hint}")
    return (content or "").strip(), finish


def served(name):
    """The model name the server reported, without a local path."""
    if not isinstance(name, str) or not name:
        return None
    if name.startswith(("/", "~", "\\")) or re.match(r"[A-Za-z]:[\\/]", name):
        name = re.split(r"[\\/]", name.rstrip("\\/"))[-1]
    return name[:120]


# Run -------------------------------------------------------------------------------------------------------------

def add_arguments(p):
    p.add_argument("--model", required=True, help="model name sent in each request (the server's name for it)")
    p.add_argument("--base-url", required=True,
                   help="OpenAI-compatible base URL, e.g. http://127.0.0.1:8080/v1 (llama-server), "
                        "http://127.0.0.1:11434/v1 (Ollama), http://127.0.0.1:1234/v1 (LM Studio)")
    p.add_argument("--api-key-env", metavar="VAR",
                   help="environment variable holding the API key, sent as a bearer token (never written)")
    p.add_argument("--record-endpoint", action="store_true",
                   help="record the endpoint's host and port in run.json even when it is a local or private "
                        "address (default: 'local endpoint' or 'private endpoint')")
    p.add_argument("--out", type=Path, required=True,
                   help="run directory for predictions.jsonl and run.json; outside the checkout or Git-ignored")
    p.add_argument("--inputs", type=Path, help="prepared inputs (default: private/inputs in the checkout)")
    which = p.add_mutually_exclusive_group()
    which.add_argument("--pairs", help="comma-separated language pairs, both directions, e.g. en-ja,en-de "
                                       "(default: every direction in the inputs)")
    which.add_argument("--directions", help="comma-separated directions, e.g. en-ja,de-en")
    p.add_argument("--types", default="sentence,passage", help="sentence, passage or both (default: both)")
    p.add_argument("--limit", type=int, metavar="N", help="only the first N items of each direction and type")
    prompt = p.add_mutually_exclusive_group()
    prompt.add_argument("--prompt-profile", metavar="NAME",
                        help=f"a release prompt profile: {', '.join(PROFILES)} (default: {DEFAULT_PROFILE})")
    prompt.add_argument("--prompt-file", type=Path, metavar="FILE",
                        help="a user message template with {source}, {target} and {text} (English language names)")
    p.add_argument("--settings-from", metavar="SYSTEM_ID",
                   help="use the prompt profile, decoding settings and deadline of a release system run on "
                        "llama-server, e.g. gemma-4-e4b-it")
    p.add_argument("--temperature", help=f"sampling temperature, or none to send none (default "
                                         f"{DEFAULTS['temperature']})")
    p.add_argument("--max-tokens", help=f"output token limit, or none to send none (default {DEFAULTS['max_tokens']})")
    p.add_argument("--seed", help=f"sampling seed, or none to send none (default {DEFAULTS['seed']})")
    p.add_argument("--extra-body", metavar="JSON", help='extra request fields, e.g. \'{"top_k": 64}\'')
    p.add_argument("--timeout", type=float, help=f"seconds to wait for one reply (default {TIMEOUT})")
    p.add_argument("--retries", type=int, default=3, help="retries of a transient error, with backoff (default 3)")
    p.add_argument("--concurrency", type=int, default=1, help="requests in flight at once (default 1)")


def check_journal(rows, items, binding):
    by_id, problems = {}, []
    for row in rows:
        item = items.get(row.get("id"))
        if row.get("settings_sha256") != binding:
            problems.append(f"{row.get('id')} was made with other settings or another endpoint")
        elif item is None:
            problems.append(f"{row.get('id')!r} is not an item of --inputs")
        elif row.get("source_sha256") not in (None, sha(item["source"])):
            problems.append(f"{row['id']} has another source text in --inputs")
        elif row["id"] in by_id:
            problems.append(f"{row['id']} appears twice")
        elif row.get("status") not in STATUSES:
            problems.append(f"{row['id']} has an unknown status")
        by_id[row.get("id")] = row
    if problems:
        raise ValueError("predictions.jsonl does not belong to these inputs or settings: " + "; ".join(problems[:3])
                         + " (use a new --out)")
    return by_id


def totals(rows, items, selected):
    done = {r["id"] for r in rows}
    counts = Counter(r["status"] for r in rows)
    out = dict(items=len(rows), **{s: counts.get(s, 0) for s in STATUSES},
               selected_not_run=sum(r["id"] not in done for r in selected))
    seconds = {}
    for kind in schema.TYPES:
        values = [r["elapsed_s"] for r in rows if r["status"] == "ok" and items[r["id"]]["type"] == kind]
        if values:
            seconds[kind] = round(median(values), 3)
    tokens = [r["tokens"] for r in rows if r.get("tokens")]
    usage = dict(items=len(tokens), prompt=sum(t.get("prompt") or 0 for t in tokens),
                 completion=sum(t.get("completion") or 0 for t in tokens)) if tokens else None
    return out, seconds, usage


def write_atomic(path, value):
    """Write JSON through a temporary file, so the file is always either the old or the new version."""
    temporary = path.with_name(path.name + ".tmp")
    schema.write_json(temporary, value)
    os.replace(temporary, path)


def main(root, options, log=None):
    log = log or (lambda m: print(m, file=sys.stderr, flush=True))
    from translate_bench.score import read_inputs, verify_inputs

    out = schema.safe_location(options.out, root, "--out")
    registry = schema.read_json(root / "configs" / "systems.json")
    prompt, generation, timeout, source = resolve_settings(registry, options)
    endpoint = Endpoint(options.base_url, prompt["kind"], options.api_key_env, timeout, options.retries,
                        getattr(options, "backoff", 1.0), getattr(options, "record_endpoint", False))
    items, files = read_inputs(Path(options.inputs) if options.inputs else root / "private" / "inputs")
    manifest = schema.read_jsonl(root / "datasets" / "items.jsonl")
    check = verify_inputs(items, files, manifest, schema.read_json(root / "datasets" / "release.json")["files"])
    directions, types = parse_directions(options.pairs, options.directions), parse_types(options.types)
    selected = select(items, directions, types, options.limit)
    if not selected:
        raise ValueError("No input item in the chosen directions and types; prepare them with "
                         "`translate-bench prepare --pairs ...`")
    settings = dict(model=options.model, endpoint=endpoint.recorded, prompt=prompt_record(prompt),
                    generation=generation, timeout_s=timeout)
    # Bound into every journal line; it covers the endpoint itself, which run.json does not name.
    binding = sha(json.dumps([settings, endpoint.identity], ensure_ascii=False, sort_keys=True))
    journal = Journal(out / "predictions.jsonl")
    record_path = out / "run.json"
    with locked(out, "run.lock"):
        record = schema.read_json(record_path) if record_path.is_file() else None
        if record is not None and record.get("settings") != settings:
            changed = sorted(k for k in settings if record.get("settings", {}).get(k) != settings[k])
            raise ValueError(f"{record_path} was made with other settings ({', '.join(changed)}); use a new --out")
        done = check_journal(journal.read(), items, binding)
        todo = [r for r in selected if r["id"] not in done]
        record = record or dict(schema=SCHEMA, tool=f"translate-bench {__version__}", settings=settings,
                                settings_from=source["id"] if source else None, sessions=[])
        record.update(authenticated=endpoint.authenticated, inputs=check)
        if not check["verified_release_items"]:
            log("Inputs: NOT the verified release inputs; results will not be comparable with the published ones.")
        log(f"{options.model} via {endpoint.public} (recorded as {endpoint.recorded}): {len(todo)} of "
            f"{len(selected)} selected items to send ({len(selected) - len(todo)} already in {journal.path.name}), "
            f"prompt {prompt['name']}, {options.concurrency} at a time")
        chosen = {f"{r['src']}-{r['tgt']}" for r in selected}
        session = dict(started=now(), ended=None, concurrency=options.concurrency,
                       directions=[d for d in schema.DIRECTIONS if d in chosen],
                       types=[t for t in types if any(r["type"] == t for r in selected)], limit=options.limit,
                       sent=0, served_models=[], stop=None, interrupted=False, wall_s=None)
        record["sessions"].append(session)
        write_atomic(record_path, record)  # the settings are on disk before the first request
        counts, started, last = Counter(), time.monotonic(), [time.monotonic()]

        def work(row):
            content, fields = render(prompt, row["src"], row["tgt"], row["source"])
            body = request_body(options.model, prompt, content, fields, generation)
            entry = dict(id=row["id"], status="ok", translation=None, elapsed_s=None, attempts=None,
                         finish_reason=None, error=None, source_sha256=sha(row["source"]), tokens=None,
                         settings_sha256=binding)
            try:
                reply, entry["attempts"], seconds = endpoint.post(body)
                entry["elapsed_s"] = round(seconds, 3)
                text, entry["finish_reason"] = parse_reply(reply, prompt["kind"])
                usage = reply.get("usage") if isinstance(reply.get("usage"), dict) else None
                if usage:
                    entry["tokens"] = dict(prompt=usage.get("prompt_tokens"), completion=usage.get("completion_tokens"))
                entry["_served"] = served(reply.get("model"))
                if text:
                    entry["translation"] = text
                else:
                    entry["status"] = "empty"
            except Failure as exc:
                entry.update(status=exc.status, error=endpoint.mask(exc),
                             attempts=entry["attempts"] or getattr(exc, "attempts", None),
                             elapsed_s=entry["elapsed_s"] or getattr(exc, "seconds", None))
            return entry

        def commit(row, entry):
            name = entry.pop("_served", None)
            if name and name not in session["served_models"]:
                session["served_models"].append(name)
            journal.append(entry)
            session["sent"] += 1
            counts[entry["status"]] += 1
            if entry["status"] != "ok":
                log(f"{entry['status']} {entry['id']}: {entry['error'] or 'no text in the reply'}")
            if session["sent"] == len(todo) or session["sent"] % 25 == 0 or time.monotonic() - last[0] > 15:
                last[0] = time.monotonic()
                rate = session["sent"] / max(time.monotonic() - started, 1e-9) * 60
                log(f"[{session['sent']:>5}/{len(todo)}] " + ", ".join(f"{s} {counts[s]}" for s in STATUSES)
                    + f"; {rate:.1f} items/min")

        result = run_all(todo, work, commit, options.concurrency, log) if todo else dict(stop=None, interrupted=False)
        session.update(ended=now(), wall_s=round(time.monotonic() - started, 3), stop=result["stop"],
                       interrupted=result["interrupted"])
        rows = journal.read()
        record["counts"], record["median_seconds"], record["tokens"] = totals(rows, items, selected)
        record["wall_s"] = round(sum(s.get("wall_s") or 0 for s in record["sessions"]), 3)
        record["predictions_sha256"] = (hashlib.sha256(journal.path.read_bytes()).hexdigest()
                                        if journal.path.exists() else None)
        record["note"] = ("median_seconds is end-to-end time per successful request in this run, not a speed result "
                          "of the benchmark; speed and memory come only from the serial speed benchmark.")
        write_atomic(record_path, record)
    c = record["counts"]
    summary = ", ".join(f"{s} {c[s]}" for s in STATUSES)
    if result["stop"]:
        log(f"Stopped: {result['stop']}. {session['sent']} items saved this session; run the same command again "
            "to resume.")
        return 3
    if result["interrupted"]:
        log(f"Interrupted: {session['sent']} items saved this session ({summary} in total); run the same command "
            "again to resume.")
        return 130
    log(f"Done: {c['items']} items in {journal.path} ({summary}); settings in {record_path}.")
    if c["selected_not_run"]:
        log(f"{c['selected_not_run']} selected items were not run.")
    if getattr(options, "hint", True):
        log(f"Next: translate-bench score --predictions {journal.path} --system-name {options.model} "
            f"--out {out / 'score'}")
    return 0
