"""Objective / masking tests (AC-4, AC-5)."""

from __future__ import annotations

from scripts.research.student_scorer.common import (
    PROVENANCE_AUTOMATIC,
    PROVENANCE_HUMAN,
    PROVENANCE_UNKNOWN,
)
from scripts.research.student_scorer.objectives import (
    build_rank_pairs,
    coverage_normalized_head_losses,
    human_weight_for_field,
    masked_huber_mean,
    pair_is_confident,
)


def test_missing_teacher_targets_are_masked_not_zeroed():
    preds = [0.5, 0.6, 0.7]
    targets = [0.5, None, 0.7]
    masks = [True, False, True]
    loss = masked_huber_mean(preds, targets, masks)
    assert loss is not None
    loss_if_zeroed = masked_huber_mean(preds, [0.5, 0.0, 0.7], [True, True, True])
    assert loss != loss_if_zeroed


def test_head_losses_are_coverage_normalized():
    preds = {
        "a": [0.1, 0.2, 0.3, 0.4, 0.5],
        "b": [0.9],
    }
    targets = {
        "a": [0.0, 0.0, 0.0, 0.0, 0.0],
        "b": [0.0],
    }
    masks = {
        "a": [True] * 5,
        "b": [True],
    }
    out = coverage_normalized_head_losses(
        preds, targets, masks, head_weights={"a": 1.0, "b": 1.0}
    )
    assert out["active_heads"] == 2
    assert abs(out["loss"] - 0.5 * (out["per_head"]["a"] + out["per_head"]["b"])) < 1e-9


def test_near_ties_do_not_create_confident_pairs():
    assert not pair_is_confident(0.50, 0.52, margin=0.04)
    assert pair_is_confident(0.50, 0.55, margin=0.04)
    items = [
        {
            "image_id": "1",
            "score_general": 0.50,
            "pick_status": 0,
            "rating": None,
            "provenance": {"pick_status": PROVENANCE_UNKNOWN, "rating": PROVENANCE_UNKNOWN},
        },
        {
            "image_id": "2",
            "score_general": 0.52,
            "pick_status": 0,
            "rating": None,
            "provenance": {"pick_status": PROVENANCE_UNKNOWN, "rating": PROVENANCE_UNKNOWN},
        },
    ]
    pairs = build_rank_pairs(items, margin=0.04)
    assert pairs == []


def test_unverified_human_fields_have_zero_human_weight():
    assert human_weight_for_field({"rating": PROVENANCE_UNKNOWN}, "rating") == 0.0
    assert human_weight_for_field({"rating": PROVENANCE_AUTOMATIC}, "rating") == 0.0
    assert human_weight_for_field({"rating": PROVENANCE_HUMAN}, "rating") == 1.0
