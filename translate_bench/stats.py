"""Corpus scores and the paired document bootstrap of the release.

Resampling unit. An item belongs to a source document (`doc` in the item rows): an NTREX
news article for sentences, a WMT document for passages. One document can appear in
many cells, for example the same English article in all 18 directions, or one WMT24++
document in the twelve directions outside the core. A document gets one multiplicity
per draw and keeps it in every cell it appears in, so all directions and both text types
are resampled jointly. Documents are drawn with replacement within strata of documents
that cover the same set of cells.

The release used 2,000 draws from a NumPy PCG64 generator seeded with the first eight
bytes of SHA-256("site-v2"), a historical seed string kept so the published intervals
can be recomputed exactly. Strata are visited in a fixed order, given by STRATUM_ORDER
and the direction written with an arrow, which is the order of the release's own cell
labels. Changing either changes every interval.
"""

import hashlib
from collections import defaultdict

import numpy as np

from translate_bench.schema import parse_direction

SEED = "site-v2"
DRAWS = 2000
# Cell kinds in the order the release sorted them: the twelve-passage set, the eight-passage set,
# the core passages, then sentences.
STRATUM_ORDER = {"set-12": 0, "set-8": 1, "passage": 2, "sentence": 3}


def stratum_cell(kind, direction):
    """Sort key of one cell for the stratum order (see the module docstring)."""
    src, tgt = parse_direction(direction)
    return STRATUM_ORDER[kind], f"{src}→{tgt}"


def document_draws(coverage, seed=SEED, draws=DRAWS):
    """Yield (sorted documents, draw indices) per stratum; `coverage` maps doc -> set of cell keys."""
    strata = defaultdict(list)
    for doc, cells in coverage.items():
        strata[tuple(sorted(cells))].append(doc)
    rng = np.random.default_rng(int.from_bytes(hashlib.sha256(seed.encode()).digest()[:8], "big"))
    for _, docs in sorted(strata.items()):
        docs.sort()
        yield docs, rng.integers(0, len(docs), size=(draws, len(docs)))


def multiplicities(coverage, seed=SEED, draws=DRAWS):
    """doc -> integer array of length draws + 1: 1 for the point estimate, then the count in each draw."""
    result = {}
    for docs, index in document_draws(coverage, seed, draws):
        for j, doc in enumerate(docs):
            result[doc] = np.concatenate([[1], (index == j).sum(axis=1)])
    return result


def score_draws(items, block):
    """COMET-22 mean and corpus chrF++ for each row of `block` (draws x items weights).

    `items` are (doc, comet, chrf_stats) tuples. chrF++ is sacreBLEU's CHRF(word_order=2),
    beta 2, with effective orders, computed from pooled sufficient statistics."""
    with np.errstate(invalid="ignore", divide="ignore"):  # a draw without any of the items is set to NaN later
        comet = block @ np.array([x[1] for x in items], dtype=float) / block.sum(axis=1)
    stats = block @ np.array([x[2] for x in items], dtype=float)
    hyp, ref, match = (stats[:, i::3] for i in range(3))
    valid = (hyp > 0) & (ref > 0)
    orders = valid.sum(axis=1).clip(min=1)
    precision = (match / hyp.clip(min=1) * valid).sum(axis=1) / orders
    recall = (match / ref.clip(min=1) * valid).sum(axis=1) / orders
    denom = 4 * precision + recall
    chrf = np.divide(500 * precision * recall, denom, out=np.zeros_like(comet), where=denom > 0)
    return np.array([comet, chrf])


def corpus_scores(items):
    """(COMET-22 mean, corpus chrF++) of a list of (doc, comet, chrf_stats) tuples."""
    (comet,), (chrf,) = score_draws(items, np.ones((1, len(items))))
    return float(comet), float(chrf)


def interval(values):
    """[point, 2.5th percentile, 97.5th percentile] of draws whose first entry is the point estimate."""
    if not np.isfinite(values[0]):
        return None
    return [float(values[0]), *map(float, np.nanquantile(values[1:], [0.025, 0.975]))]


class Draws:
    """Cached score draws of one system's eligible items in one cell, on a given ID set."""

    def __init__(self, cells, weights):
        # cells: {system: {(type, direction): {id: (doc, comet, stats)}}}
        self.cells, self.weights, self.cache = cells, weights, {}

    def __call__(self, system, key, ids):
        token = (system, key, ids)
        if token not in self.cache:
            items = self.cells[system][key]
            rows = [items[i] for i in sorted(ids)]
            try:
                block = np.stack([self.weights[r[0]] for r in rows], axis=1).astype(float)
            except KeyError as exc:
                raise ValueError(f"Document {exc.args[0]!r} is not part of the release") from None
            values = score_draws(rows, block)
            values[:, block.sum(axis=1) == 0] = np.nan  # a draw without any of these documents
            self.cache[token] = values
        return self.cache[token]

    def pair(self, keys, a, b):
        """Paired a - b draws on common IDs: mean over directions of the mean over each direction's types.

        Returns (draws of shape (2, draws + 1) for COMET-22 and chrF++, number of paired items),
        or (None, 0) if some cell has no common item."""
        by_direction = defaultdict(list)
        n = 0
        for key in keys:
            sa, sb = frozenset(self.cells[a][key]), frozenset(self.cells[b][key])
            common = sa if sa == sb else sa & sb
            if not common:
                return None, 0
            n += len(common)
            by_direction[key[1]].append(self(a, key, common) - self(b, key, common))
        values = [v[0] if len(v) == 1 else np.mean(v, axis=0) for v in by_direction.values()]
        return np.mean(values, axis=0), n
