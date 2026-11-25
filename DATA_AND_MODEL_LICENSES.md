# Third-party data, models, metrics and services

This repository distributes the author's scores, identifiers (line numbers, document and segment ids, model ids), settings (revisions, client flags) and SHA-256 digests for the datasets, models, metrics and services below. It distributes no test text, no model weights and no system outputs. Obtain datasets and weights from their publishers and keep their notices for any separate use. The results are for evaluation, not for training models. [Results licence](LICENSE-results.md)

## Test sets

| Dataset | Publisher terms and attribution |
| --- | --- |
| [NTREX-128](https://github.com/MicrosoftTranslator/NTREX) | Microsoft. Federmann, Kocmi and Xin (2022), *NTREX-128 – News Test References for MT Evaluation of 128 Languages*. [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) |
| [WMT12](https://www.statmt.org/wmt12/translation-task.html) | WMT test material for research purposes. Callison-Burch et al. (2012), [W12-3102](https://aclanthology.org/W12-3102/) |
| [WMT13](https://www.statmt.org/wmt13/translation-task.html) | WMT test material for research purposes. Bojar et al. (2013), [W13-2202](https://aclanthology.org/W13-2202/) |
| [WMT23](https://github.com/wmt-conference/wmt23-news-systems) | WMT test material for research purposes. Kocmi et al. (2023), [2023.wmt-1.1](https://aclanthology.org/2023.wmt-1.1/) |
| [WMT24++](https://huggingface.co/datasets/google/wmt24pp) | Apache-2.0 dataset card; the underlying WMT texts have their own provenance. [WMT24 overview](https://aclanthology.org/2024.wmt-1.1/), [WMT24++](https://aclanthology.org/2025.findings-acl.634/) |

`translate-bench prepare` downloads these files from their publishers. Keep the texts it writes out of public repositories, issues and pull requests.

## Local models

The registry ([`configs/systems.json`](configs/systems.json)) gives each quantized file, revision and SHA-256. The licence column is the base model's card as recorded at measurement time. Where no licence was recorded, the entry links the model card.

| System | Base model · quantized weights | Licence |
| --- | --- | --- |
| Hy-MT2 1.8B | [tencent/Hy-MT2-1.8B](https://huggingface.co/tencent/Hy-MT2-1.8B) · tencent/Hy-MT2-1.8B-GGUF | Apache-2.0 |
| Hy-MT2 7B | [tencent/Hy-MT2-7B](https://huggingface.co/tencent/Hy-MT2-7B) · tencent/Hy-MT2-7B-GGUF | Apache-2.0 |
| Hy-MT2 30B-A3B | [tencent/Hy-MT2-30B-A3B](https://huggingface.co/tencent/Hy-MT2-30B-A3B) · tencent/Hy-MT2-30B-A3B-GGUF | Apache-2.0 |
| PLaMo 3 Translate 0.8B | [pfnet/plamo-3-translate-0.8b](https://huggingface.co/pfnet/plamo-3-translate-0.8b) · pfnet/plamo-3-translate-0.8b-GGUF | Not recorded here; see the [model card](https://huggingface.co/pfnet/plamo-3-translate-0.8b) |
| PLaMo 3 Translate 2B | [pfnet/plamo-3-translate-2b](https://huggingface.co/pfnet/plamo-3-translate-2b) · pfnet/plamo-3-translate-2b-GGUF | PLaMo Community License |
| PLaMo 3 Translate 8B | [pfnet/plamo-3-translate-8b](https://huggingface.co/pfnet/plamo-3-translate-8b) · pfnet/plamo-3-translate-8b-GGUF | PLaMo Community License |
| PLaMo 3 Translate 31B | [pfnet/plamo-3-translate-31b](https://huggingface.co/pfnet/plamo-3-translate-31b) · pfnet/plamo-3-translate-31b-GGUF | Not recorded here; see the [model card](https://huggingface.co/pfnet/plamo-3-translate-31b) |
| Index-Translate 2B | [IndexTeam/Index-Translate-2B](https://huggingface.co/IndexTeam/Index-Translate-2B) · IndexTeam/Index-Translate-2B-GGUF | Apache-2.0 |
| Index-Translate 9B | [IndexTeam/Index-Translate-9B](https://huggingface.co/IndexTeam/Index-Translate-9B) · IndexTeam/Index-Translate-9B-GGUF | Apache-2.0 |
| Index-Translate 35B-A3B preview | [IndexTeam/Index-Translate-35B-A3B-preview](https://huggingface.co/IndexTeam/Index-Translate-35B-A3B-preview) · IndexTeam/Index-Translate-35B-A3B-preview-GGUF | Apache-2.0 |
| TranslateGemma 4B | [google/translategemma-4b-it](https://huggingface.co/google/translategemma-4b-it) · Menterium/translategemma-4b-it-GGUF | Gemma Terms |
| TranslateGemma 12B | [google/translategemma-12b-it](https://huggingface.co/google/translategemma-12b-it) · Menterium/translategemma-12b-it-GGUF | Gemma Terms |
| TranslateGemma 27B | [google/translategemma-27b-it](https://huggingface.co/google/translategemma-27b-it) · mradermacher/translategemma-27b-it-GGUF | Gemma Terms |
| Gemma 4 E2B IT | [google/gemma-4-E2B-it](https://huggingface.co/google/gemma-4-E2B-it) · ggml-org/gemma-4-E2B-it-GGUF | Apache-2.0 |
| Gemma 4 E4B IT | [google/gemma-4-E4B-it](https://huggingface.co/google/gemma-4-E4B-it) · ggml-org/gemma-4-E4B-it-GGUF | Apache-2.0 |
| Gemma 4 12B IT | [google/gemma-4-12B-it](https://huggingface.co/google/gemma-4-12B-it) · ggml-org/gemma-4-12B-it-GGUF | Apache-2.0 |
| Gemma 4 31B IT | [google/gemma-4-31B-it](https://huggingface.co/google/gemma-4-31B-it) · ggml-org/gemma-4-31B-it-GGUF | Apache-2.0 |
| Qwen3.5 2B | [Qwen/Qwen3.5-2B](https://huggingface.co/Qwen/Qwen3.5-2B) · unsloth/Qwen3.5-2B-GGUF | Apache-2.0 |
| Qwen3.5 4B | [Qwen/Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B) · unsloth/Qwen3.5-4B-GGUF | Apache-2.0 |
| Qwen3.5 9B | [Qwen/Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B) · unsloth/Qwen3.5-9B-GGUF | Apache-2.0 |
| Qwen3.5 27B | [Qwen/Qwen3.5-27B](https://huggingface.co/Qwen/Qwen3.5-27B) · unsloth/Qwen3.5-27B-GGUF | Not recorded here; see the [model card](https://huggingface.co/Qwen/Qwen3.5-27B) |
| Seed-X-PPO 7B | [ByteDance-Seed/Seed-X-PPO-7B](https://huggingface.co/ByteDance-Seed/Seed-X-PPO-7B) · mradermacher/Seed-X-PPO-7B-GGUF | OpenMDW-1.0 |
| EuroLLM-Instruct-2512 22B | [utter-project/EuroLLM-22B-Instruct-2512](https://huggingface.co/utter-project/EuroLLM-22B-Instruct-2512) · mradermacher/EuroLLM-22B-Instruct-2512-GGUF | Apache-2.0 |
| Qwen-MT-Lumen | [ATH-MaaS/Qwen-MT-Lumen](https://huggingface.co/ATH-MaaS/Qwen-MT-Lumen) · bac2qh/Qwen-MT-Lumen-MLX-4bit | Apache-2.0 |
| Apple Intelligence on-device model (Foundation Models) | Apple operating-system framework, no weight file | Apple's terms for macOS |
| Apple Intelligence on-device model (Foundation Models, permissive guardrails) | Apple operating-system framework, no weight file | Apple's terms for macOS |
| Apple Translation framework (on-device) | Apple operating-system framework, no weight file | Apple's terms for macOS |

TranslateGemma is subject to the [Gemma Terms](https://ai.google.dev/gemma/terms). Outputs of PLaMo models are subject to the notice in [LICENSE-results.md](LICENSE-results.md).

## Metrics and tools

| Metric or tool | Terms |
| --- | --- |
| [Unbabel/wmt22-comet-da](https://huggingface.co/Unbabel/wmt22-comet-da), [COMET](https://github.com/Unbabel/COMET) | Apache-2.0 |
| [XLM-RoBERTa large](https://huggingface.co/FacebookAI/xlm-roberta-large) | MIT |
| [google/metricx-24-hybrid-large-v2p6](https://huggingface.co/google/metricx-24-hybrid-large-v2p6) and the [mt5-xl](https://huggingface.co/google/mt5-xl) SentencePiece model | Not recorded here; see the [MetricX-24 model card](https://huggingface.co/google/metricx-24-hybrid-large-v2p6) and the [mT5-XL model card](https://huggingface.co/google/mt5-xl) |
| [sacreBLEU](https://github.com/mjpost/sacrebleu) | Apache-2.0 |
| [llama.cpp](https://github.com/ggml-org/llama.cpp) | MIT |
| [MLX](https://github.com/ml-explore/mlx) | MIT |

## Services

| Service | Terms |
| --- | --- |
| [ChatGPT / Codex](https://openai.com/policies/terms-of-use/) | Subscription service terms |
| [Claude / Claude Code](https://www.anthropic.com/legal) | Subscription service terms |
| [Gemini / Antigravity](https://antigravity.google/terms) | Google service and subscription terms |
| [DeepL API](https://developers.deepl.com/docs) | DeepL service terms |
