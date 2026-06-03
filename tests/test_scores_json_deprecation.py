"""Phase 1 deprecation tests for images.scores_json dual-write."""

import json

import pytest

from modules import db_legacy as dbl


def test_write_legacy_scores_json_column_defaults_true(monkeypatch):
    monkeypatch.setattr(
        "modules.db_legacy.config.get_config_value",
        lambda key, default=None: default,
    )
    monkeypatch.setattr("modules.db_legacy.config.get_database_engine", lambda: "postgres")
    dbl.reset_postgres_scores_json_column_cache()
    monkeypatch.setattr(dbl, "_postgres_images_has_scores_json_column", lambda: True)
    assert dbl._write_legacy_scores_json_column() is True


def test_write_legacy_scores_json_column_respects_config(monkeypatch):
    monkeypatch.setattr(
        "modules.db_legacy.config.get_config_value",
        lambda key, default=None: False if key == "database.write_legacy_scores_json_column" else default,
    )
    monkeypatch.setattr("modules.db_legacy.config.get_database_engine", lambda: "postgres")
    monkeypatch.setattr(dbl, "_postgres_images_has_scores_json_column", lambda: True)
    assert dbl._write_legacy_scores_json_column() is False


def test_write_legacy_scores_json_column_firebird_always_true(monkeypatch):
    monkeypatch.setattr(
        "modules.db_legacy.config.get_config_value",
        lambda key, default=None: False if key == "database.write_legacy_scores_json_column" else default,
    )
    monkeypatch.setattr("modules.db_legacy.config.get_database_engine", lambda: "firebird")
    assert dbl._write_legacy_scores_json_column() is True


def test_scores_json_column_value_none_when_dual_write_off(monkeypatch):
    monkeypatch.setattr(dbl, "_write_legacy_scores_json_column", lambda: False)
    result = {"models": {"spaq": {"score": 0.8, "status": "success"}}}
    assert dbl._scores_json_column_value(result) is None


def test_scores_json_column_value_serializes_when_dual_write_on(monkeypatch):
    monkeypatch.setattr(dbl, "_write_legacy_scores_json_column", lambda: True)
    result = {"models": {"spaq": {"score": 0.8, "status": "success"}}}
    blob = dbl._scores_json_column_value(result)
    assert blob is not None
    assert json.loads(blob) == result


@pytest.mark.parametrize("engine", ["postgres", "firebird"])
def test_scoring_outputs_present_sql_postgres_uses_image_model_scores(monkeypatch, engine):
    monkeypatch.setattr(dbl, "_get_db_engine", lambda: engine)
    sql = dbl._scoring_outputs_present_sql("i")
    if engine == "postgres":
        assert "image_model_scores" in sql
        assert "scores_json" not in sql
    else:
        assert "score_spaq" in sql
        assert "image_model_scores" not in sql


def test_salvage_subquery_uses_scoring_outputs_present(monkeypatch):
    monkeypatch.setattr(dbl, "_get_db_engine", lambda: "postgres")
    sub = dbl._salvage_scoring_outputs_image_ids_subquery()
    assert "FROM images i" in sub
    assert "image_model_scores" in sub


def test_get_scores_json_parity_report_column_dropped(monkeypatch):
    monkeypatch.setattr(dbl, "_get_db_engine", lambda: "postgres")
    monkeypatch.setattr(dbl, "_postgres_images_has_scores_json_column", lambda: False)
    report = dbl.get_scores_json_parity_report()
    assert report["legacy_column_dropped"] is True
    assert report["legacy_scores_json_rows"] == 0


def test_write_legacy_scores_json_column_false_when_column_dropped(monkeypatch):
    monkeypatch.setattr(dbl, "_get_db_engine", lambda: "postgres")
    monkeypatch.setattr(dbl, "_postgres_images_has_scores_json_column", lambda: False)
    assert dbl._write_legacy_scores_json_column() is False
