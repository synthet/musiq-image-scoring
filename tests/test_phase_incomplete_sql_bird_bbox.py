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
    assert "COALESCE(i.bird_bbox->>'error', '') IN ('detector_unavailable')" in sql
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


def test_bird_bbox_needs_scan_sql_is_null_safe():
    """``NOT (gap)`` must be FALSE, never NULL, for a row holding a real box.

    ``bird_bbox->>'error'`` is NULL for a real box and for ``{"detected": false}``, and
    ``NULL IN (...)`` evaluates to NULL. The folder rollup negates this expression, so
    without COALESCE every boxed image silently stopped counting toward done_count.
    """
    with patch.object(db, "_get_db_engine", return_value="postgres"):
        sql = db._sql_bird_bbox_needs_scan("i")
    assert "COALESCE(i.bird_bbox->>'error', '')" in sql


def test_bird_bbox_needs_scan_sql_honours_empty_alias():
    with patch.object(db, "_get_db_engine", return_value="postgres"):
        sql = db._sql_bird_bbox_needs_scan("")
    assert "(bird_bbox IS NULL" in sql
    assert "i.bird_bbox" not in sql


# ──────────────────────────────────────────────────────────────────────────────
# Folder rollup — the predicate above is only half the story. The Dashboard bucket
# comes from get_folder_phase_summary, which counts IPS rows; without the same
# bbox condition there a box gap stays invisible to Drive to Complete.
# ──────────────────────────────────────────────────────────────────────────────

class _CapturingConnector:
    """Minimal connector stub that records the aggregate SQL."""

    def __init__(self):
        self.queries = []

    def query_one(self, sql, params=None):
        if "phase_agg_dirty" in sql:
            return {"phase_agg_dirty": 1, "phase_agg_json": None}
        return None

    def query(self, sql, params=None):
        self.queries.append(sql)
        return []

    def execute(self, sql, params=None):
        return None


def _aggregate_sql(monkeypatch, engine: str) -> str:
    cap = _CapturingConnector()
    monkeypatch.setattr(db, "get_connector", lambda: cap)
    monkeypatch.setattr(db, "get_or_create_folder", lambda path: 1)
    monkeypatch.setattr(db, "_get_db_engine", lambda: engine)
    monkeypatch.setattr(db, "_images_table_has_legacy_keywords_column", lambda: False)
    db.get_folder_phase_summary("/mnt/d/Photos/x")
    assert cap.queries, "aggregate query was never issued"
    return cap.queries[-1]


def test_folder_rollup_excludes_bbox_gap_from_done_and_skipped(monkeypatch):
    sql = _aggregate_sql(monkeypatch, "postgres")
    # bird_bbox must be projected by the inner image subquery to be referenceable.
    assert "SELECT id, bird_bbox FROM images" in sql
    assert sql.count("i.bird_bbox IS NULL") == 2, (
        "the gap must gate both done_count and skipped_count"
    )
    # Both terminal counters must be negated by the gap, not merely mention it.
    assert sql.count("NOT ((LOWER(TRIM(pp.code)) = 'bird_species'") == 2


def test_folder_rollup_leaves_firebird_untouched(monkeypatch):
    sql = _aggregate_sql(monkeypatch, "firebird")
    assert "bird_bbox" not in sql
    assert "SELECT id FROM images" in sql
