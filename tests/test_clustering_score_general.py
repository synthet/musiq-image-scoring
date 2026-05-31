"""Regression: clustering score lookups must not KeyError on thin image rows."""

from __future__ import annotations


def burst_id_to_score(group_rows: list[dict]) -> dict[int, float]:
    """Mirror clustering.py burst stack path (~line 752)."""
    return {r["id"]: r.get("score_general") or 0 for r in group_rows}


def batch_id_to_score(batch: list[tuple[dict, object]]) -> dict[int, float]:
    """Mirror clustering.py visual batch path (~line 918-920)."""
    out: dict[int, float] = {}
    for r, _t in batch:
        out[r["id"]] = r.get("score_general") or 0
    return out


def test_burst_score_dict_missing_score_general_key():
    rows = [{"id": 1}, {"id": 2}]
    assert burst_id_to_score(rows) == {1: 0, 2: 0}


def test_burst_score_dict_none_score_general():
    rows = [{"id": 1, "score_general": None}, {"id": 2, "score_general": 0.75}]
    assert burst_id_to_score(rows) == {1: 0, 2: 0.75}


def test_batch_score_dict_missing_score_general_key():
    batch = [({"id": 10}, None), ({"id": 11, "score_general": 0.4}, "tag")]
    assert batch_id_to_score(batch) == {10: 0, 11: 0.4}


def test_batch_score_dict_empty_score_general_treated_as_zero():
    batch = [({"id": 3, "score_general": None}, "x")]
    assert batch_id_to_score(batch)[3] == 0
