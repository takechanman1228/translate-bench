# Reading the metrics

Translate Bench reports several quality measures side by side and does not combine them. Near the top of the leaderboard they disagree on the order.

## The measures

| Measure | What it is | Scale |
| --- | --- | --- |
| **COMET-22** | A learned model (`Unbabel/wmt22-comet-da`) reads the source, the output and a human reference and predicts a quality score. | Higher is better |
| **MetricX-24** | A second learned metric (`google/metricx-24-hybrid-large-v2p6`), trained to predict error severity. *QE* is its score without the reference. | 0–25, lower is better |
| **Judge vs DeepL API** | A language model sees the source and two translations, blind, and picks the better one or calls a tie. | Share of non-tied items won against DeepL API |
| **Error-free** | The same language model counts mistranslations, omissions and wrong names or numbers in one translation, ignoring style. | Share of items with no error |
| **chrF++** | Character and word n-gram overlap with the reference. | 0–100, higher is better |
| **Completion** | Items that came back with a translation, of those attempted. | Share of items |

The two judge measures use a fixed sample of 288 items. The others use every item.

## Why they disagree

**Reference-based metrics reward closeness to one human translation.** A translation that conveys the meaning in other words can score below one that follows the reference's wording.

**The two learned metrics weigh errors differently.** MetricX-24 penalises some outputs that COMET-22 scores well. 28 of the 149,918 scored outputs return the source unchanged, and COMET-22 scored 10 of them above at least one real translation of the same item. MetricX-24 scored all 28 worse than every real translation of their item.

<!-- tb:passages -->
On the passages, MetricX-24 scores 6 systems better than every GPT, Claude and Gemini system with all 18 directions (the best of those, GPT-6.1 Terra, scores 4.855): Hy-MT2 30B-A3B (4.550), Hy-MT2 7B (4.558), DeepL API (4.611), TranslateGemma 27B (4.745), Index-Translate 9B (4.806), Index-Translate 35B-A3B preview (4.827). On single sentences the order turns: Claude Fable 5.2 (1.933) is ahead of all 6.
<!-- /tb:passages -->

**The judge reads the translations without a reference.** It can credit a correct rendering that the reference phrased differently. It also catches omissions and wrong names that a reference-based score can average away.

## How closely the orders agree

Spearman rank correlation between the measures, over the systems with both text types in all 18 directions:

<!-- tb:correlations -->
| | COMET-22 | MetricX-24 | MetricX-24 QE | chrF++ | Judge vs DeepL API | Error-free |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| COMET-22 | 1.00 | 0.81 | 0.37 | 0.82 | 0.90 | 0.92 |
| MetricX-24 | 0.81 | 1.00 | 0.76 | 0.54 | 0.67 | 0.66 |
| MetricX-24 QE | 0.37 | 0.76 | 1.00 | 0.09 | 0.15 | 0.16 |
| chrF++ | 0.82 | 0.54 | 0.09 | 1.00 | 0.82 | 0.88 |
| Judge vs DeepL API | 0.90 | 0.67 | 0.15 | 0.82 | 1.00 | 0.97 |
| Error-free | 0.92 | 0.66 | 0.16 | 0.88 | 0.97 | 1.00 |

31 systems (19 local, 12 cloud). The judge column leaves out DeepL API itself (30 systems). 1.00 means the same order.
<!-- /tb:correlations -->

## Reading a paired interval

Two systems are compared by the paired 95% interval of their difference, computed on the items both translated. When the interval includes zero, the two systems are tied, and this test set does not resolve their order. Many of the leading systems are within a few thousandths of COMET-22 of each other and tied.
