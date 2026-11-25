# Limitations

- **No human ratings.** The judge is one language model, Claude Fable 5.2, and it also rates the Claude systems, including its own translations. Its sample of 8 items per direction and text type is too small for results by direction.
- **Local and cloud systems ran under different conditions.** Local models received one item per request at 4-bit quantization. Cloud models ran through their vendors' subscription clients at medium reasoning effort, with up to 25 sentences or 5 passages per request, so their time and cost are not comparable with local medians.
- **One machine.** All local speed and memory figures come from one Apple M6 with 32 GiB of memory. Peak process memory is not the RAM a machine needs.
- **Apple's on-device memory is not measured.** Those systems run in system services, outside any process the benchmark can sample.
- **Into English, NTREX sources are translations.** In those directions the source is NTREX's human translation of English news, and the English original is the reference.
- **Passages differ by direction.** In the twelve directions without Japanese, Chinese or Spanish, 14 of the 20 passages are speech transcripts. A difference between directions can reflect genre as well as language.
- **A small test set.** 200 sentences and 20 passages per direction resolve small differences over all 18 directions, but often not within one direction.
- **Public test sets.** The benchmark does not check whether a model was trained on them.
