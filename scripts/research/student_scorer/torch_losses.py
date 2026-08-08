"""Torch-side losses for image-student training.

Pure-Python helpers in ``objectives.py`` stay importable without torch; this
module is only imported when training.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def rescale_percentile_torch(score, p02, p98):
    """Differentiable port of ``modules.score_normalization.rescale_percentile``."""
    import torch

    score = torch.as_tensor(score)
    p02_t = torch.as_tensor(p02, dtype=score.dtype, device=score.device)
    p98_t = torch.as_tensor(p98, dtype=score.dtype, device=score.device)

    # Degenerate anchors → identity
    degenerate = p98_t <= p02_t
    soft = torch.where(
        p02_t <= 0,
        torch.zeros_like(score),
        torch.where(score >= 0, 0.15 * (score / p02_t), torch.zeros_like(score)),
    )
    mid = (score - p02_t) / (p98_t - p02_t)
    mid = torch.clamp(mid, 0.0, 1.0)
    out = torch.where(score <= p02_t, soft, mid)
    return torch.where(degenerate, score, out)


def masked_huber_torch(pred, target, mask, *, delta: float = 0.05):
    import torch
    import torch.nn.functional as F

    if mask.dtype != torch.bool:
        mask = mask.bool()
    if not bool(mask.any()):
        return pred.new_zeros(())
    err = pred[mask] - target[mask]
    return F.huber_loss(err, torch.zeros_like(err), delta=delta, reduction="mean")


def coverage_normalized_teacher_loss(
    preds: Mapping[str, Any],
    targets: Any,
    masks: Any,
    teachers: Sequence[str],
    *,
    delta: float = 0.05,
) -> Any:
    """Equal-weight mean of per-head masked Huber over *active* teacher heads."""
    import torch

    per_head = []
    for i, name in enumerate(teachers):
        loss = masked_huber_torch(preds[name], targets[:, i], masks[:, i], delta=delta)
        # Only count heads that had at least one active mask in the batch
        if bool(masks[:, i].any()):
            per_head.append(loss)
    if not per_head:
        # Keep graph connected
        return next(iter(preds.values())).sum() * 0.0
    return torch.stack(per_head).mean()


def aux_composite_loss(
    preds: Mapping[str, Any],
    stored_composites: Any,
    composite_masks: Any,
    *,
    delta: float = 0.05,
) -> Any:
    import torch

    keys = ("general", "technical", "aesthetic")
    losses = []
    for i, key in enumerate(keys):
        if key not in preds:
            continue
        if not bool(composite_masks[:, i].any()):
            continue
        losses.append(
            masked_huber_torch(
                preds[key], stored_composites[:, i], composite_masks[:, i], delta=delta
            )
        )
    if not losses:
        return next(iter(preds.values())).sum() * 0.0
    return torch.stack(losses).mean()


def uncertainty_loss(pred, target, mask, *, delta: float = 0.05) -> Any:
    return masked_huber_torch(pred, target, mask, delta=delta)


def compute_composites_torch(
    teacher_preds: Mapping[str, Any],
    *,
    fusion: Mapping[str, Mapping[str, float]],
    anchors: Mapping[str, Mapping[str, float]],
) -> dict[str, Any]:
    """Differentiable frozen fusion (no rounding) for consistency loss."""
    import torch

    rescaled: dict[str, Any] = {}
    for model, score in teacher_preds.items():
        if model in anchors:
            a = anchors[model]
            rescaled[model] = rescale_percentile_torch(
                score, float(a["p02"]), float(a["p98"])
            )
        else:
            rescaled[model] = score

    out: dict[str, Any] = {}
    for category in ("general", "technical", "aesthetic"):
        cat_weights = fusion.get(category, {}) or {}
        active = [(m, float(w)) for m, w in cat_weights.items() if m in rescaled]
        if not active:
            ref = next(iter(teacher_preds.values()))
            out[category] = ref * 0.0
            continue
        total_w = sum(w for _, w in active)
        acc = None
        for m, w in active:
            term = (w / total_w) * rescaled[m]
            acc = term if acc is None else acc + term
        out[category] = torch.clamp(acc, 0.0, 1.0)
    return out


def consistency_loss_torch(
    teacher_preds: Mapping[str, Any],
    stored_composites: Any,
    composite_masks: Any,
    *,
    fusion: Mapping[str, Mapping[str, float]],
    anchors: Mapping[str, Mapping[str, float]],
) -> Any:
    import torch

    derived = compute_composites_torch(teacher_preds, fusion=fusion, anchors=anchors)
    losses = []
    for i, key in enumerate(("general", "technical", "aesthetic")):
        if not bool(composite_masks[:, i].any()):
            continue
        pred = derived[key]
        tgt = stored_composites[:, i]
        m = composite_masks[:, i]
        losses.append(torch.mean(torch.abs(pred[m] - tgt[m])))
    if not losses:
        return next(iter(teacher_preds.values())).sum() * 0.0
    return torch.stack(losses).mean()


def total_student_loss(
    preds: Mapping[str, Any],
    batch: Mapping[str, Any],
    *,
    teachers: Sequence[str],
    fusion: Mapping[str, Mapping[str, float]],
    anchors: Mapping[str, Mapping[str, float]],
    coeffs: Mapping[str, float],
    delta: float = 0.05,
) -> tuple[Any, dict[str, float]]:
    teacher_preds = {t: preds[t] for t in teachers}
    teacher_l = coverage_normalized_teacher_loss(
        preds, batch["targets"], batch["masks"], teachers, delta=delta
    )
    aux_l = aux_composite_loss(
        preds, batch["stored_composites"], batch["composite_masks"], delta=delta
    )
    cons_l = consistency_loss_torch(
        teacher_preds,
        batch["stored_composites"],
        batch["composite_masks"],
        fusion=fusion,
        anchors=anchors,
    )
    unc_l = uncertainty_loss(
        preds["uncertainty"],
        batch["uncertainty_target"],
        batch["uncertainty_mask"],
        delta=delta,
    )
    total = (
        float(coeffs.get("teacher", 1.0)) * teacher_l
        + float(coeffs.get("aux_composite", 0.25)) * aux_l
        + float(coeffs.get("consistency", 0.1)) * cons_l
        + float(coeffs.get("uncertainty", 0.1)) * unc_l
    )
    parts = {
        "teacher": float(teacher_l.detach().cpu()),
        "aux_composite": float(aux_l.detach().cpu()),
        "consistency": float(cons_l.detach().cpu()),
        "uncertainty": float(unc_l.detach().cpu()),
        "total": float(total.detach().cpu()),
    }
    return total, parts
