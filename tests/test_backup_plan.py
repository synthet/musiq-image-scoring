"""Unit tests for backup selection planning."""

from modules import backup_plan
from modules.backup_plan import (
    _backup_date_key,
    _compute_folder_threshold,
    _dedupe_pairs,
    _similar_pairs_in_group,
    _stack_prefilter,
)


def test_backup_date_key_prefers_capture_date():
    row = {"capture_date": "2025-02-01", "file_path": "/x/2020-01-01/a.jpg"}
    assert _backup_date_key(row) == "2025-02-01"


def test_backup_date_key_path_fallback():
    row = {"capture_date": "", "file_path": "/photos/2024-06-15/img.nef"}
    assert _backup_date_key(row) == "2024-06-15"


def test_stack_prefilter_keeps_top_two():
    group = [
        {"id": 1, "stack_id": 5, "score_general": 0.9},
        {"id": 2, "stack_id": 5, "score_general": 0.8},
        {"id": 3, "stack_id": 5, "score_general": 0.7},
    ]
    kept, rejected = _stack_prefilter(group, 2)
    assert len(kept) == 2
    assert rejected == 1
    assert {r["id"] for r in kept} == {1, 2}


def test_stack_prefilter_keeps_all_unstacked_singletons():
    # Unstacked images (stack_id None) are distinct photos — none may be rejected,
    # no matter how many share a date.
    group = [{"id": i, "stack_id": None, "score_general": 0.9 - i * 0.01} for i in range(10)]
    kept, rejected = _stack_prefilter(group, 2)
    assert rejected == 0
    assert {r["id"] for r in kept} == {r["id"] for r in group}


def test_stack_prefilter_mixed_null_and_real_stack():
    group = [
        {"id": 1, "stack_id": None, "score_general": 0.95},
        {"id": 2, "stack_id": None, "score_general": 0.90},
        {"id": 3, "stack_id": None, "score_general": 0.85},
        {"id": 4, "stack_id": 7, "score_general": 0.80},
        {"id": 5, "stack_id": 7, "score_general": 0.70},
        {"id": 6, "stack_id": 7, "score_general": 0.60},
    ]
    kept, rejected = _stack_prefilter(group, 2)
    # All 3 unstacked kept; real stack 7 trimmed to its top 2 (ids 4,5).
    assert rejected == 1
    assert {r["id"] for r in kept} == {1, 2, 3, 4, 5}


def test_burst_lowers_similarity_threshold():
    low = _compute_folder_threshold(100, 10, 0.5)
    high = _compute_folder_threshold(100, 80, 0.5)
    assert high < low


def test_dedupe_pairs_normalizes_and_dedupes():
    pairs = [
        {"id_a": 2, "id_b": 1, "similarity": 0.9},
        {"id_a": 1, "id_b": 2, "similarity": 0.9},
        {"id_a": 3, "id_b": 4, "similarity": 0.8},
    ]
    out = _dedupe_pairs(pairs)
    keys = {(p["id_a"], p["id_b"]) for p in out}
    assert keys == {(1, 2), (3, 4)}


def test_similar_pairs_finds_cross_batch_edges(monkeypatch):
    # With batch_size=2 over [1,2,3,4], a (1,3) duplicate spans two batches and is only
    # discoverable via the cross-batch combined query.
    def fake_query(ids, threshold):
        if 1 in ids and 3 in ids:
            return [{"id_a": 1, "id_b": 3, "similarity": 0.95}], None
        return [], None

    monkeypatch.setattr(backup_plan, "_query_similar_pairs", fake_query)
    pairs, err = _similar_pairs_in_group([1, 2, 3, 4], 0.9, batch_size=2)
    assert err is None
    assert {(p["id_a"], p["id_b"]) for p in pairs} == {(1, 3)}


def test_similar_pairs_propagates_first_error(monkeypatch):
    monkeypatch.setattr(
        backup_plan, "_query_similar_pairs", lambda ids, t: ([], "boom")
    )
    pairs, err = _similar_pairs_in_group([1, 2, 3, 4], 0.9, batch_size=2)
    assert pairs == []
    assert err == "boom"
