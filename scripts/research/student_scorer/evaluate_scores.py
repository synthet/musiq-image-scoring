"""Frozen score-fidelity evaluator (locked before image-model claims)."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from scripts.research.student_scorer.common import (
    DEFAULT_GATES,
    DEFAULT_TEACHERS,
    COMPOSITE_KEYS,
    regression_metrics,
    saturated_mask,
)


FORBIDDEN_SELECTION_SPLITS = frozenset({"test", "ood_test"})


def assert_selection_split_allowed(split: str) -> None:
    """Model selection may use train/val only — never test/OOD."""
    if split in FORBIDDEN_SELECTION_SPLITS:
        raise ValueError(
            f"split {split!r} cannot drive model selection (AC-5); use val only"
        )


def fidelity_report(
    predictions: Sequence[Mapping[str, float]],
    targets: Sequence[Mapping[str, float]],
    masks: Sequence[Mapping[str, bool]] | None = None,
    *,
    teachers: Sequence[str] = DEFAULT_TEACHERS,
    gates: Mapping[str, Any] | None = None,
    saturation_values: Sequence[float] | None = None,
) -> dict[str, Any]:
    """Per-head and composite fidelity metrics with optional saturation cohort."""
    g = {**DEFAULT_GATES, **(gates or {})}
    heads = list(teachers) + list(COMPOSITE_KEYS)
    per_head: dict[str, Any] = {}
    for head in heads:
        pred_v: list[float] = []
        tgt_v: list[float] = []
        for i, (p, t) in enumerate(zip(predictions, targets)):
            if head not in p or head not in t:
                continue
            if masks is not None and not (masks[i] or {}).get(head, True):
                continue
            pred_v.append(float(p[head]))
            tgt_v.append(float(t[head]))
        per_head[head] = regression_metrics(pred_v, tgt_v)

    # Non-saturated composite MAE on general if saturation_values provided
    non_sat_mae = None
    if saturation_values is not None and len(saturation_values) == len(predictions):
        mask = saturated_mask(
            saturation_values,
            low=float(g["saturation_low"]),
            high=float(g["saturation_high"]),
        )
        pred_v = []
        tgt_v = []
        for keep, p, t in zip(mask, predictions, targets):
            if not keep:
                continue
            if "general" in p and "general" in t:
                pred_v.append(float(p["general"]))
                tgt_v.append(float(t["general"]))
        non_sat_mae = regression_metrics(pred_v, tgt_v).get("mae")

    teacher_spearmans = [
        per_head[t]["spearman"]
        for t in teachers
        if per_head.get(t, {}).get("spearman") is not None
    ]
    median_teacher = None
    if teacher_spearmans:
        teacher_spearmans_sorted = sorted(teacher_spearmans)
        mid = len(teacher_spearmans_sorted) // 2
        if len(teacher_spearmans_sorted) % 2:
            median_teacher = teacher_spearmans_sorted[mid]
        else:
            median_teacher = (
                teacher_spearmans_sorted[mid - 1] + teacher_spearmans_sorted[mid]
            ) / 2

    gate_results = {
        "composite_spearman": {
            "value": per_head.get("general", {}).get("spearman"),
            "threshold": g["composite_spearman_min"],
            "pass": (
                per_head.get("general", {}).get("spearman") is not None
                and per_head["general"]["spearman"] >= g["composite_spearman_min"]
            ),
        },
        "median_teacher_spearman": {
            "value": median_teacher,
            "threshold": g["median_teacher_spearman_min"],
            "pass": (
                median_teacher is not None
                and median_teacher >= g["median_teacher_spearman_min"]
            ),
        },
        "composite_mae_nonsaturated": {
            "value": non_sat_mae,
            "threshold": g["composite_mae_max"],
            "pass": non_sat_mae is not None and non_sat_mae <= g["composite_mae_max"],
        },
    }
    required_failed = [k for k, v in gate_results.items() if not v["pass"]]
    return {
        "per_head": per_head,
        "gates": gate_results,
        "required_failed": required_failed,
        "all_required_passed": len(required_failed) == 0,
    }


def failed_gate_cannot_be_averaged(
    gate_results: Mapping[str, Mapping[str, Any]],
) -> bool:
    """Return True iff any required gate failed — averaging must not hide this."""
    return any(not g.get("pass", False) for g in gate_results.values())
