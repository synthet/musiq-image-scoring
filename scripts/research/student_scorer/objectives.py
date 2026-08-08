"""Training objectives for student distillation.

All losses are pure-Python / numpy-friendly so unit tests do not require torch.
Torch wrappers call these helpers after detaching to CPU when needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from scripts.research.student_scorer.common import (
    PROVENANCE_HUMAN,
    compute_composites_frozen,
)


def huber(error: float, delta: float = 0.05) -> float:
    abs_e = abs(error)
    if abs_e <= delta:
        return 0.5 * error * error
    return delta * (abs_e - 0.5 * delta)


def masked_huber_mean(
    preds: Sequence[float | None],
    targets: Sequence[float | None],
    masks: Sequence[bool],
    *,
    delta: float = 0.05,
) -> float | None:
    """Mean Huber over masked positions. Missing targets must be masked, never zeroed."""
    total = 0.0
    count = 0
    for p, t, m in zip(preds, targets, masks):
        if not m:
            continue
        if p is None or t is None:
            continue
        total += huber(float(p) - float(t), delta=delta)
        count += 1
    if count == 0:
        return None
    return total / count


def coverage_normalized_head_losses(
    preds_by_head: Mapping[str, Sequence[float | None]],
    targets_by_head: Mapping[str, Sequence[float | None]],
    masks_by_head: Mapping[str, Sequence[bool]],
    *,
    head_weights: Mapping[str, float] | None = None,
    delta: float = 0.05,
) -> dict[str, float]:
    """Per-head masked Huber, then weight by explicit head weights (not raw row count).

    Returns ``{"loss": weighted_sum, "per_head": {...}, "active_heads": N}``.
    """
    weights = dict(head_weights or {})
    per_head: dict[str, float] = {}
    for head, preds in preds_by_head.items():
        targets = targets_by_head.get(head, [])
        masks = masks_by_head.get(head, [False] * len(preds))
        loss = masked_huber_mean(preds, targets, masks, delta=delta)
        if loss is None:
            continue
        per_head[head] = float(loss)
        weights.setdefault(head, 1.0)

    if not per_head:
        return {"loss": 0.0, "per_head": {}, "active_heads": 0}

    # Normalize explicit weights over *active* heads only (coverage-normalized).
    active_w = {h: float(weights[h]) for h in per_head}
    wsum = sum(active_w.values()) or 1.0
    total = sum(active_w[h] / wsum * per_head[h] for h in per_head)
    return {"loss": float(total), "per_head": per_head, "active_heads": len(per_head)}


@dataclass(frozen=True)
class RankPair:
    id_a: str
    id_b: str
    prefer_a: bool  # True if A should rank above B
    source: str
    weight: float
    margin: float


def pair_is_confident(score_a: float, score_b: float, margin: float) -> bool:
    return abs(float(score_a) - float(score_b)) >= float(margin)


def build_rank_pairs(
    group_items: Sequence[Mapping[str, object]],
    *,
    margin: float = 0.04,
    id_key: str = "image_id",
    score_key: str = "score_general",
    pick_key: str = "pick_status",
    rating_key: str = "rating",
    provenance_key: str = "provenance",
) -> list[RankPair]:
    """Build within-group RankNet pairs with frozen preference precedence.

    Precedence: verified human pick > verified rating Δ > teacher/composite gap.
    Near-ties (below margin) never become confident pairs.
    """
    pairs: list[RankPair] = []
    items = list(group_items)
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i], items[j]
            id_a, id_b = str(a[id_key]), str(b[id_key])
            prov_a = a.get(provenance_key) or {}
            prov_b = b.get(provenance_key) or {}
            if not isinstance(prov_a, Mapping):
                prov_a = {}
            if not isinstance(prov_b, Mapping):
                prov_b = {}

            pick_a = int(a.get(pick_key) or 0)
            pick_b = int(b.get(pick_key) or 0)
            human_pick = (
                prov_a.get("pick_status") == PROVENANCE_HUMAN
                and prov_b.get("pick_status") == PROVENANCE_HUMAN
            )
            if human_pick and pick_a != pick_b:
                prefer_a = pick_a > pick_b
                pairs.append(
                    RankPair(id_a, id_b, prefer_a, "human_pick", 1.0, margin)
                )
                continue

            rating_a = a.get(rating_key)
            rating_b = b.get(rating_key)
            human_rating = (
                prov_a.get("rating") == PROVENANCE_HUMAN
                and prov_b.get("rating") == PROVENANCE_HUMAN
                and rating_a is not None
                and rating_b is not None
            )
            if human_rating and int(rating_a) != int(rating_b):
                prefer_a = int(rating_a) > int(rating_b)
                pairs.append(
                    RankPair(id_a, id_b, prefer_a, "human_rating", 0.8, margin)
                )
                continue

            sa = a.get(score_key)
            sb = b.get(score_key)
            if sa is None or sb is None:
                continue
            if not pair_is_confident(float(sa), float(sb), margin):
                continue
            prefer_a = float(sa) > float(sb)
            pairs.append(
                RankPair(id_a, id_b, prefer_a, "teacher_composite", 0.4, margin)
            )
    return pairs


def ranknet_loss(logit_diff: float, prefer_a: bool) -> float:
    """Binary logistic RankNet: prefer_a ⇒ P(A>B) should be high."""
    # Softplus form: log(1+exp(-y * s)) with y in {+1,-1}
    y = 1.0 if prefer_a else -1.0
    z = -y * float(logit_diff)
    # Numerically stable softplus
    if z > 20:
        return z
    if z < -20:
        return 0.0
    import math

    return math.log1p(math.exp(z))


def human_weight_for_field(provenance: Mapping[str, str], field: str) -> float:
    """Unverified / automatic / unknown fields contribute zero human loss weight."""
    return 1.0 if provenance.get(field) == PROVENANCE_HUMAN else 0.0


def ordinal_rating_loss(pred: float, target: int, *, min_r: int = 1, max_r: int = 5) -> float:
    """Simple squared error on rating mapped to [0,1] midpoint of bins."""
    t = max(min_r, min(max_r, int(target)))
    # Map rating r to (r - 0.5) / max_r in (0,1]
    target_f = (t - 0.5) / float(max_r)
    err = float(pred) - target_f
    return err * err


def consistency_loss(
    predicted_teacher_heads: Mapping[str, float],
    stored_composites: Mapping[str, float],
    *,
    fusion: Mapping[str, Mapping[str, float]],
    anchors: Mapping[str, Mapping[str, float]],
) -> float:
    derived = compute_composites_frozen(predicted_teacher_heads, fusion=fusion, anchors=anchors)
    total = 0.0
    n = 0
    for key in ("general", "technical", "aesthetic"):
        if key not in stored_composites:
            continue
        total += abs(derived[key] - float(stored_composites[key]))
        n += 1
    return total / n if n else 0.0


def teacher_disagreement(scores: Mapping[str, float]) -> float:
    vals = [float(v) for v in scores.values()]
    if len(vals) < 2:
        return 0.0
    mean = sum(vals) / len(vals)
    var = sum((v - mean) ** 2 for v in vals) / len(vals)
    return var ** 0.5


def combine_losses(
    *,
    teacher: float,
    rank: float = 0.0,
    human: float = 0.0,
    consistency: float = 0.0,
    coeffs: Mapping[str, float] | None = None,
) -> float:
    c = {
        "teacher": 1.0,
        "rank": 0.4,
        "human": 0.25,
        "consistency": 0.1,
    }
    if coeffs:
        c.update({k: float(v) for k, v in coeffs.items()})
    return (
        c["teacher"] * teacher
        + c["rank"] * rank
        + c["human"] * human
        + c["consistency"] * consistency
    )
