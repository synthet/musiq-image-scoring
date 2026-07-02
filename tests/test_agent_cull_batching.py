"""Tests for agent-cull review batching helpers."""

from modules.agent_cull.batching import (
    merge_validated_batch_responses,
    plan_review_batches,
    split_into_batches,
    subset_review_unit,
)
from modules.agent_cull.discovery import ReviewUnit


def _unit(*image_ids: int) -> ReviewUnit:
    picked = tuple(image_ids[:2])
    rejected = tuple(image_ids[2:])
    return ReviewUnit(
        stack_id=1,
        sub_stack_id=2,
        review_unit_key="stack:1:sub:2",
        image_ids=image_ids,
        picked_ids=picked,
        rejected_ids=rejected,
        neutral_ids=(),
        usable_ids=image_ids,
        hierarchy_tier="single_leaf",
    )


def test_split_into_batches():
    assert split_into_batches(list(range(25)), 10) == [
        list(range(0, 10)),
        list(range(10, 20)),
        list(range(20, 25)),
    ]


def test_plan_review_batches_single_when_small():
    unit = _unit(*range(1, 8))
    rows = {i: {"id": i, "score_general": float(i)} for i in range(1, 8)}
    batches = plan_review_batches(unit, rows, batch_size=10)
    assert len(batches) == 1
    assert len(batches[0]) == 7


def test_plan_review_batches_multiple_when_large():
    unit = _unit(*range(1, 26))
    rows = {i: {"id": i, "score_general": float(i)} for i in range(1, 26)}
    batches = plan_review_batches(unit, rows, batch_size=10)
    assert len(batches) == 3
    assert sum(len(b) for b in batches) == 25


def test_subset_review_unit_preserves_key():
    unit = _unit(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)
    batch = [11, 10, 9, 8, 7, 6, 5, 4, 3, 2]
    sub = subset_review_unit(unit, batch)
    assert sub.review_unit_key == unit.review_unit_key
    assert sub.image_ids == tuple(batch)
    assert sub.picked_ids == (2,)
    assert sub.rejected_ids == (3, 4, 5, 6, 7, 8, 9, 10, 11)


def test_merge_validated_batch_responses():
    part_a = {
        "group_decision": "apply_removals",
        "confidence": 0.8,
        "summary": "batch a",
        "rejected_image_decisions": [{"image_id": 3, "decision": "remove", "confidence": 0.9, "better_alternatives": [1]}],
        "viewed_image_ids": [1, 3],
        "vision_used": True,
    }
    part_b = {
        "group_decision": "do_not_apply",
        "confidence": 0.7,
        "summary": "batch b",
        "rejected_image_decisions": [{"image_id": 4, "decision": "keep", "confidence": 0.6, "better_alternatives": []}],
        "viewed_image_ids": [2, 4],
        "vision_used": True,
    }
    merged = merge_validated_batch_responses([part_a, part_b], stack_id=1, sub_stack_id=2)
    assert merged["group_decision"] == "apply_removals"
    assert merged["batch_count"] == 2
    assert len(merged["rejected_image_decisions"]) == 2
    assert set(merged["viewed_image_ids"]) == {1, 2, 3, 4}
