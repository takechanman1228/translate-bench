"""MetricX-24 hybrid (large), with and without the reference, as in the release.

Lower is better (0–25). The checkpoint has the mT5 layout of the official MT5ForRegression and
loads as MT5ForConditionalGeneration; the score is the logit of token 250089 at the first decoder
step, clipped to 0–25. Inputs are "source: … candidate: … reference: …" (reference-based) and
"source: … candidate: …" (quality estimation), encoded with the raw mT5 SentencePiece model,
without an end-of-sequence token, and cut to 1,535 tokens (the official limit of 1,536 less that
token). The weights and the SentencePiece model are pinned by revision and SHA-256 and checked
before scoring. Tokenization differs from the official fast tokenizer on rare inputs; see the
protocol. Install with: python -m pip install -e '.[metricx]'
"""

import hashlib
from pathlib import Path

from translate_bench.metrics import require

MODEL = "google/metricx-24-hybrid-large-v2p6"
REVISION = "51e875ba5c525c81627cfd135ee10f43c87dce00"
WEIGHTS = "pytorch_model.bin"
WEIGHTS_SHA256 = "f584e231b25a20d7766f03fa464d0b990e235b8514a3de2034002132c04a2878"
SPIECE = "google/mt5-xl"
SPIECE_REVISION = "63fc6450d80515b48e026b69ef2fbbd426433e84"
SPIECE_FILE = "spiece.model"
SPIECE_SHA256 = "ef78f86560d809067d12bac6c09f19a462cb3af3f54d2b8acbba26e1433125d6"
MAX_TOKENS = 1535
SCORE_TOKEN = 250089
CLIP = (0.0, 25.0)


def _verified(repo, name, revision, expected):
    from huggingface_hub import hf_hub_download

    path = Path(hf_hub_download(repo, name, revision=revision))
    with path.open("rb") as stream:  # the bytes, not the cache's file name
        if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
            raise ValueError(f"{repo}/{name} differs from the pinned SHA-256")
    return path


def versions():
    return dict(metricx_model=MODEL, metricx_revision=REVISION, metricx_weights_sha256=WEIGHTS_SHA256,
                metricx_tokenizer=SPIECE, metricx_tokenizer_revision=SPIECE_REVISION,
                metricx_tokenizer_sha256=SPIECE_SHA256)


def scores(pairs, with_reference=True, device=None):
    """MetricX-24 for (source, translation[, reference]) tuples."""
    require(["torch", "transformers", "sentencepiece", "huggingface_hub"], "metricx")
    import sentencepiece as spm
    import torch
    from transformers import MT5ForConditionalGeneration

    if not pairs:
        return []
    _verified(MODEL, WEIGHTS, REVISION, WEIGHTS_SHA256)
    sp = spm.SentencePieceProcessor(model_file=str(_verified(SPIECE, SPIECE_FILE, SPIECE_REVISION, SPIECE_SHA256)))
    device = device or ("mps" if torch.backends.mps.is_available() else "cpu")
    model = MT5ForConditionalGeneration.from_pretrained(MODEL, revision=REVISION, use_safetensors=False,
                                                        torch_dtype=torch.float32).to(device).eval()
    texts = [f"source: {p[0]} candidate: {p[1]}" + (f" reference: {p[2]}" if with_reference else "") for p in pairs]
    encoded = sorted(((i, sp.encode(t)[:MAX_TOKENS]) for i, t in enumerate(texts)), key=lambda x: len(x[1]))
    out = [None] * len(texts)
    i = 0
    while i < len(encoded):
        size = max(1, min(64, 6000 // max(len(encoded[i][1]), 1)))
        batch = encoded[i:i + size]
        i += size
        width = max(len(x[1]) for x in batch)
        ids = torch.tensor([x[1] + [0] * (width - len(x[1])) for x in batch], device=device)
        mask = torch.tensor([[1] * len(x[1]) + [0] * (width - len(x[1])) for x in batch], device=device)
        start = torch.zeros((len(batch), 1), dtype=torch.long, device=device)
        with torch.no_grad():
            logits = model(input_ids=ids, attention_mask=mask, decoder_input_ids=start).logits[:, 0, SCORE_TOKEN]
        for (index, _), value in zip(batch, logits.clamp(*CLIP).tolist()):
            out[index] = float(value)
    return out
