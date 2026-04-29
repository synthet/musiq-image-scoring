"""Unit tests for the image_model_scores dual-write helpers in db_legacy.

Covers the pure row-extractor and the engine-gating in _write_image_model_scores.
No real DB or pipeline dependencies.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple
from unittest.mock import patch

from modules import db_legacy


def _result_with_models(models: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    return {"version": "test", "models": models, "summary": {"total_models": len(models)}}


# ─── _extract_image_model_score_rows ──────────────────────────────────────

def test_extract_returns_empty_when_no_image_id():
    out = db_legacy._extract_image_model_score_rows(None, _result_with_models({"spaq": {}}), "v1")
    assert out == []


def test_extract_returns_empty_when_no_models_key():
    out = db_legacy._extract_image_model_score_rows(7, {"summary": {}}, "v1")
    assert out == []


def test_extract_returns_empty_when_models_empty():
    out = db_legacy._extract_image_model_score_rows(7, _result_with_models({}), "v1")
    assert out == []


def test_extract_skips_non_dict_payloads():
    result = _result_with_models({"image_hash": "abc123"})  # legacy stray key, not a dict
    result["models"]["image_hash"] = "abc123"
    out = db_legacy._extract_image_model_score_rows(7, result, "v1")
    assert out == []


def test_extract_success_payload_full_row():
    result = _result_with_models({
        "spaq": {
            "score": 72.5,
            "score_range": "0.0-100.0",
            "normalized_score": 0.725,
            "inference_time_seconds": 0.041,
            "status": "success",
        },
    })
    rows: List[Tuple] = db_legacy._extract_image_model_score_rows(42, result, "host-1.0.0")
    assert rows == [(42, "spaq", 72.5, 0.725, "success", False, "host-1.0.0")]


def test_extract_includes_failed_and_not_loaded_statuses():
    result = _result_with_models({
        "ava":   {"score": None, "status": "failed", "error": "boom"},
        "qpt":   {"score": None, "status": "not_loaded"},
        "spaq":  {"score": 50.0, "normalized_score": 0.5, "status": "success"},
    })
    rows = db_legacy._extract_image_model_score_rows(11, result, "v1")
    by_name = {r[1]: r for r in rows}
    assert by_name["ava"] == (11, "ava", None, None, "failed", False, "v1")
    assert by_name["qpt"] == (11, "qpt", None, None, "not_loaded", False, "v1")
    assert by_name["spaq"] == (11, "spaq", 50.0, 0.5, "success", False, "v1")


def test_extract_unknown_status_coerced_to_failed():
    result = _result_with_models({"weird": {"score": 1.0, "status": "interrupted"}})
    [(_, _, raw, _, status, *_)] = db_legacy._extract_image_model_score_rows(1, result, "v1")
    assert status == "failed"
    assert raw == 1.0


def test_extract_propagates_is_shadow_flag():
    result = _result_with_models({
        "spaq":   {"score": 10.0, "normalized_score": 0.1, "status": "success"},
        "qpt_v2": {"score": 4.0,  "normalized_score": 0.8, "status": "success", "is_shadow": True},
    })
    rows = db_legacy._extract_image_model_score_rows(99, result, "v1")
    by_name = {r[1]: r for r in rows}
    assert by_name["spaq"][5] is False
    assert by_name["qpt_v2"][5] is True


# ─── _write_image_model_scores (engine gating) ────────────────────────────

class _StubConnPostgres:
    type = "postgres"


class _StubConnFirebird:
    type = "firebird"


def test_write_no_op_when_engine_is_firebird():
    result = _result_with_models({"spaq": {"score": 1.0, "normalized_score": 0.01, "status": "success"}})
    with patch.object(db_legacy, "get_connector", return_value=_StubConnFirebird()), \
         patch.object(db_legacy.db_postgres, "execute_write") as exec_w:
        db_legacy._write_image_model_scores(7, result, "v1")
    exec_w.assert_not_called()


def test_write_no_op_when_no_rows_to_emit():
    with patch.object(db_legacy, "get_connector", return_value=_StubConnPostgres()), \
         patch.object(db_legacy.db_postgres, "execute_write") as exec_w:
        db_legacy._write_image_model_scores(7, {"summary": {}}, "v1")
    exec_w.assert_not_called()


def test_write_postgres_emits_one_execute_per_row():
    result = _result_with_models({
        "spaq": {"score": 70.0, "normalized_score": 0.7, "status": "success"},
        "ava":  {"score": 6.0,  "normalized_score": 0.55, "status": "success"},
        "liqe": {"score": 4.2,  "normalized_score": 0.8, "status": "success"},
    })
    with patch.object(db_legacy, "get_connector", return_value=_StubConnPostgres()), \
         patch.object(db_legacy.db_postgres, "execute_write") as exec_w:
        db_legacy._write_image_model_scores(123, result, "host-1")

    assert exec_w.call_count == 3
    names = sorted(call.args[1][1] for call in exec_w.call_args_list)
    assert names == ["ava", "liqe", "spaq"]
    sql_seen = exec_w.call_args_list[0].args[0]
    assert "INSERT INTO image_model_scores" in sql_seen
    assert "ON CONFLICT (image_id, model_name)" in sql_seen
    # Every call must pass exactly 7 bind params (image_id..model_version).
    for call in exec_w.call_args_list:
        assert len(call.args[1]) == 7


def test_write_swallows_per_row_db_errors():
    result = _result_with_models({
        "spaq": {"score": 1.0, "normalized_score": 0.01, "status": "success"},
        "ava":  {"score": 2.0, "normalized_score": 0.02, "status": "success"},
    })

    def _boom(_sql, _params):
        raise RuntimeError("connection lost")

    with patch.object(db_legacy, "get_connector", return_value=_StubConnPostgres()), \
         patch.object(db_legacy.db_postgres, "execute_write", side_effect=_boom):
        # Must not raise — failures are logged and ignored so a per-model write
        # error never blocks the surrounding transaction.
        db_legacy._write_image_model_scores(7, result, "v1")
