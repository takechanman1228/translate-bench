"""Corpus chrF++ as in the release: sacreBLEU 2.5.1, CHRF(word_order=2), pooled sufficient statistics."""

import hashlib

from sacrebleu.metrics import CHRF

SACREBLEU_VERSION = "2.5.1"
SIGNATURE = "nrefs:1|case:mixed|eff:yes|nc:6|nw:2|space:no|version:2.5.1"


def metric():
    return CHRF(word_order=2)


def statistics(chrf, hypothesis, reference):
    """The 24 sufficient statistics of one segment: (hypothesis, reference, match) counts for character
    n-grams 1–6 and word n-grams 1–2."""
    (stats,) = chrf._extract_corpus_statistics([hypothesis], [[reference]])
    return [int(x) for x in stats]


def signature(chrf=None):
    """sacreBLEU's reproducibility signature (one reference per segment)."""
    return str(CHRF(word_order=2, references=[["."]]).get_signature())


def output_sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
