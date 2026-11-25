# A GGUF model with llama-server

Evaluate a GGUF model with llama.cpp's `llama-server`, the way the release ran its 23 GGUF configurations. Run every command from the checkout. Inputs, translations and scores go under `private/`, which Git ignores.

## Install and prepare

```sh
python -m pip install -e '.[comet]'
translate-bench prepare
```

## Start the server

```sh
llama-server -m my-model-Q4_K_M.gguf --host 127.0.0.1 --port 8080 -c 4096 -np 1 --jinja
```

These are the release's settings: a 4,096-token context per request, one request at a time, and the chat template embedded in the GGUF. For N parallel requests, start the server with `-np N -c $((4096 * N))` and pass `--concurrency N` to `run`.

## Smoke test

```sh
translate-bench evaluate --model my-model --base-url http://127.0.0.1:8080/v1 \
  --pairs en-ja --limit 5 --metrics chrf,comet22 --out private/runs/my-model-smoke
```

A partial run gets scores but no rank. The first COMET-22 score downloads the checkpoint (about 2.3 GB).

## Full run

```sh
translate-bench run --model my-model --base-url http://127.0.0.1:8080/v1 --out private/runs/my-model
translate-bench score --predictions private/runs/my-model/predictions.jsonl \
  --system-name my-model --metrics chrf,comet22 --out private/runs/my-model/score
translate-bench compare --results private/runs/my-model/score
```

The defaults are the release's generic instruction, temperature 0, at most 512 tokens, seed 42 and a 120-second deadline.

- **Thinking models:** add `--extra-body '{"chat_template_kwargs": {"enable_thinking": false}}'`.
- **Published prompts:** `--prompt-profile hy-mt`, `index-translate`, `plamo` or `translategemma`, or `--prompt-file FILE` with `{source}`, `{target}` and `{text}`.

## Rerun a release system

`--settings-from` takes the system's prompt profile, decoding settings and deadline from [`configs/systems.json`](../../configs/systems.json). Check the weight file against the registry's `weights.sha256` first.

```sh
shasum -a 256 gemma-4-E4B-it-Q4_0.gguf
translate-bench run --model gemma-4-e4b-it --base-url http://127.0.0.1:8080/v1 \
  --settings-from gemma-4-e4b-it --concurrency 4 --out private/runs/gemma-4-e4b-it
translate-bench score --predictions private/runs/gemma-4-e4b-it/predictions.jsonl \
  --system-name gemma-4-e4b-it --metrics chrf,comet22 --out private/runs/gemma-4-e4b-it/score
translate-bench compare --results private/runs/gemma-4-e4b-it/score --against gemma-4-e4b-it
```

Sampled systems such as Gemma 4 give close, not equal, scores. `--settings-from` covers every llama-server system of the release except Seed-X-PPO 7B.
