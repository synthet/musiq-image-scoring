"""Scoring incompleteness SQL used by workflow healing and folder status."""

from unittest.mock import patch

from modules import db, db_legacy


def test_incomplete_sql_postgres_uses_image_model_scores():
    """On PostgreSQL the predicate joins ``image_model_scores`` (migration 0016)."""
    with patch.object(db_legacy, "_get_db_engine", return_value="postgres"):
        sql = db._incomplete_images_where_sql("i")
    assert "EXISTS" in sql and "image_model_scores ims" in sql
    assert "ims.image_id = i.id" in sql
    assert "ims.status = 'success'" in sql
    assert "ims.is_shadow = FALSE" in sql
    for name in ("spaq", "ava", "liqe", "paq2piq", "koniq"):
        assert f"'{name}'" in sql
    # Aggregates and legacy typed columns must not appear (#162 + IMS migration).
    assert "score_general" not in sql
    assert "score_technical" not in sql
    assert "i.score_spaq" not in sql


def test_incomplete_sql_firebird_falls_back_to_typed_columns():
    """Firebird has no image_model_scores; predicate keeps the legacy fallback."""
    with patch.object(db_legacy, "_get_db_engine", return_value="firebird"):
        sql = db._incomplete_images_where_sql("i")
    assert "image_model_scores" not in sql
    assert "i.score_spaq IS NOT NULL AND i.score_spaq > 0" in sql
    assert "NOT (" in sql


def test_incomplete_sql_omits_score_general_clause_issue_162():
    """Regression for #162: score_general must never gate scoring completeness."""
    for engine in ("postgres", "firebird"):
        with patch.object(db_legacy, "_get_db_engine", return_value=engine):
            for alias in ("", "i", "img"):
                sql = db._incomplete_images_where_sql(alias)
                prefix = f"{alias}." if alias else ""
                assert f"{prefix}score_general" not in sql, (
                    f"score_general leaked with engine={engine} alias={alias!r}: {sql}"
                )


def test_is_image_scoring_complete_true_when_postgres_ims_row_exists_issue_162():
    """Regression for #162: with score_general=0 but a positive per-model score in IMS, complete."""
    with patch.object(db_legacy, "_get_db_engine", return_value="postgres"), \
         patch.object(db_legacy, "get_connector") as gc:
        gc.return_value.query_one.return_value = {"hit": 1}
        assert db.is_image_scoring_complete(153393) is True
        called_sql = gc.return_value.query_one.call_args.args[0]
        assert "image_model_scores" in called_sql
        assert "is_shadow = FALSE" in called_sql


def test_is_image_scoring_complete_false_when_no_ims_row_postgres():
    """No production model row in IMS → not complete on Postgres."""
    with patch.object(db_legacy, "_get_db_engine", return_value="postgres"), \
         patch.object(db_legacy, "get_connector") as gc:
        gc.return_value.query_one.return_value = None
        assert db.is_image_scoring_complete(1) is False


def test_is_image_scoring_complete_firebird_uses_legacy_columns():
    """Firebird path still reads typed columns from the images row."""
    row = {
        "score_spaq": None,
        "score_ava": 0.0,
        "score_koniq": None,
        "score_paq2piq": None,
        "score_liqe": 0.36,
    }
    with patch.object(db_legacy, "_get_db_engine", return_value="firebird"), \
         patch.object(db_legacy, "get_connector") as gc:
        gc.return_value.query_one.return_value = row
        assert db.is_image_scoring_complete(42) is True
        called_sql = gc.return_value.query_one.call_args.args[0]
        assert "score_spaq" in called_sql
        assert "score_koniq" in called_sql
        assert "image_model_scores" not in called_sql


def test_is_image_scoring_complete_firebird_koniq_only_returns_true():
    """Image scored only by koniq must be reported complete (matches incomplete SQL)."""
    row = {
        "score_spaq": None,
        "score_ava": None,
        "score_koniq": 0.42,
        "score_paq2piq": None,
        "score_liqe": None,
    }
    with patch.object(db_legacy, "_get_db_engine", return_value="firebird"), \
         patch.object(db_legacy, "get_connector") as gc:
        gc.return_value.query_one.return_value = row
        assert db.is_image_scoring_complete(7) is True


def test_is_image_scoring_complete_firebird_false_without_positive_score():
    row = {
        "score_spaq": None,
        "score_ava": 0.0,
        "score_koniq": None,
        "score_paq2piq": None,
        "score_liqe": None,
    }
    with patch.object(db_legacy, "_get_db_engine", return_value="firebird"), \
         patch.object(db_legacy, "get_connector") as gc:
        gc.return_value.query_one.return_value = row
        assert db.is_image_scoring_complete(1) is False


def test_is_image_scoring_complete_firebird_false_when_image_missing():
    with patch.object(db_legacy, "_get_db_engine", return_value="firebird"), \
         patch.object(db_legacy, "get_connector") as gc:
        gc.return_value.query_one.return_value = None
        assert db.is_image_scoring_complete(999_999) is False


def test_canon_path_matches_wsl_and_windows():
    from modules import workflow_healing as wh

    a = wh._canon_path_for_active_match("/mnt/d/Photos/Z8/test")
    b = wh._canon_path_for_active_match("D:\\Photos\\Z8\\test")
    assert a == b
    assert a.endswith("/photos/z8/test")
