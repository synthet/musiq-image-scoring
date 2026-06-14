"""CLIP ViT-B/32 prompt-quality (``clip_quality_v0``) — auxiliary pick/reject signal.

Computes a 0–1 "good photo" score from the persisted ``clip_vit_b32_image`` (512-d)
embeddings and antonym text prompts (CLIP-IQA antonym softmax). This is an *auxiliary*
signal used as a low-weight within-stack tie-breaker in culling
(:mod:`modules.selection`) — never the primary quality model.

Benchmark and rationale: ``reports/clip-culling/prompt-quality/`` (B/32 wins; global
pick/reject AUC 0.89, within-stack concordance 0.986).

Tower-match (critical): the B/32 *image* embeddings (``KeywordScorer`` /
``embedding_extractors`` ``hf_clip`` loader) and the *text* tower
(:func:`modules.similar_search._get_clip_text_embedding`) use the same HF
``openai/clip-vit-base-patch32`` weights. Mixing image/text encoders silently
corrupts cosine similarity.

Postgres-only; a no-op on other engines. Scores persist to ``image_model_scores``
under ``model_name = "clip_quality_v0"``.
"""

from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)

CLIP_QUALITY_MODEL = "clip_quality_v0"
PROMPT_SET_VERSION = "v0"
# CLIP temperature for the antonym softmax (cosine margins are ~0.01–0.05, so a raw
# sigmoid(pos-neg) collapses to ~0.5; the logit scale gives a real 0–1 spread).
LOGIT_SCALE = 100.0

# Six caption templates; short adjectival phrases are expanded through all of them and
# averaged. Full captions (containing the verbatim tokens below) are used as-is.
TEMPLATES = (
    "a photo that is {phrase}",
    "a photograph that is {phrase}",
    "an image that is {phrase}",
    "a {phrase} photograph",
    "a {phrase} image",
    "this is a {phrase} photo",
)
_VERBATIM_TOKENS = ("photo", "photograph", "image", "bird", "wildlife", "subject")

# Positive / negative prompt banks for clip_quality_v0 (validated in the benchmark).
GOOD = [
    "high quality", "good", "beautiful", "sharp", "clear", "well focused",
    "properly exposed", "clean", "detailed", "professional", "well composed",
    "visually pleasing", "good lighting", "natural colors",
    "a photo with strong subject separation", "crisp details",
    "a photo with a clear subject", "balanced contrast", "good dynamic range",
    "a keeper photo",
]
BAD = [
    "low quality", "bad", "poor", "blurry", "out of focus", "misfocused",
    "overexposed", "underexposed", "noisy", "grainy", "soft", "dull",
    "washed out", "poorly composed", "a photo with no clear subject",
    "a missed shot", "a poorly timed photo", "technically flawed",
    "bad lighting", "a rejected photo",
]

# Process-cached text matrices: {"good": (P,512), "bad": (M,512)} L2-normalized.
_text_cache: dict[str, np.ndarray] = {}


def _l2_normalize(arr: np.ndarray) -> np.ndarray:
    arr = np.asarray(arr, dtype=np.float32)
    n = np.linalg.norm(arr, axis=-1, keepdims=True)
    n[n == 0] = 1.0
    return arr / n


def _is_verbatim(phrase: str) -> bool:
    p = phrase.lower()
    return any(tok in p for tok in _VERBATIM_TOKENS)


def _expand(phrase: str) -> list[str]:
    if _is_verbatim(phrase):
        return [phrase]
    return [t.format(phrase=phrase) for t in TEMPLATES]


def _encode_bank(phrases: list[str]) -> np.ndarray:
    """Encode each phrase (template-averaged) -> (n_phrases, 512) L2-normalized."""
    from modules.similar_search import _get_clip_text_embedding

    vecs = []
    for phrase in phrases:
        variants = _expand(phrase)
        per_variant = np.vstack([_get_clip_text_embedding(v) for v in variants])
        vecs.append(_l2_normalize(per_variant.mean(axis=0)))
    return np.vstack(vecs).astype(np.float32)


def _prompt_matrices() -> tuple[np.ndarray, np.ndarray]:
    """Return cached (good, bad) text matrices, encoding them on first use."""
    if "good" not in _text_cache:
        _text_cache["good"] = _encode_bank(GOOD)
        _text_cache["bad"] = _encode_bank(BAD)
        logger.info(
            "clip_quality: encoded prompt banks (good=%d, bad=%d phrases)",
            len(GOOD), len(BAD),
        )
    return _text_cache["good"], _text_cache["bad"]


