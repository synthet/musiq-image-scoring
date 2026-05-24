"""Tests for the image_model_scores read path (Part 2).

Hardware-free: stubs the DB connector; no Postgres needed. Covers the read
helpers in db_legacy and the API merge helper that flattens production scores
and keeps shadow scores in the structured block only.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from modules import db_legacy


class _FakeConn:
    def __init__(self, rows: List[Dict[str, Any]]) -> None:
        self._rows = rows
        self.last_sql = None
        self.last_params = None

    def query(self, sql: str, params=None):
        self.last_sql = sql
        self.last_params = params
        return self._rows


def _patch_conn(monkeypatch, rows):
    conn = _FakeConn(rows)
    monkeypatch.setattr(db_legacy, "get_connector", lambda: conn)
    return conn


_ROWS = [
    {"image_id": 1, "model_name": "topiq", "raw_score": 0.72, "normalized": 0.72, "status": "success", "is_shadow": False},
    {"image_id": 1, "model_name": "claude", "raw_score": 82.0, "normalized": 0.82, "status": "success", "is_shadow": True},
]


# --- get_image_model_scores ----------------------------------------------

def test_get_excludes_shadow_by_default(monkeypatch):
    _patch_conn(monkeypatch, _ROWS)
    out = db_legacy.get_image_model_scores(1)
    assert set(out) == {"topiq"}
    assert out["topiq"]["normalized"] == 0.72
    assert out["topiq"]["is_shadow"] is False


def test_get_includes_shadow_when_requested(monkeypatch):
    _patch_conn(monkeypatch, _ROWS)
    out = db_legacy.get_image_model_scores(1, include_shadow=True)
    assert set(out) == {"topiq", "claude"}
    assert out["claude"]["is_shadow"] is True


def test_get_none_id_returns_empty(monkeypatch):
    _patch_conn(monkeypatch, _ROWS)
    assert db_legacy.get_image_model_scores(None) == {}


def test_get_returns_empty_when_table_missing(monkeypatch):
    class _Boom:
        def query(self, *a, **k):
            raise RuntimeError("no such table")

    monkeypatch.setattr(db_legacy, "get_connector", lambda: _Boom())
    assert db_legacy.get_image_model_scores(1) == {}


# --- get_batch_image_model_scores ----------------------------------------

def test_batch_groups_by_image(monkeypatch):
    rows = _ROWS + [
        {"image_id": 2, "model_name": "topiq", "raw_score": 0.5, "normalized": 0.5, "status": "success", "is_shadow": False},
    ]
    _patch_conn(monkeypatch, rows)
    out = db_legacy.get_batch_image_model_scores([1, 2], include_shadow=True)
    assert set(out) == {1, 2}
    assert set(out[1]) == {"topiq", "claude"}
    assert set(out[2]) == {"topiq"}


def test_batch_empty_ids(monkeypatch):
    _patch_conn(monkeypatch, _ROWS)
    assert db_legacy.get_batch_image_model_scores([]) == {}


# --- API merge helper -----------------------------------------------------

def test_merge_helper_flattens_production_only():
    api = pytest.importorskip("modules.api")
    data = {"id": 1, "score_spaq": 60.0}
    ims = {
        "topiq": {"normalized": 0.72, "raw_score": 0.72, "status": "success", "is_shadow": False},
        "claude": {"normalized": 0.82, "raw_score": 82.0, "status": "success", "is_shadow": True},
        "spaq": {"normalized": 0.6, "raw_score": 60.0, "status": "success", "is_shadow": False},
    }
    api._merge_model_scores_into(data, ims)

    # Structured block carries everything (incl. shadow).
    assert set(data["model_scores"]) == {"topiq", "claude", "spaq"}
    # Production model without a legacy column → flat field.
    assert data["topiq_score"] == 0.72
    # Shadow engine → NOT flattened.
    assert "claude_score" not in data
    # Model with an existing legacy score_ column → not duplicated.
    assert "spaq_score" not in data


def test_merge_helper_noop_on_empty():
    api = pytest.importorskip("modules.api")
    data = {"id": 1}
    api._merge_model_scores_into(data, {})
    assert "model_scores" not in data


def test_merge_helper_overlays_null_legacy_columns_from_ims():
    """Once dual-writes stop, score_spaq is NULL on the row. Overlay IMS production value."""
    api = pytest.importorskip("modules.api")
    data = {"id": 5, "score_spaq": None, "score_ava": None, "score_liqe": None}
    ims = {
        "spaq": {"normalized": 0.7, "raw_score": 70.0, "status": "success", "is_shadow": False},
        "ava":  {"normalized": 0.55, "raw_score": 5.5, "status": "success", "is_shadow": False},
        "liqe": {"normalized": 0.81, "raw_score": 4.05, "status": "success", "is_shadow": False},
    }
    api._merge_model_scores_into(data, ims)

    assert data["score_spaq"] == 0.7
    assert data["score_ava"] == 0.55
    assert data["score_liqe"] == 0.81
    # No flat *_score duplicates for legacy-column models.
    for key in ("spaq_score", "ava_score", "liqe_score"):
        assert key not in data


def test_merge_helper_preserves_existing_legacy_column_value():
    """If the row still has a non-null typed value, do not clobber it."""
    api = pytest.importorskip("modules.api")
    data = {"id": 6, "score_spaq": 0.42}
    ims = {"spaq": {"normalized": 0.99, "raw_score": 99.0, "status": "success", "is_shadow": False}}
    api._merge_model_scores_into(data, ims)
    assert data["score_spaq"] == 0.42
