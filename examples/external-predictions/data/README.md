# Synthetic example set

Made-up sentences and passages written for this repository, with made-up reference translations and made-up system outputs. They are not the release's inputs, they come from no test set, and scores on them are not comparable with the published results; `score` and `compare` say so when they read them.

- `sentences.tsv`: 8 English sentences, each with a Japanese and a German reference (16 items).
- `passages.tsv`: 2 English passages of three sentences, each with a Japanese and a German reference (4 items).
- `predictions.jsonl`: one made-up translation per item; `synthetic/s08/en-ja` is recorded as a failed request, to show how a failure counts.

The files have the format `translate-bench prepare` writes, and every item id starts with `synthetic/`. The repository's public-tree check allows text in these three files only, and only under such ids.

License: [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/). The authors waive all rights to these texts to the extent possible under law.
