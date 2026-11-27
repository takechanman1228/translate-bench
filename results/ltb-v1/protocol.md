# Hard cases: Last Translation Benchmark

This track measures the 40 systems of Translate Bench v1 on hard-to-translate items. It was added in Translate Bench v1.1; `results/v1/` is unchanged. Only identifiers, digests, verdicts and scores are published here; the texts are in the Last Translation Benchmark itself.

## Items

The [Last Translation Benchmark](https://github.com/zouharvi/last-translation-benchmark) (LTB; Zouhar et al., 2026, [arXiv:2609.04173](https://arxiv.org/abs/2609.04173)) collects human-written, peer-reviewed examples that break current translation systems. Each example comes with handwritten verification rules, such as a word the translation must or must not use. We use the `LTBv1-eval` items of `LTBv1.json` (SHA-256 `99fa3d547530b64b45fa3181811fba11281a013c53b9959091f770a5f6594b9f`): 911 text items in 66 language directions, with 1,693 rules. 208 of them, in 11 directions, are English to or from one of the release's nine languages, language varieties included; `items.jsonl` marks them `ours`.

## Translation

Every system translated every item with the same prompts, settings and batching as in v1: local systems one item per request with their v1 prompt and decoding settings, cloud systems in batches of up to 25 items of one language pair with the v1 batch prompt, DeepL API through its translate endpoint. Prompts that take a language name get LTB's label, variety included (such as "Spanish (Colombia)"); prompts that take a language code get the release's code without the variety, or the plain language name outside the release's languages. The translating system sees only the source text and the languages, never the rules.

An item is `unsupported` when the system's interface offers no way to request its language pair: DeepL API and the Apple Translation framework for a language or pair they do not offer. Such an item has no translation and counts as failed, as does an `empty` one (no translation returned).

## Verification

Each rule is checked with LTB's own verification prompt by Claude Sonnet 5.5 (high effort) through the Claude Code CLI. LTB's leaderboard uses Gemini 3.8 Flash for this step; the prompt and the reading of the reply follow its leaderboard script and are given verbatim in `summary.json`. Every score in `summary.json` comes from this one verifier. An item passes when all its rules pass. The rules of an item are asked in order, one call per rule; after a failed rule the item has failed and its remaining rules are recorded as skipped. An item without a translation fails every rule without a call. These are not LTB's official leaderboard numbers: the verifier differs, and Translate Bench's Overall score uses only the items in the release's directions.

On 300 item-translation pairs with LTB's published verdicts (33 systems), this verifier agreed with LTB on 96.1% of 536 rules (Cohen's kappa 0.92) and on 96.3% of the items (kappa 0.93).

## Scores

`summary.json` gives, per system, the pass rate on all 911 items and on the 208 items in the release's directions, each with a 95% bootstrap interval over items (2,000 draws, fixed seed), the counts of unsupported and empty items, and the pass rate per language pair. A system whose items are not all verified yet is listed under `incomplete`, without rows or scores. `translate-bench verify` recomputes the scores and intervals from `rows/`.

