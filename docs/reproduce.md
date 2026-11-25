# Reproduce

Run the commands from the checkout with Python 3.11 or 3.12. Each command lists its options with `--help`.

## Verify

`verify` recomputes the summary, rankings, intervals and judge aggregates from the item rows, offline.

```sh
python -m pip install -e .
translate-bench verify
```

Speed, memory and cloud outputs cannot be recomputed from the published rows.

## Prepare

`prepare` downloads the test sets from their publishers, checks them against the published hashes and writes `private/inputs/`.

```sh
translate-bench prepare                  # --pairs en-ja,en-de for some language pairs only
```

## Run

`run` translates the inputs through an OpenAI-compatible endpoint, one item per request, and resumes where it stopped.

```sh
translate-bench run --model my-model --base-url http://127.0.0.1:8080/v1 --out private/runs/my-model
```

| Server | Base URL | `--model` |
| --- | --- | --- |
| llama-server | `http://127.0.0.1:8080/v1` | any name |
| Ollama | `http://127.0.0.1:11434/v1` | the model tag, for example `qwen3:8b` |
| LM Studio | `http://127.0.0.1:1234/v1` | the model identifier LM Studio shows |
| vLLM | `http://127.0.0.1:8000/v1` | the served model name |
| A hosted API | the provider's base URL | the provider's model id |

- **Hosted API.** `--api-key-env VAR` names the environment variable that holds the key, which is never written to a file.
- **Rejected fields.** `--seed none`, `--temperature none` and `--max-tokens none` leave a field out, and `--extra-body JSON` adds others.
- **Thinking models.** Turn thinking off as the release did, for example `--extra-body '{"chat_template_kwargs": {"enable_thinking": false}}'`.
- **Loading.** Ollama and LM Studio load a model on its first request, so send one item with `--limit 1` to a scratch directory first.
- **Parallel requests.** `--concurrency N` sends N requests at once.

To rerun a release system, add `--settings-from SYSTEM_ID` ([llama-server example](../examples/llama-server/README.md)).

## Score

`score` checks that the inputs were the release's and writes item rows in the release's format. `'.[metricx]'` adds MetricX-24.

```sh
python -m pip install -e '.[comet]'
translate-bench score --predictions private/runs/my-model/predictions.jsonl \
    --system-name my-model --metrics chrf,comet22 --out private/runs/my-model/score
```

## Compare

`compare` ranks the system among the published ones on the directions it covers, with paired intervals.

```sh
translate-bench compare --results private/runs/my-model/score    # --against SYSTEM_ID ... for other systems
```

## Evaluate

`evaluate` runs `run`, `score` and `compare` in one command.

```sh
translate-bench evaluate --model my-model --base-url http://127.0.0.1:8080/v1 \
    --metrics chrf,comet22 --out private/runs/my-model
```

## Judge

`judge` runs [judge v1](methodology.md#judge-v1) on the fixed sample with a judge model you choose. Results are comparable only with those of the same judge model.

```sh
translate-bench judge --predictions private/runs/my-model/predictions.jsonl --system-name my-model \
    --judge-model judge-model --base-url https://api.example.com/v1 --api-key-env PROVIDER_API_KEY \
    --out private/judge/my-model
translate-bench compare --results private/runs/my-model/score --judge private/judge/my-model
```

`--against-predictions FILE` judges your outputs pairwise against another system's instead of counting errors.

Translations made another way can be scored directly ([external predictions](../examples/external-predictions/README.md)).
