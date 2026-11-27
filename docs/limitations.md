# Limitations

- **No human ratings.** The judge is one language model, Claude Fable 5.2, and it also rates the Claude systems, including its own translations. Its sample of 8 items per direction and text type is too small for results by direction.
- **Local and cloud systems ran under different conditions.** Local models received one item per request at 4-bit quantization. Cloud models ran through their vendors' subscription clients at medium reasoning effort, with up to 25 sentences or 5 passages per request, so their time and cost are not comparable with local medians.
- **One machine.** All local speed and memory figures come from one Apple M6 with 32 GiB of memory. Peak process memory is not the RAM a machine needs.
- **Apple's on-device memory is not measured.** Those systems run in system services, outside any process the benchmark can sample.
- **Into English, NTREX sources are translations.** In those directions the source is NTREX's human translation of English news, and the English original is the reference.
- **Passages differ by direction.** In the twelve directions without Japanese, Chinese or Spanish, 14 of the 20 passages are speech transcripts. A difference between directions can reflect genre as well as language.
- **A small test set.** 200 sentences and 20 passages per direction resolve small differences over all 18 directions, but often not within one direction.
- **Public test sets.** The benchmark does not check whether a model was trained on them.
- **Hard cases rest on one verifier and 208 items.** Claude Sonnet 5.5 checks the Last Translation Benchmark's rules, not LTB's own verifier, so these are not LTB leaderboard numbers; a re-run of ten systems with Gemini 3.8 Flash, the model LTB uses, is in the [protocol](../results/ltb-v1/protocol.md). The 208 items fall in 11 of the 18 directions, and for the leading systems a pass rate's 95% interval is more than ten points wide.
- **The Overall score is one weighting.** Its three pillars count equally; another weighting would order the systems differently. It leaves out MetricX-24, and it has no interval of its own.
- **Some Overall scores cover fewer directions.** Seven systems are scored over the 16 or 14 directions they cover (marked 16/18 or 14/18), so their scores are not over the same test as the others'. Among the systems with all 18 directions, keeping only those directions moves COMET-22 by less than half a point (× 100), but the judge and hard-case pillars of such a system also rest on fewer items.
