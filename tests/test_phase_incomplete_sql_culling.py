"""Sanity checks for culling incompleteness SQL used by workflow healing."""

from unittest.mock import patch

from modules import db_legacy as db


def test_get_phase_incomplete_sql_culling_missing_decision_always_included():
    sql = db.get_phase_incomplete_sql("culling", table_alias="i")
    assert "cull_decision IS NULL" in sql or "TRIM(CAST(i.cull_decision" in sql


def test_get_phase_incomplete_sql_culling_similarity_stale_branch():
    with patch.object(db, "_get_db_engine", return_value="postgres"):
        sql = db.get_phase_incomplete_sql("culling", table_alias="i")
    assert "i.stack_id IS NULL" in sql
    assert "i.image_hash IS NOT NULL" in sql
    assert "image_embeddings" in sql

    with patch.object(db, "_get_db_engine", return_value="firebird"):
        sql_fb = db.get_phase_incomplete_sql("culling", table_alias="i")
    assert "i.stack_id IS NULL" in sql_fb
    assert "i.image_embedding IS NULL" in sql_fb


def test_get_phase_incomplete_sql_culling_time_cohesion_branch_postgres():
    with patch("modules.config.get_config_section", return_value={
        "heal_folder_cohesion_candidates": True,
        "default_time_gap": 7.0,
    }):
        with patch.object(db, "_get_db_engine", return_value="postgres"):
            sql = db.get_phase_incomplete_sql("culling", table_alias="i")
    assert "_fcd" in sql
    assert "i3.folder_id" in sql and "i.folder_id" in sql
    assert "EXTRACT(EPOCH FROM" in sql
    assert "7.0" in sql


def test_get_phase_incomplete_sql_culling_time_cohesion_branch_firebird_span():
    with patch("modules.config.get_config_section", return_value={
        "heal_folder_cohesion_candidates": True,
        "default_time_gap": 4.0,
    }):
        with patch.object(db, "_get_db_engine", return_value="firebird"):
            sql = db.get_phase_incomplete_sql("culling", table_alias="i")
    assert "_fcd" in sql
    assert "DATEDIFF" in sql


def test_get_phase_incomplete_sql_culling_cohesion_can_disable():
    with patch("modules.config.get_config_section", return_value={
        "heal_folder_cohesion_candidates": False,
        "default_time_gap": 120,
    }):
        with patch.object(db, "_get_db_engine", return_value="postgres"):
            sql = db.get_phase_incomplete_sql("culling", table_alias="i")
    assert "_fcd" not in sql
