"""Discover eligible stack/substack review units for agent-assisted cull review."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from modules.agent_cull.config import AgentCullConfig
from modules.culling_analytics.hierarchy import (
    TIER_SINGLETON_ROOT,
    classify_stack_tier,
)


@dataclass(frozen=True)
class ReviewUnit:
    stack_id: int
    sub_stack_id: int | None
    review_unit_key: str
    image_ids: tuple[int, ...]
    picked_ids: tuple[int, ...]
    rejected_ids: tuple[int, ...]
    neutral_ids: tuple[int, ...]
    usable_ids: tuple[int, ...]
    hierarchy_tier: str
    skip_reason: str | None = None


@dataclass
class GroupCounts:
    total: int = 0
    picked: int = 0
    rejected: int = 0
    neutral: int = 0
    usable: int = 0


def build_review_unit_key(stack_id: int, sub_stack_id: int | None) -> str:
    if sub_stack_id is None:
        return f"stack:{stack_id}"
    return f"stack:{stack_id}:sub:{sub_stack_id}"


def effective_pick_status(row: dict[str, Any], *, decision_source: str) -> int:
    """Return 1 picked, -1 rejected, 0 neutral."""
    pick_status = int(row.get("pick_status") or 0)
    if decision_source == "pick_status":
        return pick_status
    cull = str(row.get("cull_decision") or "").strip().lower()
    if pick_status == 1 or cull == "pick":
        return 1
    if pick_status == -1 or cull == "reject":
        return -1
    return 0


def classify_image_status(row: dict[str, Any], *, decision_source: str) -> str:
    status = effective_pick_status(row, decision_source=decision_source)
    if status == 1:
        return "picked"
    if status == -1:
        return "rejected"
    return "neutral"


def count_group_members(
    rows: list[dict[str, Any]],
    *,
    decision_source: str,
    is_usable_fn,
) -> GroupCounts:
    counts = GroupCounts()
    for row in rows:
        counts.total += 1
        status = classify_image_status(row, decision_source=decision_source)
        if status == "picked":
            counts.picked += 1
        elif status == "rejected":
            counts.rejected += 1
        else:
            counts.neutral += 1
        if is_usable_fn(row):
            counts.usable += 1
    return counts


def is_group_eligible(
    counts: GroupCounts,
    cfg: AgentCullConfig,
    *,
    hierarchy_tier: str | None = None,
) -> tuple[bool, str | None]:
    if hierarchy_tier == TIER_SINGLETON_ROOT:
        return False, "singleton_root"
    if counts.usable < cfg.min_usable_images:
        return False, "insufficient_usable_images"
    if counts.total > cfg.max_group_size:
        return False, "group_too_large"
    if counts.rejected < 1:
        return False, "no_rejected_images"
    if counts.picked < 1:
        return False, "no_picked_images"
    if counts.picked < counts.rejected:
        return False, "picked_lt_rejected"
    return True, None


def partition_rows_by_review_unit(
    stack_id: int,
    rows: list[dict[str, Any]],
    *,
    leaf_count: int,
    images_with_substack: int,
) -> list[tuple[int | None, list[dict[str, Any]]]]:
    """Split stack member rows into review units (sub-stack leaves or flat root)."""
    tier = classify_stack_tier(
        len(rows),
        leaf_count,
        images_with_substack,
    )
    if tier == TIER_SINGLETON_ROOT:
        return []

    substack_ids = {r.get("sub_stack_id") for r in rows if r.get("sub_stack_id") is not None}
    if not substack_ids:
        return [(None, list(rows))]

    units: list[tuple[int | None, list[dict[str, Any]]]] = []
    for sub_id in sorted(int(s) for s in substack_ids):
        unit_rows = [r for r in rows if int(r.get("sub_stack_id") or 0) == sub_id]
        if unit_rows:
            units.append((sub_id, unit_rows))
    return units


def build_review_unit(
    stack_id: int,
    sub_stack_id: int | None,
    rows: list[dict[str, Any]],
    cfg: AgentCullConfig,
    *,
    hierarchy_tier: str,
    is_usable_fn,
) -> ReviewUnit:
    counts = count_group_members(rows, decision_source=cfg.decision_source, is_usable_fn=is_usable_fn)
    eligible, skip_reason = is_group_eligible(counts, cfg, hierarchy_tier=hierarchy_tier)

    picked: list[int] = []
    rejected: list[int] = []
    neutral: list[int] = []
    usable: list[int] = []
    all_ids: list[int] = []

    for row in rows:
        image_id = int(row["id"])
        all_ids.append(image_id)
        status = classify_image_status(row, decision_source=cfg.decision_source)
        if status == "picked":
            picked.append(image_id)
        elif status == "rejected":
            rejected.append(image_id)
        else:
            neutral.append(image_id)
        if is_usable_fn(row):
            usable.append(image_id)

    if not eligible and skip_reason is None:
        skip_reason = "ineligible"

    return ReviewUnit(
        stack_id=stack_id,
        sub_stack_id=sub_stack_id,
        review_unit_key=build_review_unit_key(stack_id, sub_stack_id),
        image_ids=tuple(all_ids),
        picked_ids=tuple(picked),
        rejected_ids=tuple(rejected),
        neutral_ids=tuple(neutral),
        usable_ids=tuple(usable),
        hierarchy_tier=hierarchy_tier,
        skip_reason=skip_reason if not eligible else None,
    )


def default_is_usable(row: dict[str, Any]) -> bool:
    """True when source file or thumbnail path exists on disk."""
    for key in ("file_path", "thumbnail_path", "thumbnail_path_win"):
        path = row.get(key)
        if path and os.path.isfile(str(path)):
            return True
    return False


def discover_eligible_units_from_stack_rows(
    stack_id: int,
    rows: list[dict[str, Any]],
    cfg: AgentCullConfig,
    *,
    leaf_count: int = 0,
    images_with_substack: int = 0,
    is_usable_fn=default_is_usable,
) -> list[ReviewUnit]:
    """Pure discovery over in-memory stack member rows (for tests and DB layer)."""
    tier = classify_stack_tier(len(rows), leaf_count, images_with_substack)
    partitions = partition_rows_by_review_unit(
        stack_id,
        rows,
        leaf_count=leaf_count,
        images_with_substack=images_with_substack,
    )
    units: list[ReviewUnit] = []
    for sub_stack_id, unit_rows in partitions:
        unit = build_review_unit(
            stack_id,
            sub_stack_id,
            unit_rows,
            cfg,
            hierarchy_tier=tier,
            is_usable_fn=is_usable_fn,
        )
        if unit.skip_reason is None:
            units.append(unit)
    return units
