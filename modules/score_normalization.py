"""
Canonical score normalization and composite scoring module.

Single source of truth for:
- Percentile-based rescaling of model scores
- Composite score computation (technical, aesthetic, general)
- Rating assignment (1-5 stars)
- Color label assignment

Individual model scores stored in DB remain in theoretical 0-1 range.
Composite scores use empirical percentile rescaling for better discrimination.
"""

import logging
from typing import Dict

logger = logging.getLogger(__name__)

# --- Percentile Anchors (empirical, from DB analysis of 61,350 images) ---
# These define the effective range of each model on our corpus.
# Scores below p02 map to 0.0, above p98 map to 1.0.
# Refreshed from the model-score quality report (May 2026); `topiq` added when
# it was promoted into the live fusion. `arniqa` anchors come from the full-corpus
# shadow backfill (61,350 images, p02≈0.467 / p98≈0.746, effective range ~0.28):
# they calibrate the shadow scores but do NOT enter fusion (see `scoring.fusion`).
# `qpt_v2` is not registered until #185.
DEFAULT_PERCENTILE_ANCHORS = {
    "liqe":   {"p02": 0.311, "p98": 0.998},
    "ava":    {"p02": 0.301, "p98": 0.524},
    "spaq":   {"p02": 0.257, "p98": 0.760},
    "topiq":  {"p02": 0.390, "p98": 0.709},
    "arniqa": {"p02": 0.467, "p98": 0.746},
}

# --- Composite (fusion) Weights ---
# "Moderate" profile adopted May 2026 after the corpus quality analysis: `topiq`
# joins all three composites so `technical` is no longer a LIQE alias. `arniqa`
# promoted from shadow into `general` + `technical` (May 2026) after full-corpus
# calibration — it is a technical NR-IQA signal (~uncorrelated with aesthetic),
# so it is intentionally absent from `aesthetic`. Membership and weights are
# overridable via `scoring.fusion` in config.json.
DEFAULT_COMPOSITE_WEIGHTS = {
    "general":   {"liqe": 0.35, "spaq": 0.30, "topiq": 0.13, "arniqa": 0.10, "ava": 0.12},
    "technical": {"topiq": 0.30, "arniqa": 0.25, "spaq": 0.25, "liqe": 0.20},
    "aesthetic": {"ava": 0.40, "spaq": 0.50, "liqe": 0.10},
}

# --- Rating Thresholds (applied to rescaled general score) ---
DEFAULT_RATING_THRESHOLDS = {
    5: 0.90,
    4: 0.72,
    3: 0.50,
    2: 0.30,
}

# --- Label Thresholds (applied to rescaled tech/aes scores) ---
DEFAULT_LABEL_THRESHOLDS = {
    "red_tech_max": 0.30,
    "purple_tech_max": 0.50,
    "purple_aes_min": 0.65,
    "blue_aes_min": 0.65,
    "blue_tech_min": 0.65,
    "green_tech_min": 0.55,
}

_config_cache = None


def _load_config() -> dict:
    """Load scoring config (config.json merged with environment.json), with caching."""
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    try:
        from modules.config import load_config as _load_app_config

        _config_cache = _load_app_config()
        return _config_cache
    except Exception as e:
        logger.warning("Could not load config for scoring: %s", e)

    _config_cache = {}
    return _config_cache


def reload_config():
    """Force reload of config cache (call after config changes)."""
    global _config_cache
    _config_cache = None


def get_percentile_anchors() -> dict:
    cfg = _load_config()
    return cfg.get("percentile_anchors", DEFAULT_PERCENTILE_ANCHORS)


def get_composite_weights() -> dict:
    """Composite (fusion) weights per category.

    Resolution order:
      1. ``scoring.fusion`` (canonical, lives next to ``scoring.models``)
      2. ``composite_weights`` (legacy top-level, kept for back-compat)
      3. ``DEFAULT_COMPOSITE_WEIGHTS``
    """
    cfg = _load_config()
    fusion = (cfg.get("scoring") or {}).get("fusion")
    if isinstance(fusion, dict) and fusion:
        return fusion
    legacy = cfg.get("composite_weights")
    if isinstance(legacy, dict) and legacy:
        return legacy
    return DEFAULT_COMPOSITE_WEIGHTS


