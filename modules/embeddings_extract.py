"""Piggyback embedding extractors for models already running in other phases.

These helpers do **not** touch the database. They take objects (or tensors /
outputs) the caller has on hand inside the existing forward pass, and return a
1-D ``float32`` ``numpy.ndarray`` that is L2-normalized so cosine distance
behaves consistently across callers.

See ``docs/technical/EMBEDDINGS.md`` for the registry contract and
``modules/embedding_spaces.py`` for per-code dimensions (must agree with what
this module produces).
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


def _to_float32_np(t: Any) -> np.ndarray:
    """Detach a torch tensor or convert any array-like to float32 numpy."""
    try:
        import torch

        if isinstance(t, torch.Tensor):
            return t.detach().to(dtype=torch.float32).cpu().numpy()
    except Exception:
        pass
    return np.asarray(t, dtype=np.float32)


def l2_normalize(vec: np.ndarray) -> np.ndarray:
    """L2-normalize a 1-D vector; zero-vectors are returned unchanged."""
    arr = np.asarray(vec, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(arr))
    if norm == 0.0 or not np.isfinite(norm):
        return arr
    return arr / norm


def extract_clip_image_features_from_outputs(outputs: Any) -> np.ndarray | None:
    """Return a 512-d L2-normalized image embedding from a CLIPModel output.

    Expects ``outputs.image_embeds`` with shape ``(1, 512)`` (single image).
    Returns ``None`` if the output does not carry image embeddings.
    """
    image_embeds = getattr(outputs, "image_embeds", None)
    if image_embeds is None:
        return None
    arr = _to_float32_np(image_embeds).reshape(-1)
    if arr.size == 0:
        return None
    return l2_normalize(arr)


def extract_blip_image_features(blip_model: Any, pixel_values: Any) -> np.ndarray | None:
    """Return a 768-d L2-normalized pooler_output from the BLIP vision encoder.

    ``blip_model`` is a ``BlipForConditionalGeneration`` instance; the caller
    supplies already-preprocessed ``pixel_values`` (as produced by ``BlipProcessor``).
    This runs an extra forward pass through the vision tower alone — cheap but
    not free; callers should gate it behind a config flag.
    """
    try:
        import torch

        vision_model = getattr(blip_model, "vision_model", None)
        if vision_model is None:
            return None
        with torch.no_grad():
            out = vision_model(pixel_values=pixel_values)
        pooler = getattr(out, "pooler_output", None)
        if pooler is None:
            last = getattr(out, "last_hidden_state", None)
            if last is None:
                return None
            pooler = last[:, 0, :]
        arr = _to_float32_np(pooler).reshape(-1)
        if arr.size == 0:
            return None
        return l2_normalize(arr)
    except Exception as e:
        logger.warning("BLIP image feature extraction failed: %s", e)
        return None


def extract_bioclip_image_features(img_features: Any) -> np.ndarray | None:
    """Return a 768-d L2-normalized image embedding from BioCLIP 2 ``encode_image``.

    BioCLIP 2 (ViT-L/14, ``hf-hub:imageomics/bioclip-2``) outputs 768 dimensions.
    ``img_features`` is the tensor already computed by
    ``open_clip_model.encode_image(img_tensor)``; this helper only reshapes,
    converts, and L2-normalizes. It does not run additional inference.
    """
    if img_features is None:
        return None
    arr = _to_float32_np(img_features).reshape(-1)
    if arr.size == 0:
        return None
    return l2_normalize(arr)
