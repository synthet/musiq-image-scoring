"""Batch oversized agent-cull review units for vision payload limits."""

from __future__ import annotations

from typing import Any, Sequence

from modules.agent_cull.discovery import ReviewUnit


def order_image_ids_for_batching(
    image_ids: Sequence[int],
    rows_by_id: dict[int, dict[str, Any]],
    *,
    score_field: str = "score_general",
) -> list[int]:
    """Stable score-desc ordering for batch boundaries."""

    def _key(iid: int) -> tuple:
        row = rows_by_id.get(iid) or {}
        score = row.get(score_field) or row.get("score_general") or 0
        try:
            s = float(score)
        except (TypeError, ValueError):
            s = 0.0
        return (-s, iid)

    return sorted((int(i) for i in image_ids), key=_key)


def split_into_batches(image_ids: Sequence[int], batch_size: int) -> list[list[int]]:
    size = max(1, int(batch_size))
    ids = list(image_ids)
    if not ids:
        return []
    return [ids[i : i + size] for i in range(0, len(ids), size)]


def plan_review_batches(
    unit: ReviewUnit,
    rows_by_id: dict[int, dict[str, Any]],
    *,
    batch_size: int,
    score_field: str = "score_general",
) -> list[list[int]]:
    """Return ordered image-id batches; single batch when unit fits."""
    ordered = order_image_ids_for_batching(unit.image_ids, rows_by_id, score_field=score_field)
    if len(ordered) <= max(1, int(batch_size)):
        return [ordered]
    return split_into_batches(ordered, batch_size)


def subset_review_unit(unit: ReviewUnit, batch_image_ids: Sequence[int]) -> ReviewUnit:
    """Narrow a review unit to one batch while preserving review_unit_key."""
    batch_set = {int(i) for i in batch_image_ids}
    ordered_ids = tuple(int(i) for i in batch_image_ids)
    return ReviewUnit(
        stack_id=unit.stack_id,
        sub_stack_id=unit.sub_stack_id,
        review_unit_key=unit.review_unit_key,
        image_ids=ordered_ids,
        picked_ids=tuple(i for i in unit.picked_ids if i in batch_set),
        rejected_ids=tuple(i for i in unit.rejected_ids if i in batch_set),
        neutral_ids=tuple(i for i in unit.neutral_ids if i in batch_set),
        usable_ids=tuple(i for i in unit.usable_ids if i in batch_set),
        hierarchy_tier=unit.hierarchy_tier,
        skip_reason=None,
    )


def merge_validated_batch_responses(
    parts: Sequence[dict[str, Any]],
    *,
    stack_id: int,
    sub_stack_id: int | None,
) -> dict[str, Any]:
    """Merge per-batch agent JSON into one validated-shaped dict."""
    if not parts:
        raise ValueError("no_batch_responses")
    if len(parts) == 1:
        return dict(parts[0])

    decisions: list[dict[str, Any]] = []
    advisories: list[dict[str, Any]] = []
    viewed: list[int] = []
    summaries: list[str] = []
    confidences: list[float] = []
    group_decisions: list[str] = []

    for part in parts:
        group_decisions.append(str(part.get("group_decision") or "do_not_apply"))
        try:
            confidences.append(float(part.get("confidence") or 0.0))
        except (TypeError, ValueError):
            confidences.append(0.0)
        summary = str(part.get("summary") or "").strip()
        if summary:
            summaries.append(summary)
        for item in part.get("rejected_image_decisions") or []:
            if isinstance(item, dict):
                decisions.append(dict(item))
        for item in part.get("picked_image_advisories") or []:
            if isinstance(item, dict):
                advisories.append(dict(item))
        for vid in part.get("viewed_image_ids") or []:
            try:
                viewed.append(int(vid))
            except (TypeError, ValueError):
                continue

    merged_group = (
        "apply_removals"
        if any(g == "apply_removals" for g in group_decisions)
        else "do_not_apply"
    )
    avg_conf = sum(confidences) / len(confidences) if confidences else 0.75
    vision_used = any(part.get("vision_used") is True for part in parts)

    out = dict(parts[0])
    out.update(
        {
            "stack_id": stack_id,
            "sub_stack_id": sub_stack_id,
            "group_decision": merged_group,
            "confidence": avg_conf,
            "summary": " | ".join(summaries)[:4000] if summaries else out.get("summary", ""),
            "rejected_image_decisions": decisions,
            "picked_image_advisories": advisories or out.get("picked_image_advisories"),
            "viewed_image_ids": sorted(set(viewed)),
            "vision_used": vision_used,
            "batch_count": len(parts),
        }
    )
    return out