def get_rating_thresholds() -> dict:
    cfg = _load_config()
    raw = cfg.get("rating_thresholds", DEFAULT_RATING_THRESHOLDS)
    return {int(k): v for k, v in raw.items()}


def get_label_thresholds() -> dict:
    cfg = _load_config()
    return cfg.get("label_thresholds", DEFAULT_LABEL_THRESHOLDS)


# ─── Core Functions ──────────────────────────────────────────────────────────


def rescale_percentile(score: float, p02: float, p98: float) -> float:
    """
    Rescale a 0-1 model score using empirical percentile anchors.
    Maps [p02, p98] -> [0.0, 1.0], clamped.
    Scores below p02 are linearly mapped to [0, 0.15] so composites stay visible
    when all models are in the low tail (avoids "0% composite" with non-zero raw scores).
    """
    if p98 <= p02:
        return score
    if score <= p02:
        # Soft floor: map [0, p02] -> [0, 0.15] so low scores still show a non-zero composite
        if p02 <= 0:
            return 0.0
        return 0.15 * (score / p02) if score >= 0 else 0.0
    rescaled = (score - p02) / (p98 - p02)
    return max(0.0, min(1.0, rescaled))


def rescale_scores(scores: Dict[str, float]) -> Dict[str, float]:
    """
    Apply percentile rescaling to a dict of {model_name: normalized_score}.
    Returns new dict with rescaled values.
    """
    anchors = get_percentile_anchors()
    rescaled = {}
    for model, score in scores.items():
        if model in anchors:
            a = anchors[model]
            rescaled[model] = rescale_percentile(score, a["p02"], a["p98"])
        else:
            rescaled[model] = score
    return rescaled


def compute_composites(scores: Dict[str, float]) -> Dict[str, float]:
    """
    Compute technical, aesthetic, and general scores from raw model scores.
    Applies percentile rescaling before weighting.

    Args:
        scores: dict of {model_name: normalized_score_0_1} (from DB or model output)

    Returns:
        {"technical": float, "aesthetic": float, "general": float}
    """
    rescaled = rescale_scores(scores)
    weights = get_composite_weights()

    def weighted_sum(category: str) -> float:
        cat_weights = weights.get(category, {})
        # Only weight models actually present — re-normalize so missing models
        # don't pull the composite toward 0.
        active = {m: w for m, w in cat_weights.items() if m in rescaled}
        if not active:
            return 0.0
        total_weight = sum(active.values())
        total = sum(w * rescaled[m] for m, w in active.items())
        return round(max(0.0, min(1.0, total / total_weight if total_weight > 0 else 0.0)), 4)

    return {
        "technical": weighted_sum("technical"),
        "aesthetic": weighted_sum("aesthetic"),
        "general":  weighted_sum("general"),
    }


def score_to_rating(general_score: float) -> int:
    """
    Convert rescaled general score to 1-5 star rating.
    """
    s = max(0.0, min(1.0, general_score))
    thresholds = get_rating_thresholds()

    for rating in sorted(thresholds.keys(), reverse=True):
        if s >= thresholds[rating]:
            return rating
    return 1


def determine_label(scores: Dict[str, float]) -> str:
    """
    Determine Lightroom color label from raw model scores.
    Applies percentile rescaling internally.

    Returns one of: Red, Purple, Blue, Green, Yellow
    """
    composites = compute_composites(scores)
    tech = composites["technical"]
    aes = composites["aesthetic"]

    lt = get_label_thresholds()

    if tech < lt["red_tech_max"]:
        return "Red"
    if aes > lt["purple_aes_min"] and tech < lt["purple_tech_max"]:
        return "Purple"
    if aes > lt["blue_aes_min"] and tech > lt["blue_tech_min"]:
        return "Blue"
    if tech > lt["green_tech_min"]:
        return "Green"
    return "Yellow"


def compute_all(scores: Dict[str, float]) -> Dict:
    """
    One-shot: compute composites, rating, and label from raw model scores.

    Args:
        scores: {model_name: normalized_0_1_score} e.g. {"liqe": 0.85, "ava": 0.42, "spaq": 0.61}

    Returns:
        {
            "technical": float,
            "aesthetic": float,
            "general": float,
            "rating": int,
            "label": str,
        }
    """
    composites = compute_composites(scores)
    rating = score_to_rating(composites["general"])
    label = determine_label(scores)

    return {
        **composites,
        "rating": rating,
        "label": label,
    }