def score_embeddings(img: np.ndarray, good: np.ndarray, bad: np.ndarray
                     ) -> tuple[np.ndarray, np.ndarray]:
    """Score L2-normalized image vectors against the prompt banks.

    Returns ``(margin, normalized)`` where ``margin = mean cos(img, good) -
    mean cos(img, bad)`` and ``normalized`` is the antonym softmax probability in
    ``[0, 1]`` at :data:`LOGIT_SCALE`.
    """
    img = _l2_normalize(img)
    pos_mean = (img @ good.T).mean(axis=1)
    neg_mean = (img @ bad.T).mean(axis=1)
    margin = pos_mean - neg_mean
    logits = np.stack([pos_mean, neg_mean], axis=1) * LOGIT_SCALE
    logits -= logits.max(axis=1, keepdims=True)
    e = np.exp(logits)
    normalized = e[:, 0] / e.sum(axis=1)
    return margin.astype(np.float32), normalized.astype(np.float32)


def _persist_scores(scored: list[tuple[int, float, float]], chunk: int = 500) -> int:
    """Batch-upsert (image_id, margin, normalized) into image_model_scores."""
    from modules import db_postgres

    written = 0
    cols = "(image_id, model_name, raw_score, normalized, status, is_shadow, model_version, scored_at)"
    for i in range(0, len(scored), chunk):
        batch = scored[i:i + chunk]
        values = ", ".join(
            ["(%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)"] * len(batch)
        )
        params: list = []
        for image_id, margin, norm in batch:
            params += [int(image_id), CLIP_QUALITY_MODEL, float(margin), float(norm),
                       "success", False, PROMPT_SET_VERSION]
        sql = (
            f"INSERT INTO image_model_scores {cols} VALUES {values} "
            "ON CONFLICT (image_id, model_name) DO UPDATE SET "
            "raw_score = EXCLUDED.raw_score, normalized = EXCLUDED.normalized, "
            "status = EXCLUDED.status, is_shadow = EXCLUDED.is_shadow, "
            "model_version = EXCLUDED.model_version, scored_at = CURRENT_TIMESTAMP"
        )
        try:
            db_postgres.execute_write(sql, tuple(params))
            written += len(batch)
        except Exception as exc:  # noqa: BLE001
            logger.warning("clip_quality persist chunk failed (%d rows): %s", len(batch), exc)
    return written


def compute_clip_quality(image_ids, *, persist: bool = True, ensure: bool = True,
                         dim: int = 512) -> dict[int, float]:
    """Compute ``clip_quality_v0`` (0–1) for ``image_ids`` from B/32 embeddings.

    When ``ensure`` is true, missing ``clip_vit_b32_image`` vectors are generated
    just-in-time (Postgres + GPU); this is what lets the signal run *before* the
    keywords phase produces them. Returns ``{image_id: normalized_score}`` for the
    images that had (or gained) an embedding. No-op (empty dict) on non-Postgres.
    """
    from modules import db
    from modules.embedding_spaces import CLIP_IMAGE_SPACE_CODE

    ids = sorted({int(i) for i in (image_ids or []) if i is not None})
    if not ids:
        return {}
    if db._get_db_engine() != "postgres":  # noqa: SLF001
        logger.debug("clip_quality: skipped (engine != postgres)")
        return {}

    if ensure:
        try:
            from modules.culling_embeddings import ensure_embeddings_for_space
            ensure_embeddings_for_space(CLIP_IMAGE_SPACE_CODE, ids)
        except Exception as exc:  # noqa: BLE001 — degrade to whatever vectors exist
            logger.warning("clip_quality: ensure embeddings failed: %s", exc)

    raw = db.get_image_embeddings_batch_for_space(CLIP_IMAGE_SPACE_CODE, ids)
    if not raw:
        logger.warning("clip_quality: no clip_vit_b32_image embeddings for %d ids", len(ids))
        return {}

    vec_ids: list[int] = []
    mats: list[np.ndarray] = []
    for iid, emb in raw.items():
        try:
            v = np.frombuffer(bytes(emb), dtype=np.float32)
        except (TypeError, ValueError):
            continue
        if v.size != dim:
            continue
        vec_ids.append(int(iid))
        mats.append(v)
    if not mats:
        return {}

    good, bad = _prompt_matrices()
    img = np.vstack(mats).astype(np.float32)
    margin, normalized = score_embeddings(img, good, bad)

    if persist:
        _persist_scores([(vec_ids[i], float(margin[i]), float(normalized[i]))
                         for i in range(len(vec_ids))])

    return {vec_ids[i]: float(normalized[i]) for i in range(len(vec_ids))}
