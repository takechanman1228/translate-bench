# Methodology

How Translate Bench was measured: the v1 results, unchanged in v1.1, and the [hard cases](#hard-cases) and [Overall score](#overall-score) that v1.1 adds. The [protocol](../results/v1/protocol.md) is the exact record of v1, with every seed string, revision and hash, and the [hard-cases protocol](../results/ltb-v1/protocol.md) that of the hard cases. Each system's settings are in [`configs/systems.json`](../configs/systems.json).

## Data

Eighteen directions: English to and from Japanese, Simplified Chinese, Spanish, Korean, French, German, Brazilian Portuguese, Arabic and Indonesian. Each direction has 200 sentences and 20 passages, 3,960 items in all.

**Sentences.** The same 200 lines of [NTREX-128](https://github.com/MicrosoftTranslator/NTREX) news from 61 articles, in every direction. Each line is translated on its own. Out of English the source is the English original and the reference is NTREX's human translation. Into English the two exchange roles. Arabic is Standard Arabic.

**Passages.** Multi-sentence excerpts of WMT test documents, at most 140 words (360 characters for Japanese and Chinese sources), with segments joined by line feeds.

- English to Japanese, Chinese and Spanish: 20 English [WMT24++](https://huggingface.co/datasets/google/wmt24pp) documents, five each of news, social media, speech and literary text.
- Japanese, Chinese and Spanish to English: 20 original-language documents per language. Japanese and Chinese come from the WMT23 general test sets, Spanish from newstest2012/2013.
- The other twelve directions: 20 WMT24++ documents in two sets. *set-8* has two social, two speech and four literary documents, and *set-12* has twelve speech transcripts. Into English, source and reference exchange roles. Arabic is the Egyptian locale.

**Selection.** Every sample was fixed from identifiers and texts before any output existed. Candidates were ordered by the SHA-256 of a seed string followed by an identifier. [`datasets/selection.json`](../datasets/selection.json) records each rule and its result, and `translate-bench prepare` recomputes them from the upstream files. [`datasets/items.jsonl`](../datasets/items.jsonl) lists the items with the SHA-256 of each source and reference.

## Systems

**Local.** Every local system ran on one Apple M6 with 32 GiB of unified memory, macOS 27.0, one item per request.

- 23 GGUF configurations ran through llama.cpp's `llama-server` on Metal, from one pinned build. They used 4-bit weights (Q4_K_M, or Q4_0 for Gemma 4), a 4,096-token context per request, at most 512 output tokens and seed 42.
- Qwen-MT-Lumen ran through MLX at 4 bits.
- Apple's three on-device systems ran through the operating system. The Foundation Models framework got a generic instruction, once with the default guardrails and once with the permissive ones. The Translation framework used its high-fidelity strategy.

Each family used its own published prompt format:

| Prompt format | Systems |
| --- | --- |
| Source as the user message, language codes as chat-template arguments | PLaMo 3 Translate |
| Chinese instruction naming both languages | Index-Translate |
| Chinese instruction when Chinese is involved, otherwise English | Hy-MT2 |
| The published TranslateGemma text template | TranslateGemma |
| The published Seed-X prompt with a target tag | Seed-X-PPO |
| Generic English instruction naming both languages | Gemma 4, Qwen3.5, EuroLLM, Apple Foundation Models |
| Minimal prompt with an empty guidelines block | Qwen-MT-Lumen |

The templates are under `prompt_profiles` in the registry, and each system's sampler is under `generation`. Models with a thinking switch ran with it off.

**Cloud.** GPT models ran through Codex CLI, Claude models through Claude Code and Gemini models through Antigravity CLI, all at medium reasoning effort. Each request carried up to 25 sentences or 5 passages of one direction, drawn from different source documents. DeepL API ran through its translation API on the same batches.

## System settings

<!-- tb:systems -->
| System | Kind | Runtime or client | Directions | Not supported | Items per request | Concurrent requests | Reasoning | Decoding | Completion |
| --- | --- | --- | ---: | --- | --- | ---: | --- | --- | ---: |
| Hy-MT2 1.8B | local | llama.cpp, Q4_K_M | 18 | — | 1 / 1 | 1 | off | sampled (T 0.7, top-p 0.6, top-k 20) | 100% |
| Hy-MT2 7B | local | llama.cpp, Q4_K_M | 18 | — | 1 / 1 | 4 | off | sampled (T 0.7, top-p 0.6, top-k 20) | 100% |
| Hy-MT2 30B-A3B | local | llama.cpp, Q4_K_M | 18 | — | 1 / 1 | 1 | off | sampled (T 0.7, top-p 1.0, top-k off) | 100% |
| PLaMo 3 Translate 0.8B | local | llama.cpp, Q4_K_M | 16 | Brazilian Portuguese | 1 / 1 | 4 | off | greedy | 99.9% (2 failed) |
| PLaMo 3 Translate 2B | local | llama.cpp, Q4_K_M | 16 | Brazilian Portuguese | 1 / 1 | 1 | off | greedy | 100% |
| PLaMo 3 Translate 8B | local | llama.cpp, Q4_K_M | 16 | Brazilian Portuguese | 1 / 1 | 1 | off | greedy | 100% |
| PLaMo 3 Translate 31B | local | llama.cpp, Q4_K_M | 16 | Brazilian Portuguese | 1 / 1 | 3 | off | greedy | 99.97% (1 failed) |
| Index-Translate 2B | local | llama.cpp, Q4_K_M | 18 | — | 1 / 1 | 1 | off | greedy | 100% |
| Index-Translate 9B | local | llama.cpp, Q4_K_M | 18 | — | 1 / 1 | 4 | off | greedy | 99.9% (3 failed) |
| Index-Translate 35B-A3B preview | local | llama.cpp, Q4_K_M | 18 | — | 1 / 1 | 2 | off | greedy | 100% |
| TranslateGemma 4B | local | llama.cpp, Q4_K_M | 18 | — | 1 / 1 | 4 | off | greedy | 100% |
| TranslateGemma 12B | local | llama.cpp, Q4_K_M | 18 | — | 1 / 1 | 1 | off | greedy | 100% |
| TranslateGemma 27B | local | llama.cpp, Q4_K_M | 18 | — | 1 / 1 | 4 | off | greedy | 100% |
| Gemma 4 E2B IT | local | llama.cpp, Q4_0 | 18 | — | 1 / 1 | 1 | off | sampled (T 1.0, top-p 0.95, top-k 64) | 100% |
| Gemma 4 E4B IT | local | llama.cpp, Q4_0 | 18 | — | 1 / 1 | 4 | off | sampled (T 1.0, top-p 0.95, top-k 64) | 100% |
| Gemma 4 12B IT | local | llama.cpp, Q4_0 | 18 | — | 1 / 1 | 1 | off | sampled (T 1.0, top-p 0.95, top-k 64) | 100% |
| Gemma 4 31B IT | local | llama.cpp, Q4_0 | 18 | — | 1 / 1 | 2 | off | sampled (T 1.0, top-p 0.95, top-k 64) | 99.9% (2 failed) |
| Qwen3.5 2B | local | llama.cpp, Q4_K_M | 18 | — | 1 / 1 | 1 | off | sampled (T 0.7, top-p 0.8, top-k 20) | 100% |
| Qwen3.5 4B | local | llama.cpp, Q4_K_M | 18 | — | 1 / 1 | 4 | off | sampled (T 0.7, top-p 0.8, top-k 20) | 100% |
| Qwen3.5 9B | local | llama.cpp, Q4_K_M | 18 | — | 1 / 1 | 4 | off | sampled (T 0.7, top-p 0.8, top-k 20) | 100% |
| Qwen3.5 27B | local | llama.cpp, Q4_K_M | 18 | — | 1 / 1 | 4 | off | sampled (T 0.7, top-p 0.8, top-k 20) | 100% |
| Seed-X-PPO 7B | local | llama.cpp, Q4_K_M | 18 | — | 1 / 1 | 4 | off | greedy | 99.9% (3 failed) |
| EuroLLM-Instruct-2512 22B | local | llama.cpp, Q4_K_M | 16 | Indonesian | 1 / 1 | 2 | off | greedy | 99.8% (7 failed) |
| Qwen-MT-Lumen | local | MLX, 4-bit | 5 (sentences 5, passages 6) | see note | 1 / 1 | 1 | off | greedy | 100% |
| Apple Intelligence on-device model (Foundation Models) | local | Apple FoundationModels framework | 14 | Arabic, Indonesian | 1 / 1 | 1 | off | greedy | 92.8% (223 failed) |
| Apple Intelligence on-device model (Foundation Models, permissive guardrails) | local | Apple FoundationModels framework | 14 | Arabic, Indonesian | 1 / 1 | 1 | off | greedy | 100% |
| Apple Translation framework (on-device) | local | Apple Translation framework | 18 | — | 1 / 1 | 1 | off | framework (highFidelity) | 100% |
| GPT-6.2 Astra | cloud | Codex CLI | 18 | — | 25 / 5 | — | medium | service default | 100% |
| GPT-6.2 Sol | cloud | Codex CLI | 18 | — | 25 / 5 | — | medium | service default | 100% |
| GPT-6.1 Terra | cloud | Codex CLI | 18 | — | 25 / 5 | — | medium | service default | 100% |
| GPT-6 Luna | cloud | Codex CLI | 18 | — | 25 / 5 | — | medium | service default | 100% |
| Claude Fable 5.2 | cloud | Claude Code | 18 | — | 25 / 5 | — | medium | service default | 100% |
| Claude Opus 5.5 | cloud | Claude Code | 18 | — | 25 / 5 | — | medium | service default | 100% |
| Claude Sonnet 5.5 | cloud | Claude Code | 18 | — | 25 / 5 | — | medium | service default | 99.4% (25 failed) |
| Claude Haiku 5.5 | cloud | Claude Code | 18 | — | 25 / 5 | — | medium | service default | 100% |
| Gemini 4 Argon | cloud | Antigravity CLI | 18 | — | 25 / 5 | — | medium | service default | 100% |
| Gemini 4 Neon | cloud | Antigravity CLI | 18 | — | 25 / 5 | — | medium | service default | 100% |
| Gemini 4 Hydrogen | cloud | Antigravity CLI | 18 | — | 25 / 5 | — | medium | service default | 100% |
| Gemini 3.8 Flash | cloud | Antigravity CLI | 0 (sentences 12, passages 0) | — | 25 / 5 | — | medium | service default | 100% |
| DeepL API | cloud | DeepL API | 18 | — | 25 / 5 | — | none | none (translation API) | 100% |

Qwen-MT-Lumen: English to Korean, German, Indonesian, Japanese and Simplified Chinese, and English to Arabic on passages only (the Egyptian locale of WMT24++); every other direction is unsupported. Gemini 3.8 Flash: passages only from set-12, so it has no complete 20-passage cell. Its sentences cover 12 directions.
<!-- /tb:systems -->

Items per request: sentences / passages. Concurrent requests: how many requests one local server decoded at once in the quality runs. Decoding: the settings sent to the model. Completion: items with a scored translation, of those attempted. Failed items stay in the denominator and are never retried ([what counts as a failure](../results/v1/protocol.md#failures)).

## Metrics

| Metric | Version | Computed on |
| --- | --- | --- |
| COMET-22 | `Unbabel/wmt22-comet-da`, unbabel-comet 2.2.7, CPU | Every item |
| MetricX-24 | `google/metricx-24-hybrid-large-v2p6`, float32, with and without the reference | Every item |
| chrF++ | sacreBLEU 2.5.1, `nrefs:1\|case:mixed\|eff:yes\|nc:6\|nw:2\|space:no\|version:2.5.1` | Every item |
| LLM judge | Claude Fable 5.2, [judge v1](#judge-v1) | A fixed sample of 288 items |
| Hard cases | Last Translation Benchmark rules, checked by Claude Sonnet 5.5 ([hard cases](#hard-cases)) | 208 items in the release's directions (911 in all) |

[Reading the metrics](metrics.md) explains what each one measures and why they disagree.

## Aggregation

A *cell* is one text type in one direction: 200 sentences or 20 passages. A cell's COMET-22 and MetricX-24 are means over its scored items, and its chrF++ is corpus chrF++ from pooled statistics. The overall score averages the sentence and passage cells 50:50 within each direction, then averages the 18 directions with equal weight. A system is ranked on a selection only if it has every cell of it. `sentence_weights` in [`results/v1/summary.json`](../results/v1/summary.json) lists the leaders at other sentence weights.

## Intervals

Two systems are compared cell by cell on the items both scored, and the difference is aggregated like the score. The 95% interval spans the 2.5th to 97.5th percentile of 2,000 paired bootstrap draws. The resampling unit is the source document, an NTREX article or a WMT document. A document keeps its draw in every cell it appears in, so one English article is resampled jointly across all 18 directions. The draws come from a fixed seed, so every interval can be recomputed exactly (`translate_bench/stats.py`). Intervals are not adjusted for multiple comparisons. When an interval includes zero, the two systems are tied.

## Speed and memory

Each local system was timed alone in a separate benchmark, with its quality-run settings and one request at a time. A run loaded the model once, discarded one warm-up request, then translated a fixed subset of 30 sentences and 30 passages three times. The subset is drawn from the item ids. The benchmark reports median and 90th-percentile seconds per item, load time, and the peak resident memory of the inference process, sampled every second. Cloud seconds and estimated cost per item come from the batched client requests ([protocol](../results/v1/protocol.md#speed-and-memory)).

## Judge v1

The judge rates every system on one fixed sample: the first 8 item ids per direction and text type, ordered by a hash of the id. That gives 288 items from 111 source documents ([`datasets/judge-sample.json`](../datasets/judge-sample.json)).

- **Pairwise.** Each system is compared with DeepL API on the sample. Identical outputs count as ties without a judge. Otherwise the judge sees the source and both outputs, blind and in a fixed order, and picks the better one or calls a tie.
- **Errors.** The judge counts critical, major and minor errors in each translation on its own, ignoring style. DeepL API is annotated like every other system.
- **Judge.** Claude Fable 5.2 through Claude Code at high reasoning effort. It sees no reference.

Judge results are aggregated like the scores, with their own 2,000 bootstrap draws. *Preferred* is the share of non-tied items on which the system won. *Error-free* is the share of items with no error counted. The rows and summary are in [`results/v1/judge/`](../results/v1/judge/). `translate-bench judge` runs the same protocol on your own predictions.

## Hard cases

Added in v1.1. Every system translated the 911 text items of the [Last Translation Benchmark](https://github.com/zouharvi/last-translation-benchmark) (LTB; Zouhar et al., 2026, [arXiv:2609.04173](https://arxiv.org/abs/2609.04173); data CC BY 4.0) with its v1 prompt, settings and batching. Each item comes with handwritten rules, such as a word the translation must or must not use. Claude Sonnet 5.5 checks each rule with LTB's own verification prompt, and an item passes when all its rules pass. An item a system cannot translate (an unsupported language pair) or leaves empty fails. The 208 items whose direction is one of the release's 18 (11 directions occur) give the hard-cases figure of the leaderboard and the Overall score; for a system below 18 directions, the items in the directions it covers give it. The pass rate on all 911 is in the summary too. Intervals come from 2,000 bootstrap draws of items. LTB's own leaderboard uses Gemini 3.8 Flash as the verifier, so these are not LTB leaderboard numbers; ten systems were checked again with it. The [hard-cases protocol](../results/ltb-v1/protocol.md) has the details, and the verdicts are in [`results/ltb-v1/`](../results/ltb-v1/), without texts.

## Overall score

Added in v1.1. The Overall score is the mean of three pillars on a 0–100 scale, weighted equally and rounded to one decimal: COMET-22 × 100, the judge's error-free share in percent, and the hard-case pass rate in percent. A system gets one when every pillar covers at least 12 of the 18 directions. Below 18, each pillar is a mean over the directions the system covers: COMET-22 over its complete directions (sentences and passages 50:50), the judge over its sampled items in them, and the hard cases over the items in those directions, so items in a direction it does not cover leave the denominator instead of counting as failed. Coverage comes from v1 (both text types complete). The coverage, such as 16/18, is published with the score; the others keep their pillar values. MetricX-24 is not part of it, and it has no interval of its own. [`results/v1.1/overall.json`](../results/v1.1/overall.json) holds every system's pillars and coverage, and `translate-bench verify` recomputes it from the three summaries.
