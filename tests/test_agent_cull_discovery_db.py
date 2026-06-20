"""SQL placeholder parity for agent cull discovery queries."""

from modules.agent_cull import discovery_db
from modules.agent_cull.discovery import ReviewUnit
from modules.agent_cull.discovery_db import _stack_member_query, load_unit_rows
from modules.db_legacy import _count_placeholders_firebird_style


def test_stack_member_query_placeholders_match_params_with_stack_filter():
    sql, params = _stack_member_query(folder_id=42, stack_id=28556)
    assert _count_placeholders_firebird_style(sql) == len(params)
    assert "ORDER BY kd.keyword_display" in sql
    assert " AND i.stack_id = ?" in sql


def test_stack_member_query_placeholders_match_params_without_stack_filter():
    sql, params = _stack_member_query(folder_id=None, stack_id=None)
    assert _count_placeholders_firebird_style(sql) == len(params)
    assert " AND i.stack_id = ?" not in sql


def test_load_unit_rows_selects_technical_and_exif(monkeypatch):
    captured: dict[str, object] = {}

    class _FakeConn:
        def query(self, sql, params):
            captured["sql"] = sql
            captured["params"] = params
            return [
                {
                    "id": 10, "pick_status": 1, "cull_decision": "pick",
                    "file_path": "/x/a.nef", "file_name": "a.nef", "file_type": "nef",
                    "thumbnail_path": None, "thumbnail_path_win": None,
                    "score_general": 0.8, "score_technical": 0.7,
                    "score_aesthetic": 0.6, "score": 0.7,
                    "blur": 0.1, "overexposed": 0.0, "underexposed": 0.0,
                    "make": "NIKON", "model": "Z9", "lens_model": "200mm",
                    "date_time_original": None, "orientation": 1,
                    "keywords": "",
                }
            ]

    monkeypatch.setattr(discovery_db, "require_postgres", lambda: None)
    monkeypatch.setattr(discovery_db.db, "get_connector", lambda: _FakeConn())

    unit = ReviewUnit(
        stack_id=1, sub_stack_id=None, review_unit_key="stack:1",
        image_ids=(10,), picked_ids=(10,), rejected_ids=(), neutral_ids=(),
        usable_ids=(10,), hierarchy_tier="flat_root",
    )
    out = load_unit_rows(unit)

    sql = captured["sql"]
    assert "image_technical_failures" in sql
    assert "image_exif" in sql
    assert "tf.blur" in sql and "ex.lens_model" in sql
    # New joins add no new bind params -> placeholder parity preserved.
    assert _count_placeholders_firebird_style(sql) == len(captured["params"])
    assert out[10]["blur"] == 0.1 and out[10]["make"] == "NIKON"