The pass rate on the 208 items in the release's directions is the hard-cases pillar of Translate Bench v1.1's Overall score ([`results/v1.1/overall.json`](../v1.1/overall.json)); for a system below 18 directions it is the pass rate on the items in the directions it covers ([Coverage](#coverage)).

## Coverage

A system that covers fewer than the release's 18 directions in v1 (both text types complete) also gets `covered` in `summary.json`: the pass rate on the items in the release's directions that it covers, with its own bootstrap draws (the seed string followed by `/covered/` and the covered directions). Items in the directions it does not cover leave that denominator instead of counting as failed. The Overall score uses this figure for such systems and the pass rate on all 208 items for the others.

| System | Directions | Items | Passed | Pass rate | On all 208 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Apple Intelligence on-device model (Foundation Models) | 14 | 170 | 1 | 0.6% | 0.5% |
| Apple Intelligence on-device model (Foundation Models, permissive guardrails) | 14 | 170 | 1 | 0.6% | 0.5% |
| EuroLLM-Instruct-2512 22B | 16 | 188 | 2 | 1.1% | 1.0% |
| Gemini 3.8 Flash | 0 | 0 | 0 | — | 34.1% |
| PLaMo 3 Translate 0.8B | 16 | 208 | 3 | 1.4% | 1.4% |
| PLaMo 3 Translate 2B | 16 | 208 | 2 | 1.0% | 1.0% |
| PLaMo 3 Translate 31B | 16 | 208 | 11 | 5.3% | 5.3% |
| PLaMo 3 Translate 8B | 16 | 208 | 9 | 4.3% | 4.3% |
| Qwen-MT-Lumen | 5 | 40 | 3 | 7.5% | 3.8% |

Coverage comes from v1, not from the statuses here, and the two disagree in places: Apple Intelligence on-device model (Foundation Models) was asked to translate all 38 items outside its covered directions (none is `unsupported`); they leave the covered figure all the same. Apple Intelligence on-device model (Foundation Models, permissive guardrails) was asked to translate all 38 items outside its covered directions (none is `unsupported`); they leave the covered figure all the same. EuroLLM-Instruct-2512 22B was asked to translate all 20 items outside its covered directions (none is `unsupported`); they leave the covered figure all the same. Gemini 3.8 Flash has no direction with both text types complete in v1, so it has no covered figure; its pass rate on all 208 items stands. PLaMo 3 Translate 0.8B marked 1 item in a covered direction `unsupported`; it stays in the covered items and counts as failed. PLaMo 3 Translate 2B marked 1 item in a covered direction `unsupported`; it stays in the covered items and counts as failed. PLaMo 3 Translate 31B marked 1 item in a covered direction `unsupported`; it stays in the covered items and counts as failed. PLaMo 3 Translate 8B marked 1 item in a covered direction `unsupported`; it stays in the covered items and counts as failed. Qwen-MT-Lumen was asked to translate all 168 items outside its covered directions (none is `unsupported`); they leave the covered figure all the same.

## Second verifier

To see how much the pass rates depend on the verifier, the items in the release's directions were verified again for ten cloud systems by Gemini 3.8 Flash, the model LTB's leaderboard uses, with no reasoning-effort setting, through the Antigravity CLI. It got the same prompt, the same reading of the reply and the same early exit as Claude Sonnet 5.5, on the same translation files. `second-verifier.json` gives, per system, the items each verifier passed and the items on which the two agree; `translate-bench verify` checks them against `rows/`. Every score in `summary.json` stays Claude Sonnet 5.5's.

The two verifiers gave the same verdict on 97.1% of 2,080 items. Per system, the two pass rates are at most 3.4 points apart. Ranked by pass rate, the systems keep their order, except that Gemini 4 Argon and Gemini 4 Neon, one item apart under Gemini 3.8 Flash, change places.

| System | Claude Sonnet 5.5 | Gemini 3.8 Flash | Same verdict |
| --- | ---: | ---: | ---: |
| Claude Fable 5.2 | 61.5% | 59.1% | 199 of 208 |
| Gemini 4 Neon | 55.8% | 53.4% | 203 of 208 |
| Gemini 4 Argon | 53.4% | 53.8% | 201 of 208 |
| GPT-6.2 Astra | 51.9% | 48.6% | 201 of 208 |
| Claude Sonnet 5.5 | 47.1% | 46.2% | 200 of 208 |
| GPT-6.2 Sol | 45.2% | 44.2% | 204 of 208 |
| Gemini 4 Hydrogen | 42.3% | 42.3% | 202 of 208 |
| Claude Opus 5.5 | 38.9% | 38.0% | 202 of 208 |
| GPT-6.1 Terra | 26.4% | 24.5% | 204 of 208 |
| GPT-6 Luna | 7.7% | 7.2% | 203 of 208 |

## Credit and licence

The Last Translation Benchmark is by Vilém Zouhar and its contributors; its data are licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) and its code MIT. The verdicts and scores here are released under this repository's [results licence](../../LICENSE-results.md).
