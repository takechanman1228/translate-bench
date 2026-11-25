import random
import unittest

import numpy as np
from sacrebleu.metrics import CHRF

from translate_bench import stats
from translate_bench.metrics import chrf as chrf_metric

SENTENCES = [
    ("The committee approved the plan on Tuesday.", "On Tuesday the committee approved the plan."),
    ("Rain is expected in the north.", "Rain is forecast for the northern regions."),
    ("She left before the meeting ended.", "She departed before the end of the meeting."),
    ("Prices rose by three percent.", "Prices increased three per cent."),
]


class ChrfTest(unittest.TestCase):
    def test_pooled_statistics_equal_sacrebleu(self):
        metric = chrf_metric.metric()
        items = [("doc", 0.5, chrf_metric.statistics(metric, h, r)) for h, r in SENTENCES]
        _, ours = stats.corpus_scores(items)
        theirs = CHRF(word_order=2).corpus_score([h for h, _ in SENTENCES], [[r for _, r in SENTENCES]]).score
        self.assertAlmostEqual(ours, theirs, places=9)

    def test_signature(self):
        self.assertEqual(chrf_metric.signature(chrf_metric.metric()), chrf_metric.SIGNATURE)


class BootstrapTest(unittest.TestCase):
    def coverage(self):
        rng = random.Random(1)
        return {f"doc{i}": {stats.stratum_cell(rng.choice(["sentence", "passage"]), rng.choice(["en-ja", "ko-en"]))}
                for i in range(30)}

    def test_deterministic(self):
        a = stats.multiplicities(self.coverage())
        b = stats.multiplicities(self.coverage())
        self.assertEqual(a.keys(), b.keys())
        for doc in a:
            self.assertTrue(np.array_equal(a[doc], b[doc]))
            self.assertEqual(a[doc][0], 1)
            self.assertEqual(len(a[doc]), stats.DRAWS + 1)

    def test_draw_sizes_match_strata(self):
        coverage = self.coverage()
        weights = stats.multiplicities(coverage)
        strata = {}
        for doc, cells in coverage.items():
            strata.setdefault(tuple(sorted(cells)), []).append(doc)
        for docs in strata.values():
            totals = sum(weights[d][1:] for d in docs)
            self.assertTrue(np.all(totals == len(docs)))  # each stratum keeps its size in every draw

    def test_seed_changes_draws(self):
        coverage = self.coverage()
        a = stats.multiplicities(coverage, seed="site-v2")
        b = stats.multiplicities(coverage, seed="other")
        self.assertFalse(all(np.array_equal(a[d], b[d]) for d in a))

    def test_stratum_order(self):
        keys = [stats.stratum_cell(k, "en-ja") for k in ("sentence", "passage", "set-8", "set-12")]
        self.assertEqual(sorted(keys), [keys[3], keys[2], keys[1], keys[0]])

    def test_interval(self):
        values = np.concatenate([[0.5], np.linspace(0, 1, 2000)])
        point, low, high = stats.interval(values)
        self.assertEqual(point, 0.5)
        self.assertAlmostEqual(low, 0.025, places=3)
        self.assertAlmostEqual(high, 0.975, places=3)
        self.assertIsNone(stats.interval(np.array([np.nan, 1.0])))


if __name__ == "__main__":
    unittest.main()
