# Changelog

## 1.0.0

- Results for 40 systems (27 local, 13 cloud) in 18 directions between English and nine languages, 200 sentences and 20 passages per direction (`results/v1/`).
- Item rows with COMET-22, MetricX-24, chrF++ statistics and the SHA-256 of every output, a summary with rankings and paired intervals, local speed and memory, and judge v1 results.
- The system registry (`configs/systems.json`) and the dataset manifests with the SHA-256 of every source and reference (`datasets/`).
- Commands: `verify`, `leaderboard`, `prepare`, `run`, `score`, `compare`, `evaluate`, `judge` and `validate-submission`.
