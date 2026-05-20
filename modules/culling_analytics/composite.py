"""Combined heuristic scores for review priority and consistency."""

from __future__ import annotations

from typing import Any

from modules.config import get_config_value


def _cfg(key: str, default: float) -> float:
    try:
        return float(get_config_value(f"culling.analytics.{key}", default=default))
    except (TypeError, ValueError):
        return default


def build_composite(
    *,
    flags: dict[str, Any],
    stack_size: dict[str, Any],
    embeddings: dict[str, Any] | None = None,
    exposure: dict[str, Any] | None = None,
    stack_scores: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Library-level composite summary."""
    mixed_threshold = _cfg("visually_mixed_similarity", 0.85)
    gap_low = _cfg("low_score_gap", 0.05)

    stacks_review = int(flags.get("stacks_needing_review") or 0)
    total_stacks = int(stack_size.get("total_stacks") or 0)
    review_pressure = (stacks_review / total_stacks) if total_stacks else 0.0

    avg_sim = None
    if embeddings and embeddings.get("avg_cosine_similarity") is not None:
        avg_sim = embeddings["avg_cosine_similarity"]

    consistency = 0.5
    if avg_sim is not None:
        consistency = max(0.0, min(1.0, avg_sim))
    elif exposure and exposure.get("exposure_similarity_score") is not None:
        consistency = float(exposure["exposure_similarity_score"])

    gap = (stack_scores or {}).get("score_gap_top_two")
    pick_conf = 0.5
    if gap is not None:
        pick_conf = max(0.0, min(1.0, gap / max(gap_low, 0.001)))

    review_priority = max(0.0, min(1.0, 0.6 * review_pressure + 0.4 * (1.0 - consistency)))

    return {
        "stack_consistency_score": round(consistency, 4),
        "review_priority_score": round(review_priority, 4),
        "auto_pick_confidence": round(pick_conf, 4),
        "auto_reject_confidence": round(1.0 - pick_conf, 4),
        "thresholds": {
            "visually_mixed_similarity": mixed_threshold,
            "low_score_gap": gap_low,
        },
        "interpretation": {
            "review_priority": "Higher = more stacks need human review (conflicts, low consistency).",
            "auto_pick_confidence": "Higher = larger gap between top two scores in stack.",
        },
        "blocks_auto_cull": False,
    }


def build_stack_composite(
    *,
    flags: dict[str, Any] | None = None,
    embeddings: dict[str, Any] | None = None,
    exposure: dict[str, Any] | None = None,
    scores: dict[str, Any] | None = None,
) -> dict[str, Any]:
    emb = embeddings or {}
    exp = exposure or {}
    sc = scores or {}

    consistency = emb.get("avg_cosine_similarity")
    if consistency is None:
        consistency = exp.get("exposure_similarity_score")
    if consistency is None:
        consistency = 0.5
    consistency = max(0.0, min(1.0, float(consistency)))

    gap = sc.get("score_gap_top_two")
    gap_low = _cfg("low_score_gap", 0.05)
    pick_conf = 0.5 if gap is None else max(0.0, min(1.0, float(gap) / max(gap_low, 0.001)))

    conflict = 0.0
    if flags and flags.get("mixed_labels"):
        conflict += 0.3
    if emb.get("visually_mixed"):
        conflict += 0.4
    if exp.get("warnings"):
        conflict += 0.2 * min(1.0, len(exp["warnings"]) / 2.0)

    review_priority = max(0.0, min(1.0, conflict + (1.0 - consistency) * 0.3))

    return {
        "stack_consistency_score": round(consistency, 4),
        "review_priority_score": round(review_priority, 4),
        "auto_pick_confidence": round(pick_conf, 4),
        "metadata_consistency_score": round(1.0 - conflict, 4),
        "visual_similarity_score": round(float(emb.get("avg_cosine_similarity") or consistency), 4),
        "blocks_auto_cull": False,
    }
