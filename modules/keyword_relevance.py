"""Per-keyword relevance weighting from model similarity scores.

``image_keywords`` carries two distinct per-tag signals:

* ``confidence`` — the assigning model's raw confidence (e.g. CLIP softmax
  probability over the candidate keyword set, or a species classifier prob).
* ``relevance_weight`` — a *stable* per-keyword importance score in ``(0, 1)``
  used for ranking / filtering / propagation. Unlike softmax, it must not
  depend on how many candidate keywords were scored alongside it, so it is
  derived from the raw cosine similarity between the image embedding and the
  keyword's text embedding rather than from the softmax distribution.

This module owns the single transform shared by the forward-fill path
(``modules.tagging``) and the backfill script
(``scripts/db/backfill_keyword_relevance.py``) so both agree on calibration.
"""

from __future__ import annotations

import math

# Temperature for the sigmoid mapping raw cosine similarity -> (0, 1).
#
# CLIP image/text cosine similarity for a relevant "a photo of {kw}" prompt
# typically lands around 0.20-0.35 (and lower for irrelevant prompts). Dividing
# by this temperature before the sigmoid spreads that band across a useful
# portion of (0, 1): cos=0.30 -> ~0.69, cos=0.20 -> ~0.62, cos=0.10 -> ~0.55.
# Pinned here so forward-fill and backfill produce identical weights for the
# same cosine. Re-calibrate deliberately (and re-run the backfill) if changed.
RELEVANCE_SIGMOID_TEMPERATURE = 0.18


def cosine_to_relevance(
    cosine: float, temperature: float = RELEVANCE_SIGMOID_TEMPERATURE
) -> float:
    """Map a raw cosine similarity to a relevance weight in ``(0, 1)``.

    ``cosine`` is the true image/text cosine similarity (``logits_per_image``
    divided by the model's ``logit_scale``), expected roughly in ``[-1, 1]``.
    Returns ``1 / (1 + exp(-cosine / temperature))``, clamped to ``(0, 1)``.
    """
    try:
        cos = float(cosine)
    except (TypeError, ValueError):
        return 1.0
    if not math.isfinite(cos):
        return 1.0
    if temperature <= 0:
        temperature = RELEVANCE_SIGMOID_TEMPERATURE
    # Guard against overflow in exp() for extreme inputs.
    x = cos / temperature
    if x >= 0:
        z = math.exp(-x)
        value = 1.0 / (1.0 + z)
    else:
        z = math.exp(x)
        value = z / (1.0 + z)
    # Keep strictly inside (0, 1) so NOT NULL DOUBLE rows never store 0/1 edges
    # that downstream callers might treat as "unset".
    return min(1.0 - 1e-6, max(1e-6, value))
