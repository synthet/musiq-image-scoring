"""Unit tests for JSON-safe API row serialization (pgvector / numpy in /api/db/query)."""

from __future__ import annotations

import datetime

import pytest

from modules.db_legacy import _json_safe_api_row, _json_safe_api_value


def test_json_safe_api_value_datetime():
    dt = datetime.datetime(2026, 5, 23, 12, 0, 0)
    assert _json_safe_api_value(dt) == "2026-05-23T12:00:00"


def test_json_safe_api_value_bytes_omitted():
    assert _json_safe_api_value(b"\x00\x01") is None


def test_json_safe_api_value_numpy_vector():
    np = pytest.importorskip("numpy")
    vec = np.array([0.1, 0.2, 0.3], dtype=np.float32)
    assert _json_safe_api_value(vec) == pytest.approx([0.1, 0.2, 0.3])


def test_json_safe_api_row():
    np = pytest.importorskip("numpy")
    row = {
        "id": 1,
        "image_embedding": np.array([1.0, 2.0], dtype=np.float32),
        "created_at": datetime.date(2026, 1, 1),
    }
    out = _json_safe_api_row(row)
    assert out["id"] == 1
    assert out["image_embedding"] == [1.0, 2.0]
    assert out["created_at"] == "2026-01-01"
