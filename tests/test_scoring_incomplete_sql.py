"""Scoring incompleteness SQL used by workflow healing and folder status."""

from unittest.mock import patch

from modules import db, db_legacy


def test_incomplete_sql_aligns_with_is_image_scoring_complete_semantics():
    """At least one model > 0; do not require every model, score_technical, or score_general."""
    sql = db._incomplete_images_where_sql("i")
    assert "i.score_spaq IS NOT NULL AND i.score_spaq > 0" in sql
    assert "NOT (" in sql
    # Aggregates and legacy fields must not appear in the predicate (#162).
    assert "score_general" not in sql
    assert "score_technical" not in sql
    assert "i.score IS NULL" not in sql


def test_incomplete_sql_omits_score_general_clause_issue_162():
    """Regression for #162: score_general must not gate scoring completeness.

    An image whose aggregate weighted score happens to be 0.0 (e.g. because the
    technical sub-aggregate is 0.0) but with at least one successful per-model
    score must NOT be flagged as scoring_incomplete. The audit predicate must
    therefore not reference score_general at all.
    """
    for alias in ("", "i", "img"):
        sql = db._incomplete_images_where_sql(alias)
        prefix = f"{alias}." if alias else ""
        assert f"{prefix}score_general" not in sql, (
            f"score_general leaked into predicate with alias={alias!r}: {sql}"
        )


def test_is_image_scoring_complete_accepts_zero_general_with_positive_model_issue_162():
    """Regression for #162: row with score_general=0 but score_liqe>0 is complete.

    Reproduces the evidence from issue #162 (image 153393): the scorer ran
    successfully (score_liqe=0.36) but the derived weighted score_general
    happened to be 0. Previously this returned False, causing an infinite heal
    loop. It must now return True.
    """
    row = {
        "score_spaq": None,
        "score_ava": None,
        "score_paq2piq": None,
        "score_liqe": 0.36,
    }
    with patch.object(db_legacy, "get_connector") as gc:
        gc.return_value.query_one.return_value = row
        assert db.is_image_scoring_complete(153393) is True


def test_is_image_scoring_complete_false_when_no_model_scored():
    """Sanity: an image with no positive per-model score is still incomplete."""
    row = {
        "score_spaq": None,
        "score_ava": 0.0,
        "score_paq2piq": None,
        "score_liqe": None,
    }
    with patch.object(db_legacy, "get_connector") as gc:
        gc.return_value.query_one.return_value = row
        assert db.is_image_scoring_complete(1) is False


def test_is_image_scoring_complete_false_when_image_missing():
    """Sanity: missing row → not complete."""
    with patch.object(db_legacy, "get_connector") as gc:
        gc.return_value.query_one.return_value = None
        assert db.is_image_scoring_complete(999_999) is False


def test_canon_path_matches_wsl_and_windows():
    from modules import workflow_healing as wh

    a = wh._canon_path_for_active_match("/mnt/d/Photos/Z8/test")
    b = wh._canon_path_for_active_match("D:\\Photos\\Z8\\test")
    assert a == b
    assert a.endswith("/photos/z8/test")
