# Contributing

Translate Bench takes results for new systems, corrections of published results and code changes. Start from a checkout where `make check` passes, after `python -m pip install -e '.[dev]'` with Python 3.11 or 3.12.

Never commit test texts, references, outputs, logs, local paths or credentials. Keep them in `private/`, which Git ignores, and `make check` scans every file and commit for them.

## Submitting a system

1. Run `translate-bench prepare` and translate every item of each direction you attempt, both text types. Use `translate-bench run` for an OpenAI-compatible endpoint, or your own pipeline ([examples](examples/)).
2. Score with the release's metrics: `translate-bench score --metrics chrf,comet22,metricx24 --out DIR`.
3. Put these files in `submissions/<system-id>/`:

   | File | From |
   | --- | --- |
   | `items/<system-id>.jsonl` | `score --out`: one row per item, with scores and the output's SHA-256 |
   | `system.json` | `score --out`: metric versions, the input check, the SHA-256 of the predictions file |
   | `summary.json` | `score --out` (optional, it is recomputed) |
   | `run.json` | `run --out`, or written by hand ([example](examples/external-predictions/README.md#submitting)) |
   | `registry-entry.json` | You: the system's entry for `configs/systems.json` (below) |

4. Run `translate-bench validate-submission submissions/<system-id>` and `make check`, then open a pull request.

The system id is the `--system-name` in lower case, with characters other than letters, digits and dots replaced by hyphens. `run.json` records a local or private endpoint by name only, so it is safe to commit.

### The registry entry

`validate-submission` requires the fields of the first three rows. The others are what a reader needs to repeat the run.

| Field | Content |
| --- | --- |
| `id`, `name`, `developer`, `kind`, `family` | The system id, a display name, the developer, `local` or `cloud`, a family name for grouping sizes |
| `directions_attempted`, `directions_complete` | For `sentence` and `passage`, the directions in the order of the release (`en-ja`, `ja-en`, `en-zh-Hans`, ...) |
| `passage_sets_attempted` | `set-12` and/or `set-8`, the passage sets of the non-core directions in the rows |
| `size_label`, `parameters`, `mixture_of_experts` | For a local model: the size as named, the total parameter count, whether it is a mixture of experts |
| `weights` | For a local model: `format`, `base_model`, `base_revision`, `repository`, `revision`, `file`, `sha256`, `size_bytes`, `quantization`, `license` |
| `runtime` | The engine: `name`, `backend`, `version`, `commit`, `context_tokens_per_request`, `max_output_tokens`, `endpoint`, `request_timeout_s` |
| `prompt_profile`, `generation`, `reasoning` | The prompt (a profile of the registry, or describe yours), the decoding settings as sent, the reasoning or thinking setting |
| `request_mode` | `items_per_request`, `concurrent_requests` and a `note` on anything that changed during the run |
| `client` | For a cloud system: the client or API and its version |
| `unsupported_languages`, `measured` | Languages left out, and the dates of the run (`{"release": {"start": "...", "end": "..."}}`) |

A local GGUF model attempted in English–Japanese and English–German (made up):

```json
{
 "id": "my-model-7b",
 "name": "My Model 7B",
 "developer": "Example Lab",
 "kind": "local",
 "family": "My Model",
 "size_label": "7B",
 "parameters": 7241732096,
 "mixture_of_experts": false,
 "weights": {
  "format": "GGUF",
  "base_model": "example-lab/my-model-7b",
  "base_revision": "0123456789abcdef0123456789abcdef01234567",
  "repository": "example-lab/my-model-7b-GGUF",
  "revision": "89abcdef0123456789abcdef0123456789abcdef",
  "file": "my-model-7b-Q4_K_M.gguf",
  "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "size_bytes": 4368439584,
  "quantization": "Q4_K_M",
  "license": "Apache-2.0"
 },
 "runtime": {
  "name": "llama.cpp", "backend": "Metal", "version": "...", "commit": "...",
  "context_tokens_per_request": 4096, "max_output_tokens": 512, "endpoint": "llama-server", "request_timeout_s": 120
 },
 "prompt_profile": "generic-instruction",
 "generation": {"temperature": 0, "seed": 42, "max_tokens": 512},
 "reasoning": null,
 "request_mode": {"items_per_request": 1, "concurrent_requests": 1, "note": null},
 "client": null,
 "directions_attempted": {"sentence": ["en-ja", "ja-en", "en-de", "de-en"], "passage": ["en-ja", "ja-en", "en-de", "de-en"]},
 "directions_complete": {"sentence": ["en-ja", "ja-en", "en-de", "de-en"], "passage": ["en-ja", "ja-en", "en-de", "de-en"]},
 "passage_sets_attempted": ["set-12", "set-8"],
 "unsupported_languages": [],
 "measured": {"release": {"start": "2026-12-01", "end": "2026-12-02"}}
}
```

### What is checked

`validate-submission` checks that every row follows the schema and is a release item, that every attempted cell is complete, and that the submitted files agree with each other. It cannot see your outputs, so the scores are your attestation until a maintainer reproduces them from your privately shared `predictions.jsonl` or by rerunning the system.

Accepted systems are added in a new results version, and `results/v1/` does not change. Submitted systems have no speed or memory figures.

## Corrections

Open an issue with the system id, the metric, the item ids or table, and how to reproduce the difference. Leave texts and outputs out of it. A confirmed correction is published in a new results version.

## Code

- Keep the base install to the standard library, NumPy and sacreBLEU. Optional metrics live in extras.
- Tests use made-up data only (`tests/fixtures.py`, `tests/fake_openai.py`, the synthetic example set).
- `python -m tests.fake_openai --port 8080` starts a local OpenAI-compatible server for trying `run` and `judge` without a model.
- Run `make check` before opening a pull request. CI runs the same checks on Python 3.11 and 3.12.
