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


def test_bird_species_in_scope_matches_birds_predicate():
    assert db_legacy._sql_bird_species_in_scope("i") == db_legacy._sql_image_has_birds_keyword("i")
