# Evaluation protocol, v1

The exact record of how Translate Bench v1 was measured. [Methodology](../../docs/methodology.md) describes the design for readers. System settings are in [`configs/systems.json`](../../configs/systems.json), and file formats in `translate_bench/schema.py`.

## Items

The items are described in [Methodology](../../docs/methodology.md#data). The *core* directions are those between English and Japanese, Simplified Chinese or Spanish. NTREX Arabic is the `arb` file, the WMT23 references are `refA`, and WMT24++ Arabic is the `ar_EG` locale. In the twelve other directions, out of English the reference is the WMT24++ human post-edit.

A passage is the first contiguous run of aligned segments with a nonempty source and target, stopping before the length would exceed 140 words (360 characters for Japanese and Chinese sources). A run shorter than 12 words (28 characters) is not eligible. Segments are joined with a line feed. One frozen English document whose first segment alone exceeds the cap uses that segment in full.

Every selection orders candidates by the SHA-256 of a seed string followed by an identifier. The seed strings must be used exactly as written:

| Selection | Seed string | Rule |
| --- | --- | --- |
| NTREX sentences | `open-local-translation/ntrex-v1/2026-11-19` | Lines nonempty in the document file and in English, Spanish, Chinese and Japanese. Documents ordered by SHA-256 of `seed/document`; documents at odd positions form the held-out half; within a document, lines ordered by SHA-256 of `seed/line`; one line from every document before a second from any; the first 200. |
| Core passages from English | `local-translate/2026-11-19/wmt-v1` | Documents in the Spanish, Chinese and Japanese WMT24++ files with no bad-source flag, a nonempty target in every segment and the same segments; per domain, ordered by SHA-256 of `seed` + document; the first document of at most 120 words is a development document; the next five are held out. |
| Core passages into English | `local-translate/wmt-docs/2026-11-19` | Eligible excerpts interleaved across domains, each domain ordered by SHA-256 of `seed/document`; the first 5 are development documents, the next 20 are held out. |
| set-8 | `size-sweep-v1/` | The first 8 of the 20 English core documents by SHA-256 of `seed` + `wmt24pp/` + document. |
| set-12 | `size-sweep-v1/` | WMT24++ documents outside the 66 excluded in `selection.json`, present and identical in English in the six locale files, with an eligible excerpt with the same segments in each; the first 12 by SHA-256 of `seed` + `wmt24pp/` + document. No output, score or domain filter. 87 of the 89 eligible documents are speech. |
| Speed subsets | `local-mt-bench/v2/amendment-5/speed/` | See *Speed and memory*. |

[`datasets/selection.json`](../../datasets/selection.json) records each rule, its frozen result and the 66 excluded documents. `translate-bench prepare` recomputes every selection from the upstream files and refuses to write inputs that differ.

## Local systems

llama.cpp is version 0.9.0-dev build 1 at commit `494d0f4`, with its binary SHA-256 in the registry. Every weight file is checked against its SHA-256 before it is loaded. Hy-MT2 30B-A3B has a 60-second request deadline, and other requests time out after 120 seconds. Apple's Foundation Models framework runs with greedy sampling and at most 512 response tokens. Apple's Translation framework uses its `highFidelity` strategy.

Quality runs use one of two modes, recorded in each item row's `execution` field. In *serial* mode the server serves one request at a time and restarts for every partition. In *throughput* mode one server stays loaded for all of a configuration's inputs and serves up to N requests at once (`-np N`, 4,096 tokens per slot), with N in the registry's `request_mode`. Requests, prompts, decoding settings, seeds, weights and the server binary are the same in both modes. Concurrent decoding can change a sampled output, and occasionally a greedy one, at the floating-point level. In a test on TranslateGemma 12B, two concurrent requests changed 1 of 20 passages and 0 of 100 sentences. Quality-run timing is not a result.

## Cloud systems

Twelve systems run through their vendors' command-line clients at medium reasoning effort:

| Client | Version | Systems |
| --- | --- | --- |
| Codex CLI | 0.171.0 | GPT-6.2 Astra, GPT-6.2 Sol, GPT-6.1 Terra, GPT-6 Luna |
| Claude Code | 2.1.329 | Claude Fable 5.2, Opus 5.5, Sonnet 5.5, Haiku 5.5 |
| Antigravity CLI | 1.5.13 on November 20, not recorded for later runs | Gemini 4 Argon, Neon and Hydrogen, Gemini 3.8 Flash |

Each batch is one fresh client process with no saved session, invoked as in the registry (`client.invocation`):

```sh
codex --ask-for-approval never exec --ignore-user-config --ignore-rules --ephemeral --skip-git-repo-check \
  --sandbox read-only --color never -c 'model_reasoning_effort="medium"' --model "$MODEL" --json -
claude -p --setting-sources '' --strict-mcp-config --tools '' --no-session-persistence --effort medium \
  --output-format json --model "$MODEL"
agy -p "$PROMPT" --sandbox --disable-slash-commands --output-format stream-json --model "$MODEL" \
  --print-timeout "${TIMEOUT}s"
```

Codex CLI and Claude Code read the prompt on standard input. For Antigravity CLI the model id ends in `-medium` (for example `gemini-4-neon-medium`), which selects medium effort. The clients' own system prompts are part of the condition.

Each request carries a frozen batch of up to 25 sentences or up to 5 passages of one direction, each from a different source document. The batch is a JSON object whose keys `T01`, `T02`, … map to the sources in input order. It follows this instruction (`cloud-batch-json` in the registry), with the target language name in place of `{language}`:

```text
Translate each item independently into {language}. Preserve the source's meaning, facts, names, quantities, register, and paragraph breaks. Use only the supplied text. Do not use tools, files, web search, or citations. Return one JSON object mapping every supplied key to its translation string in the same order. Use JSON escapes for line breaks inside strings. Return only the object.
```

DeepL API runs through DeepL's translation API. It receives the source strings of the same batches as a text array, with explicit source and target languages: English output as EN-US, Portuguese as PT-BR, Chinese as ZH-HANS and Arabic as AR. It gets one request per batch, with no retry, no instruction and no reasoning setting.

## Failures

A transport error, a timeout, a wrong model alias, an empty output or a finish other than `stop` (for example the 512-token limit) is a failed item. So are an Apple guardrail error and a cloud item with no translation after two attempts of its batch. Failed items stay in the denominator of completion and are never retried with other settings. An output that copies the source, a refusal returned as text and an output in the wrong language are scored. Nothing is replaced, filtered or re-prompted after the fact.

## Metrics

- **COMET-22**: `Unbabel/wmt22-comet-da` at revision `2760a223ac957f30acfb18c8aa649b01cf1d75f2` (checkpoint SHA-256 `e213091cde220f97b89f8bdfa750c458cfea741ad62affb455b59900210ff2af`), XLM-R tokenizer `xlm-roberta-large` at `c23d21b0620b635a76227c604d44e43a9f0ee389`, unbabel-comet 2.2.7, on CPU, batch size 4. An item is scored only if source, reference and output each fit in 512 XLM-R tokens, and every successful output did.
- **chrF++**: sacreBLEU 2.5.1, signature `nrefs:1|case:mixed|eff:yes|nc:6|nw:2|space:no|version:2.5.1`. A cell's chrF++ is corpus chrF++ from the pooled statistics of its scored items, and the item rows store the 24 counts per item.
- **MetricX-24**: `google/metricx-24-hybrid-large-v2p6` at revision `51e875ba5c525c81627cfd135ee10f43c87dce00` (`pytorch_model.bin`, SHA-256 `f584e231b25a20d7766f03fa464d0b990e235b8514a3de2034002132c04a2878`), with the mT5 SentencePiece model of `google/mt5-xl` at `63fc6450d80515b48e026b69ef2fbbd426433e84` (SHA-256 `ef78f86560d809067d12bac6c09f19a462cb3af3f54d2b8acbba26e1433125d6`), in float32. Every successful output is scored with and without the reference. No input reached the 1,535-token limit. The scorer feeds the official input strings to the same checkpoint but tokenizes with the raw SentencePiece model instead of the official fast tokenizer. Against the official implementation (google-research/metricx at commit `fc4978eb064670f7cc33e93ea4f52d38396b8ae6`) on 282 stored inputs, scores agree within 0.00001 where the tokens agree. 78 of the 243,251 distinct inputs (0.03%) tokenize differently, which changes their scores by up to 1.88 points, system means by at most 0.0022 and no system's position in either MetricX-24 ranking.

## Intervals

The bootstrap draws come from NumPy's PCG64 seeded with the first eight bytes of the SHA-256 of the string `site-v2`. Documents are drawn with replacement within strata of documents that cover the same set of cells, with the strata in a fixed order (`translate_bench/stats.py`).

## Speed and memory

Within each direction, the speed subset orders items by the SHA-256 of `local-mt-bench/v2/amendment-5/speed/` followed by the item id. The configuration's directions are taken in lexicographic order, one item from each in turn, until each type has 30 items. The three repetitions alternate sentences and passages. Seconds are end to end per successful item, pooled over the repetitions. A run starts only under the benchmark's measurement conditions, and a repetition during which they were not met is flagged in [`speed.json`](speed.json) and kept.

Cloud time and cost come from the batched client requests of November 20. In each direction, each item gets its request's elapsed time, including client start-up, divided by the items in the request. The published seconds per item are the mean over directions of the per-direction medians. Tokens per item, including the clients' own instructions, and the estimated cost per 1,000 items at that day's API list prices are averaged over directions the same way. Because they come from batched requests, these figures are not comparable with the local medians. DeepL API's cost is not estimated.

## Judge v1

The rows and the summary are in [`judge/`](judge/), and `verify` recomputes the summary from the rows.

- **Sample.** [`datasets/judge-sample.json`](../../datasets/judge-sample.json) holds, within each direction and text type, the first 8 item ids sorted by the SHA-256 of `translate-bench/v1/judge-sample/` followed by the id. An item is missing for a system when it has no successful output (`failed`) or its direction is unsupported (`not run`).
- **Pairwise against DeepL API.** Two outputs equal after removing leading and trailing whitespace are a tie without a judge (`identical`). Otherwise the judge sees the source and the two outputs as A and B and returns a winner (A, B or tie) and the number of major accuracy errors in each. Output A follows the SHA-256 of `translate-bench/v1/judge-pairwise/shown-first/`, the system, `/` and the item id. The release applied this rule, and the order of the items within a request, to internal system identifiers, so each row's archived `shown_first` field is authoritative. One request holds at most 8 items of one system, direction and text type.
- **Errors.** The annotator counts critical, major and minor errors (mistranslation, omission, addition, wrong name or number) in one candidate at a time. Each distinct output of an item is annotated once, and its counts apply to every system that produced it (`shared`).
- **Judge.** Claude Fable 5.2 through Claude Code at high reasoning effort, with no settings files, tools, MCP servers or saved sessions. An answer counts only if it has every requested key with valid values, and a request is sent at most twice per run. 1,331 pairwise requests judged 10,365 items, and 1,337 annotation requests covered 9,667 distinct outputs. Both instructions are in `translate_bench/judge.py`.
- **Aggregation.** An item of a cell of n items weighs 1 / (D · 2 · n), with D the directions counted. The overall values use the directions in which a system has items of both types, and the per-type values every direction with items of that type. *Net* is the weighted mean of +1 (system preferred), −1 (DeepL API preferred) and 0 (tie, judged or identical). *Preferred* is the weighted share of the decided items, and *error-free* the weighted share of items with no error counted. The penalty is 25 per critical, 5 per major and 1 per minor error.
- **Intervals.** 95% percentile intervals of 2,000 paired document-bootstrap draws from the seed string `translate-bench/v1/judge-bootstrap`. The sampled source documents are drawn with replacement within strata of documents that cover the same cells of the release's inputs, and a document's draw count applies to all its items. A draw that leaves a needed cell without documents is skipped, and `draws` in the summary counts the draws used.

## Measurement dates

- Local translations: November 19–25, 2026. Cloud translations: November 20–23, 2026.
- Speed benchmark: November 23 and 25. Judge v1: November 25.
- Apple Foundation Models with default and with permissive guardrails returned byte-identical outputs on all 2,857 items both completed. The two differ only on the 223 items that the default guardrails failed.
