"""Unit tests for bird_species folder phase aggregation helpers (no DB)."""

from __future__ import annotations

from modules import db_legacy


def test_sql_image_has_birds_keyword_uses_normalized_and_legacy(monkeypatch):
    monkeypatch.setattr(db_legacy, "_images_table_has_legacy_keywords_column", lambda: True)
    sql = db_legacy._sql_image_has_birds_keyword("i")
    assert "image_keywords" in sql
    assert "keywords_dim" in sql
    assert "%birds%" in sql
    assert "i.keywords" in sql


def test_sql_image_has_birds_keyword_normalized_only_without_legacy_column(monkeypatch):
    monkeypatch.setattr(db_legacy, "_images_table_has_legacy_keywords_column", lambda: False)
    sql = db_legacy._sql_image_has_birds_keyword("i")
    assert "image_keywords" in sql
    assert "keywords_dim" in sql
    assert "i.keywords" not in sql


def test_bird_species_incomplete_sql_requires_birds_and_missing_species():
    sql = db_legacy.get_phase_incomplete_sql("bird_species", "i")
    assert "species:%" in sql
    assert "birds" in sql.lower()


def test_bird_species_incomplete_sql_normalized_only_without_legacy_column(monkeypatch):
    monkeypatch.setattr(db_legacy, "_images_table_has_legacy_keywords_column", lambda: False)
    sql = db_legacy.get_phase_incomplete_sql("bird_species", "i")
    assert "image_keywords" in sql
    assert "i.keywords" not in sql


def test_keywords_incomplete_sql_normalized_only_without_legacy_column(monkeypatch):
    monkeypatch.setattr(db_legacy, "_images_table_has_legacy_keywords_column", lambda: False)
    sql = db_legacy.get_phase_incomplete_sql("keywords", "i")
    assert "image_keywords" in sql
    assert "i.keywords" not in sql


def test_keywords_incomplete_sql_includes_legacy_when_column_present(monkeypatch):
    monkeypatch.setattr(db_legacy, "_images_table_has_legacy_keywords_column", lambda: True)
    sql = db_legacy.get_phase_incomplete_sql("keywords", "i")
    assert "image_keywords" in sql
    assert "i.keywords" in sql


def test_bird_species_in_scope_matches_birds_predicate():
    assert db_legacy._sql_bird_species_in_scope("i") == db_legacy._sql_image_has_birds_keyword("i")


def test_is_postgres_missing_keywords_column_error():
    err = Exception("column i.keywords does not exist\nLINE 11: ...")
    assert db_legacy._is_postgres_missing_keywords_column_error(err) is True
    assert db_legacy._is_postgres_missing_keywords_column_error(Exception("timeout")) is False


def test_reset_postgres_keywords_column_cache_clears_stale_flag():
    db_legacy._pg_images_keywords_column_exists = True
    db_legacy.reset_postgres_keywords_column_cache()
    assert db_legacy._pg_images_keywords_column_exists is None


def test_pin_postgres_keywords_column_absent_blocks_legacy_sql():
    db_legacy._pin_postgres_keywords_column_absent()
    assert db_legacy._images_table_has_legacy_keywords_column() is False
    assert "i.keywords" not in db_legacy._sql_image_has_birds_keyword("i")


def test_init_db_resets_postgres_keywords_column_cache(monkeypatch):
    db_legacy._pg_images_keywords_column_exists = True
    db_legacy.reset_init_db_state_for_tests()
    monkeypatch.setattr(db_legacy, "_get_db_engine", lambda: "postgres")
    monkeypatch.setattr(db_legacy, "get_db", lambda: type("C", (), {"close": lambda s: None})())
    monkeypatch.setattr(db_legacy.db_postgres, "init_db", lambda: None)
    monkeypatch.setattr(db_legacy, "seed_pipeline_phases", lambda: None)

    db_legacy.init_db()

    assert db_legacy._pg_images_keywords_column_exists is None


def _summary_row(code: str = "scoring", **overrides):
    base = {
        "code": code,
        "name": "Quality Analysis",
        "sort_order": 3,
        "total_images": 2,
        "done_count": 2,
        "failed_count": 0,
        "running_count": 0,
        "queued_count": 0,
        "paused_count": 0,
        "cancel_requested_count": 0,
        "restarting_count": 0,
        "skipped_count": 0,
        "optional": 0,
    }
    base.update(overrides)
    return base


class _FakeConnector:
    def __init__(self, query_fn):
        self._query_fn = query_fn

    def query(self, sql, params=None):
        return self._query_fn(sql, params)

    def query_one(self, sql, params=None):
        return None

    def execute(self, sql, params=None):
        return 0


def test_get_folder_phase_summary_retries_after_missing_keywords_column(monkeypatch):
    """Stale cache + dropped column: first query fails, pin False, second omits i.keywords."""
    db_legacy._pg_images_keywords_column_exists = True
    captured_sql: list[str] = []

    def fake_query(sql, params=None):
        captured_sql.append(sql)
        if "i.keywords" in sql:
            raise Exception("column i.keywords does not exist\nLINE 11: ...")
        return [_summary_row()]

    monkeypatch.setattr(
        db_legacy,
        "get_connector",
        lambda: _FakeConnector(fake_query),
    )
    monkeypatch.setattr(db_legacy, "get_or_create_folder", lambda _path: 42)
    monkeypatch.setattr(db_legacy, "_get_db_engine", lambda: "postgres")
    monkeypatch.setattr(db_legacy, "_heal_stale_phase_flags", lambda _path: 0)
    # Catalog probe claims column exists; pin after runtime error must still win.
    monkeypatch.setattr(
        db_legacy.db_postgres,
        "execute_select_one",
        lambda *a, **k: {"x": 1},
    )

    result = db_legacy.get_folder_phase_summary("/mnt/d/Photos/test", force_refresh=True)

    assert len(captured_sql) == 2
    assert "i.keywords" in captured_sql[0]
    assert "i.keywords" not in captured_sql[1]
    assert len(result) == 1
    assert result[0]["code"] == "scoring"
    assert result[0]["status"] == "done"
    assert db_legacy._pg_images_keywords_column_exists is False


def test_get_folder_phase_summary_does_not_retry_on_unrelated_db_error(monkeypatch):
    db_legacy._pg_images_keywords_column_exists = True

    def fake_query(sql, params=None):
        raise Exception("connection refused")

    monkeypatch.setattr(
        db_legacy,
        "get_connector",
        lambda: _FakeConnector(fake_query),
    )
    monkeypatch.setattr(db_legacy, "get_or_create_folder", lambda _path: 42)
    monkeypatch.setattr(db_legacy, "_get_db_engine", lambda: "postgres")
    monkeypatch.setattr(db_legacy, "_heal_stale_phase_flags", lambda _path: 0)

    result = db_legacy.get_folder_phase_summary("/mnt/d/Photos/test", force_refresh=True)

    assert result == []


def test_postgres_images_has_keywords_column_probes_schema_once(monkeypatch):
    db_legacy.reset_postgres_keywords_column_cache()
    calls = {"n": 0}

    def fake_probe(*_args, **_kwargs):
        calls["n"] += 1
        return {"x": 1}

    monkeypatch.setattr(db_legacy, "_get_db_engine", lambda: "postgres")
    monkeypatch.setattr(db_legacy.db_postgres, "execute_select_one", fake_probe)

    assert db_legacy._postgres_images_has_keywords_column() is True
    assert db_legacy._postgres_images_has_keywords_column() is True
    assert calls["n"] == 1

    db_legacy.reset_postgres_keywords_column_cache()
