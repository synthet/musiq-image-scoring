"""
Unit tests for selection_policy module.

Policy constants and behavior: docs/planning/refactoring/STACK_CULLING_REFACTOR_PLAN.md
"""

import pytest
from modules.selection_policy import band_sizes, classify_sorted_ids, cull_decision_to_pick_status


def test_band_sizes_small_values():
    """Verify band_sizes for small stack sizes."""
    assert band_sizes(0) == (0, 0)
    assert band_sizes(1) == (0, 0)
    assert band_sizes(2) == (0, 0)
    assert band_sizes(3) == (0, 0)  # floor(3*0.33)=0
    assert band_sizes(4) == (1, 1)   # floor(4*0.33)=1
    assert band_sizes(5) == (1, 1)
    assert band_sizes(6) == (1, 1)
    assert band_sizes(9) == (2, 2)
    assert band_sizes(10) == (3, 3)


def test_band_sizes_negative():
    """Negative or zero inputs return (0, 0)."""
    assert band_sizes(-1) == (0, 0)


def test_classify_sorted_ids_deterministic():
    """Same input must produce same output (deterministic)."""
    ids = [10, 11, 12, 13, 14, 15]
    out1 = classify_sorted_ids(ids)
    out2 = classify_sorted_ids(ids)
    assert out1 == out2


def test_classify_sorted_ids_n1():
    """Stack of 1: neutral."""
    out = classify_sorted_ids([42])
    assert out == {42: "neutral"}


def test_classify_sorted_ids_n2():
    """Stack of 2: 1 pick, 1 neutral."""
    out = classify_sorted_ids([10, 11])
    assert out == {10: "pick", 11: "neutral"}


def test_classify_sorted_ids_n4():
    """Stack of 4: 1 pick, 2 neutral, 1 reject."""
    out = classify_sorted_ids([10, 11, 12, 13])
    assert out[10] == "pick"
    assert out[11] == "neutral"
    assert out[12] == "neutral"
    assert out[13] == "reject"


def test_classify_sorted_ids_n10():
    """Stack of 10: 3 pick, 4 neutral, 3 reject."""
    ids = list(range(100, 110))
    out = classify_sorted_ids(ids)
    picks = [k for k, v in out.items() if v == "pick"]
    rejects = [k for k, v in out.items() if v == "reject"]
    neutral = [k for k, v in out.items() if v == "neutral"]
    assert len(picks) == 3
    assert len(rejects) == 3
    assert len(neutral) == 4
    assert picks == [100, 101, 102]
    assert rejects == [107, 108, 109]


def test_cull_decision_to_pick_status_mapping():
    assert cull_decision_to_pick_status("pick") == 1
    assert cull_decision_to_pick_status("reject") == -1
    assert cull_decision_to_pick_status("neutral") == 0
    assert cull_decision_to_pick_status("PICK") == 1
    assert cull_decision_to_pick_status("maybe") is None


def test_classify_sorted_ids_tie_scenario():
    """Ties are handled by caller (sort order). Policy just uses position."""
    # Caller sorts by score DESC, created_at ASC, id ASC
    # So IDs here represent that order; policy assigns by position only
    ids = [1, 2, 3, 4, 5]
    out = classify_sorted_ids(ids)
    assert out[1] == "pick"
    assert out[5] == "reject"
