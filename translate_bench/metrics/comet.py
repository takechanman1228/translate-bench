"""COMET-22 as in the release: Unbabel/wmt22-comet-da at a pinned revision, on CPU, batch size 4.

An item is scored only when its source, reference and translation each fit in 512 XLM-R tokens
(special tokens included); longer items stay in the coverage denominator without a score.
Install with: python -m pip install -e '.[comet]'
"""

import hashlib
from pathlib import Path

from translate_bench.metrics import require

MODEL = "Unbabel/wmt22-comet-da"
REVISION = "2760a223ac957f30acfb18c8aa649b01cf1d75f2"
CHECKPOINT_SHA256 = "e213091cde220f97b89f8bdfa750c458cfea741ad62affb455b59900210ff2af"
TOKENIZER = "xlm-roberta-large"
TOKENIZER_REVISION = "c23d21b0620b635a76227c604d44e43a9f0ee389"
PACKAGE = "unbabel-comet==2.2.7"
MAX_TOKENS = 512


def versions():
    from importlib.metadata import version

    return dict(comet_model=MODEL, comet_revision=REVISION, comet_checkpoint_sha256=CHECKPOINT_SHA256,
                tokenizer=TOKENIZER, tokenizer_revision=TOKENIZER_REVISION,
                unbabel_comet=version("unbabel-comet"), torch=version("torch"), transformers=version("transformers"))


def _tokenizer_dir():
    from huggingface_hub import snapshot_download

    return snapshot_download(TOKENIZER, revision=TOKENIZER_REVISION,
                             allow_patterns=["config.json", "sentencepiece.bpe.model", "tokenizer*.json"])


def eligible(triples):
    """Indices of (source, reference, translation) triples within the 512-token limit."""
    require(["transformers", "huggingface_hub"], "comet")
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(_tokenizer_dir())
    keep = []
    for i, (source, reference, translation) in enumerate(triples):
        lengths = tokenizer([source, reference, translation], truncation=False, verbose=False)["input_ids"]
        if max(map(len, lengths)) <= MAX_TOKENS:
            keep.append(i)
    return keep


def scores(triples):
    """COMET-22 for each (source, reference, translation) triple."""
    require(["comet", "torch", "transformers", "huggingface_hub"], "comet")
    import torch
    from comet.models import RegressionMetric
    from huggingface_hub import hf_hub_download

    if not triples:
        return []
    checkpoint = hf_hub_download(MODEL, "checkpoints/model.ckpt", revision=REVISION)
    with Path(checkpoint).open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != CHECKPOINT_SHA256:
            raise ValueError("The COMET-22 checkpoint differs from the pinned SHA-256")
    torch.set_num_threads(4)
    model = RegressionMetric.load_from_checkpoint(
        checkpoint, map_location="cpu", pretrained_model=_tokenizer_dir(),
        load_pretrained_weights=False, local_files_only=True, strict=False)
    data = [{"src": s, "ref": r, "mt": t} for s, r, t in triples]
    return [float(x) for x in model.predict(data, batch_size=4, gpus=0, accelerator="cpu", num_workers=1,
                                            progress_bar=False).scores]
