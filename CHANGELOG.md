# Changelog

## 1.1.0

- `results/v1/` is unchanged from 1.0.0.
- Hard cases (`results/ltb-v1/`): all 40 systems on the 911 text items of the Last Translation Benchmark (Zouhar et al., 2026; data CC BY 4.0), with per-item verdicts and SHA-256 digests but no texts, pass rates with bootstrap intervals, and a cross-check of ten systems with a second verifier (`second-verifier.json`). The verifier is Claude Sonnet 5.5; these are not official LTB leaderboard numbers.
- Overall score (`results/v1.1/overall.json`): the mean of COMET-22 × 100, the LLM judge's error-free share and the pass rate on the 208 hard-case items in the release's directions. `translate-bench verify` recomputes it.
- Overall score eligibility: a system gets an Overall score when every pillar covers at least 12 of the 18 directions (38 of 40 systems). Below 18, each pillar is a mean over the directions the system covers, and the hard cases count only the items in those directions (`covered` in `results/ltb-v1/summary.json`); the coverage, such as 16/18, is published with the score and shown next to the system. Qwen-MT-Lumen (5 directions) and Gemini 3.8 Flash (no direction with both text types) get none. The leaderboard lists all 40 systems by default, and "Only systems with all 18 directions" replaces "Include partial coverage".
- Leaderboard: Overall and Hard cases columns, sorted by Overall by default; the four picks above the table go by Overall. A system's page shows its Overall score and rank, its three pillars and, for a system without an Overall score, the reason. The text-type filter's "Overall" is now "Both types", and the Languages and Speed & memory charts say they use COMET-22.
- `translate-bench leaderboard` ranks by the Overall score by default (`--metric hard_cases` by the hard-case pass rate) and shows both as columns with every metric.
- README: results table by Overall, new findings, an Overall score section, a lead figure of the Overall score and its three pillars, and a hard-cases figure. Figures name DeepL API without a developer suffix.
- Docs: hard cases and the Overall score in the methodology, the metrics guide and the limitations.

## 1.0.0

- Results for 40 systems (27 local, 13 cloud) in 18 directions between English and nine languages, 200 sentences and 20 passages per direction (`results/v1/`).
- Item rows with COMET-22, MetricX-24, chrF++ statistics and the SHA-256 of every output, a summary with rankings and paired intervals, local speed and memory, and judge v1 results.
- The system registry (`configs/systems.json`) and the dataset manifests with the SHA-256 of every source and reference (`datasets/`).
- Commands: `verify`, `leaderboard`, `prepare`, `run`, `score`, `compare`, `evaluate`, `judge` and `validate-submission`.
