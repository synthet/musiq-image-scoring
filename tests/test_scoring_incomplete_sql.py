"""Scoring incompleteness SQL used by workflow healing and folder status."""

from modules import db


def test_incomplete_sql_aligns_with_is_image_scoring_complete_semantics():
    """At least one model > 0; do not require every model or score_technical."""
    sql = db._incomplete_images_where_sql("i")
    assert "i.score_general IS NULL OR i.score_general <= 0" in sql
    assert "i.score_spaq IS NOT NULL AND i.score_spaq > 0" in sql
    assert "OR NOT (" in sql
    assert "score_technical" not in sql
    assert "i.score IS NULL" not in sql


def test_canon_path_matches_wsl_and_windows():
    from modules import workflow_healing as wh

    a = wh._canon_path_for_active_match("/mnt/d/Photos/Z8/test")
    b = wh._canon_path_for_active_match("D:\\Photos\\Z8\\test")
    assert a == b
    assert a.endswith("/photos/z8/test")
