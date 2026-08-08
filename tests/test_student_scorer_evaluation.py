"""Frozen evaluator integrity tests (AC-5, AC-6, AC-7)."""

from __future__ import annotations

import pytest

from scripts.research.student_scorer.evaluate_culling import group_bootstrap, pairwise_accuracy
from scripts.research.student_scorer.evaluate_scores import (
    assert_selection_split_allowed,
    failed_gate_cannot_be_averaged,
    fidelity_report,
)


def test_test_split_cannot_drive_selection():
    assert_selection_split_allowed("val")
    with pytest.raises(ValueError, match="cannot drive"):
        assert_selection_split_allowed("test")
    with pytest.raises(ValueError, match="cannot drive"):
        assert_selection_split_allowed("ood_test")


def test_metrics_use_frozen_pair_and_saturation_rules():
    preds = [{"spaq": 0.5, "general": 0.5}, {"spaq": 0.6, "general": 0.99}]
    tgts = [{"spaq": 0.5, "general": 0.5}, {"spaq": 0.6, "general": 0.99}]
    report = fidelity_report(
        preds,
        tgts,
        teachers=["spaq"],
        saturation_values=[0.5, 0.99],
        gates={"saturation_low": 0.02, "saturation_high": 0.98, "composite_mae_max": 0.03},
    )
    # Second sample is saturated on general → excluded from non-sat MAE cohort
    assert report["gates"]["composite_mae_nonsaturated"]["value"] == 0.0

    rows = [
        {"image_id": 1, "sub_stack_id": 1, "score_general": 0.5, "pred_general": 0.5},
        {"image_id": 2, "sub_stack_id": 1, "score_general": 0.52, "pred_general": 0.9},
    ]
    # Near-tie below margin ⇒ no confident pairs
    pair = pairwise_accuracy(rows, "pred_general", "score_general", margin=0.04)
    assert pair["n_pairs"] == 0


def test_group_bootstrap_keeps_stack_members_together():
    rows = [
        {"image_id": 1, "sub_stack_id": 1, "score_general": 0.9, "pred_general": 0.9},
        {"image_id": 2, "sub_stack_id": 1, "score_general": 0.1, "pred_general": 0.1},
        {"image_id": 3, "sub_stack_id": 2, "score_general": 0.8, "pred_general": 0.2},
        {"image_id": 4, "sub_stack_id": 2, "score_general": 0.2, "pred_general": 0.8},
    ]
    seen_sizes = []

    def metric(drawn):
        # Record whether stack 1 members always arrive together
        ids = {r["image_id"] for r in drawn if r["sub_stack_id"] == 1}
        seen_sizes.append(len(ids) in (0, 2))
        return pairwise_accuracy(drawn, "pred_general", "score_general", margin=0.05)

    group_bootstrap(rows, metric, reps=20, seed=1)
    assert all(seen_sizes)


def test_failed_required_gate_cannot_be_averaged_away():
    gates = {
        "composite_spearman": {"pass": True, "value": 0.99},
        "median_teacher_spearman": {"pass": False, "value": 0.5},
        "composite_mae_nonsaturated": {"pass": True, "value": 0.01},
    }
    assert failed_gate_cannot_be_averaged(gates) is True
    # A high average of values must not flip the failure flag
    avg = sum(g["value"] for g in gates.values()) / len(gates)
    assert avg >= 0.5
    assert failed_gate_cannot_be_averaged(gates) is True
