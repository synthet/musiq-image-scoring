"""
Generate IPTC accessibility metadata (Alt Text, Extended Description) from CLIP.

Uses cosine similarity between a stored or freshly computed CLIP image embedding
and a bank of descriptive text prompts (CLIP-interrogator style). Does not use
BLIP; Title/Caption remain the captioning model's job in tagging.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import numpy as np

from modules import config, db
from modules.embedding_spaces import CLIP_IMAGE_DIM, CLIP_IMAGE_SPACE_CODE, get_embedding_space_id
from modules.embeddings_extract import l2_normalize

logger = logging.getLogger(__name__)

_DEFAULT_PROMPTS_REL = Path("data") / "clip_accessibility_prompts.txt"
_PROMPT_CACHE: list[str] | None = None
_TEXT_EMB_CACHE: dict[tuple[str, ...], np.ndarray] = {}

_PHOTO_PREFIXES = (
    "a photo of ",
    "a photograph of ",
    "a picture of ",
    "an image of ",
    "a close-up photograph of ",
    "a close-up photo of ",
)


def _tagging_cfg() -> dict:
    return config.get_config_section("tagging") or {}


def _default_prompts_path() -> Path:
    rel = _tagging_cfg().get("accessibility_prompts_file") or str(_DEFAULT_PROMPTS_REL)
    p = Path(rel)
    if not p.is_absolute():
        from modules.config import BASE_DIR

        p = BASE_DIR / p
    return p


def load_prompt_bank(path: Path | str | None = None) -> list[str]:
    """Load descriptive prompts from a text file (comments and blank lines skipped)."""
    global _PROMPT_CACHE
    if path is None and _PROMPT_CACHE is not None:
        return _PROMPT_CACHE

    file_path = Path(path) if path is not None else _default_prompts_path()
    if not file_path.is_file():
        logger.warning("CLIP accessibility prompts file not found: %s", file_path)
        return []

    prompts: list[str] = []
    with open(file_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            prompts.append(line)

    if path is None:
        _PROMPT_CACHE = prompts
    logger.info("Loaded %d CLIP accessibility prompts from %s", len(prompts), file_path)
    return prompts


def get_stored_clip_embedding(image_id: int) -> np.ndarray | None:
    """Return L2-normalized 512-d CLIP vector from Postgres, or None."""
    if not image_id or db._get_db_engine() != "postgres":
        return None
    space_id = get_embedding_space_id(CLIP_IMAGE_SPACE_CODE)
    if space_id is None:
        return None
    try:
        with db.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT embedding FROM image_embeddings_512 "
                "WHERE image_id = %s AND embedding_space_id = %s",
                (image_id, space_id),
            )
            row = cur.fetchone()
        if not row or row[0] is None:
            return None
        raw = row[0]
        if hasattr(raw, "tobytes"):
            vec = np.frombuffer(raw.tobytes(), dtype=np.float32)
        else:
            vec = np.asarray(raw, dtype=np.float32).reshape(-1)
        if vec.size != CLIP_IMAGE_DIM:
            logger.warning(
                "CLIP embedding dim mismatch for image_id=%s: expected %d, got %d",
                image_id,
                CLIP_IMAGE_DIM,
                vec.size,
            )
            return None
        return l2_normalize(vec)
    except Exception as e:
        logger.warning("Failed to load CLIP embedding for image_id=%s: %s", image_id, e)
        return None


def _batch_clip_text_embeddings(prompts: list[str], chunk_size: int = 64) -> np.ndarray:
    """Encode prompts with CLIP text tower → (N, 512) L2-normalized rows."""
    import torch
    from transformers import CLIPModel, CLIPProcessor

    if not prompts:
        return np.zeros((0, CLIP_IMAGE_DIM), dtype=np.float32)

    cache_key = tuple(prompts)
    if cache_key in _TEXT_EMB_CACHE:
        return _TEXT_EMB_CACHE[cache_key]

    tagging_cfg = _tagging_cfg()
    model_name = tagging_cfg.get("clip_model", "openai/clip-vit-base-patch32")
    device = "cuda" if torch.cuda.is_available() else "cpu"

    model = CLIPModel.from_pretrained(model_name).to(device)
    processor = CLIPProcessor.from_pretrained(model_name)
    model.eval()

    rows: list[np.ndarray] = []
    with torch.no_grad():
        for start in range(0, len(prompts), chunk_size):
            batch = prompts[start : start + chunk_size]
            inputs = processor(text=batch, return_tensors="pt", padding=True, truncation=True)
            inputs = {k: v.to(device) for k, v in inputs.items()}
            out = model.get_text_features(**inputs)
            feats = out
            if not hasattr(feats, "cpu"):
                if hasattr(out, "text_embeds") and out.text_embeds is not None:
                    feats = out.text_embeds
                elif hasattr(out, "pooler_output") and out.pooler_output is not None:
                    feats = out.pooler_output
            arr = feats.detach().cpu().numpy().astype(np.float32)
            for i in range(arr.shape[0]):
                rows.append(l2_normalize(arr[i]))

    mat = np.stack(rows, axis=0)
    if len(_TEXT_EMB_CACHE) > 4:
        _TEXT_EMB_CACHE.clear()
    _TEXT_EMB_CACHE[cache_key] = mat
    return mat


def _rank_prompts_by_embedding(
    image_emb: np.ndarray,
    prompts: list[str],
) -> list[tuple[str, float]]:
    """Cosine similarity rank (both vectors L2-normalized)."""
    text_mat = _batch_clip_text_embeddings(prompts)
    if text_mat.shape[0] == 0:
        return []
    img = l2_normalize(np.asarray(image_emb, dtype=np.float32).reshape(-1))
    sims = text_mat @ img
    order = np.argsort(-sims)
    return [(prompts[int(i)], float(sims[int(i)])) for i in order]


def _rank_prompts_from_image_path(
    image_path: str,
    prompts: list[str],
    scorer: Any | None = None,
) -> tuple[np.ndarray | None, list[tuple[str, float]]]:
    """Run CLIP image+text forward pass; return image embedding and ranked prompts."""
    import torch

    from modules.thumbnails import open_image_for_ml

    if scorer is not None:
        scorer.load_model()
        model = scorer.model
        processor = scorer.processor
        device = scorer.device
    else:
        from modules.tagging import KeywordScorer

        scorer = KeywordScorer()
        scorer.load_model()
        model = scorer.model
        processor = scorer.processor
        device = scorer.device

    image = open_image_for_ml(image_path)
    inputs = processor(text=prompts, images=image, return_tensors="pt", padding=True, truncation=True)
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.no_grad():
        outputs = model(**inputs)

    from modules.embeddings_extract import extract_clip_image_features_from_outputs

    image_emb = extract_clip_image_features_from_outputs(outputs)
    if image_emb is None:
        return None, []

    logits = outputs.logits_per_image[0].detach().cpu().numpy()
    order = np.argsort(-logits)
    ranked = [(prompts[int(i)], float(logits[int(i)])) for i in order]
    return image_emb, ranked


def _clean_prompt_text(prompt: str) -> str:
    text = prompt.strip()
    lower = text.lower()
    for prefix in _PHOTO_PREFIXES:
        if lower.startswith(prefix):
            text = text[len(prefix) :].strip()
            break
    if text:
        text = text[0].upper() + text[1:]
    return text


def compose_alt_text(
    ranked: list[tuple[str, float]],
    *,
    top_k: int | None = None,
    max_chars: int | None = None,
) -> str:
    cfg = _tagging_cfg()
    top_k = top_k if top_k is not None else int(cfg.get("accessibility_top_k_alt", 2))
    max_chars = max_chars if max_chars is not None else int(cfg.get("alt_text_max_chars", 200))

    parts: list[str] = []
    for prompt, _score in ranked[: max(1, top_k)]:
        cleaned = _clean_prompt_text(prompt)
        if cleaned and cleaned not in parts:
            parts.append(cleaned)
    if not parts:
        return ""

    text = ". ".join(parts)
    if not text.endswith("."):
        text += "."
    if len(text) > max_chars:
        trimmed = text[: max_chars - 3].rsplit(" ", 1)[0]
        text = trimmed + "..."
    return text


def compose_extended_description(
    ranked: list[tuple[str, float]],
    *,
    keywords: list[str] | None = None,
    top_k: int | None = None,
    max_chars: int | None = None,
) -> str:
    cfg = _tagging_cfg()
    top_k = top_k if top_k is not None else int(cfg.get("accessibility_top_k_extended", 5))
    max_chars = max_chars if max_chars is not None else int(cfg.get("extended_max_chars", 1000))

    sentences: list[str] = []
    for prompt, _score in ranked[: max(1, top_k)]:
        cleaned = _clean_prompt_text(prompt)
        if cleaned:
            sentences.append(cleaned if cleaned.endswith(".") else cleaned + ".")

    if keywords:
        kw_line = "Keywords: " + ", ".join(kw.strip() for kw in keywords if kw and kw.strip()) + "."
        if kw_line != "Keywords: .":
            sentences.append(kw_line)

    text = " ".join(sentences)
    if len(text) > max_chars:
        trimmed = text[: max_chars - 3].rsplit(" ", 1)[0]
        text = trimmed + "..."
    return text


def existing_accessibility_fields(image_path: str, image_id: int | None = None) -> dict[str, str | None]:
    """Return current alt_text / extended_description from XMP sidecar or DB cache."""
    from modules import xmp

    alt = None
    extended = None
    if image_path and xmp.xmp_exists(image_path):
        data = xmp.read_xmp_full(image_path)
        alt = (data.get("alt_text") or "").strip() or None
        extended = (data.get("extended_description") or "").strip() or None
    if image_id and (alt is None or extended is None):
        row = db.get_image_xmp(image_id) or {}
        if alt is None:
            alt = (row.get("alt_text") or "").strip() or None
        if extended is None:
            extended = (row.get("extended_description") or "").strip() or None
    return {"alt_text": alt, "extended_description": extended}


def describe_from_clip(
    *,
    image_id: int | None = None,
    image_path: str | None = None,
    keywords: list[str] | None = None,
    scorer: Any | None = None,
    prompts: list[str] | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """
    Build Alt Text and Extended Description from CLIP prompt ranking.

    Returns dict with alt_text, extended_description, top_prompts (list of
    {prompt, score}), and optional error key.
    """
    prompts = prompts if prompts is not None else load_prompt_bank()
    if not prompts:
        return {"error": "No accessibility prompts loaded", "alt_text": "", "extended_description": ""}

    if image_path:
        existing = existing_accessibility_fields(image_path, image_id)
        if not overwrite and existing.get("alt_text") and existing.get("extended_description"):
            return {
                "alt_text": existing["alt_text"],
                "extended_description": existing["extended_description"],
                "skipped": True,
                "reason": "existing_accessibility_metadata",
            }

    ranked: list[tuple[str, float]] = []
    image_emb = get_stored_clip_embedding(image_id) if image_id else None

    if image_emb is not None:
        ranked = _rank_prompts_by_embedding(image_emb, prompts)
    elif image_path:
        image_emb, ranked = _rank_prompts_from_image_path(image_path, prompts, scorer=scorer)
    else:
        return {"error": "image_id or image_path required", "alt_text": "", "extended_description": ""}

    if not ranked:
        return {"error": "CLIP prompt ranking produced no results", "alt_text": "", "extended_description": ""}

    alt_text = compose_alt_text(ranked)
    extended = compose_extended_description(ranked, keywords=keywords)

    top_prompts = [{"prompt": p, "score": round(s, 4)} for p, s in ranked[:10]]
    return {
        "alt_text": alt_text,
        "extended_description": extended,
        "top_prompts": top_prompts,
    }
