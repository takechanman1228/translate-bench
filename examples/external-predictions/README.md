# Translations made elsewhere

`translate-bench score` scores any file of translations, from an API, an app or your own pipeline. `compare` then places the result among the published systems.

## Try it on the synthetic set

[`data/`](data/) holds 20 made-up items with made-up references and translations. It needs no download and no model.

```sh
translate-bench score --predictions examples/external-predictions/data/predictions.jsonl \
  --inputs examples/external-predictions/data --system-name synthetic-demo --out private/synthetic-demo
translate-bench compare --results private/synthetic-demo
```

The synthetic items are not the release's inputs, so `compare` shows scores without a rank.

## Input format

`translate-bench prepare` writes `private/inputs/sentences.tsv` and `passages.tsv`. They are tab-separated with the columns `id, src, tgt, source, reference, domain, doc`. Translate the `source` column without looking at the reference.

## Predictions format

One JSON object per line, with the item's `id` and your `translation`:

```json
{"id": "ntrex/1984/en-es", "translation": "..."}
{"id": "ntrex/1985/en-es", "status": "error"}
```

A failed item has `"status": "error"`. Failed and missing items stay in the denominator.

## Score and compare

```sh
python -m pip install -e '.[comet]'
translate-bench score --predictions private/my-system.jsonl --system-name my-system \
  --metrics chrf,comet22 --out private/my-system
translate-bench compare --results private/my-system
```

## Submitting

A submission needs a `run.json`. For translations made without `translate-bench run`, write it by hand:

```json
{
 "model": "my-system 2026-11",
 "prompt": {"description": "the system's own API; no prompt"},
 "generation": {"description": "service defaults"},
 "request": {"items_per_request": 1, "concurrent_requests": 4},
 "counts": {"items": 3960, "ok": 3960}
}
```

[CONTRIBUTING.md](../../CONTRIBUTING.md) lists the other files.
