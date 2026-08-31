"""The bird_species incomplete predicate must also count a missing bird box.

``images.bird_bbox`` is produced inside the ``bird_species`` phase, so a birds-tagged
image that never got a box still owes work — otherwise auto-drive can never see it and
only ``scripts/backfill_bird_bbox.py`` can repair it.
"""

from unittest.mock import patch

from modules import db_legacy as db


def _sql(engine: str, *, legacy_keywords: bool = False) -> str:
    with patch.object(db, "_get_db_engine", return_value=engine), patch.object(
        db, "_images_table_has_legacy_keywords_column", return_value=legacy_keywords
    ):
        return db.get_phase_incomplete_sql("bird_species", table_alias="i")


def test_bird_species_incomplete_sql_includes_bbox_gap_on_postgres():
    sql = _sql("postgres")
    assert "i.bird_bbox IS NULL" in sql
    assert "i.bird_bbox->>'error' IN ('detector_unavailable')" in sql
    # Still the species predicate it always was.
    assert "species:%" in sql
    assert "birds:species-exhausted" in sql


def test_bird_species_incomplete_sql_omits_bbox_gap_on_firebird():
    # ``bird_bbox`` is a Postgres-only JSONB column and ``->>`` is not translated.
    sql = _sql("firebird", legacy_keywords=True)
    assert "bird_bbox" not in sql
    assert "1=0" in sql


def test_bird_species_incomplete_sql_retryable_list_tracks_the_module():
    from modules.bird_detection import RETRYABLE_BBOX_ERRORS

    sql = _sql("postgres")
    for err in RETRYABLE_BBOX_ERRORS:
        assert f"'{err}'" in sql
    # Data-terminal reasons must never be re-queued.
    assert "decode_error" not in sql
    assert "file_missing" not in sql


def test_bird_bbox_needs_scan_sql_honours_empty_alias():
    with patch.object(db, "_get_db_engine", return_value="postgres"):
        sql = db._sql_bird_bbox_needs_scan("")
    assert "(bird_bbox IS NULL" in sql
    assert "i.bird_bbox" not in sql
