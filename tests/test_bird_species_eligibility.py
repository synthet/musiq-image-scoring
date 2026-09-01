"""Tests for bird species eligibility markers and incomplete SQL."""

from __future__ import annotations

from modules import db_legacy
from modules.bird_species_eligibility import (
    BIRD_SPECIES_NO_MATCH_SKIP_REASON,
    BIRDS_SPECIES_EXHAUSTED_NORM,
    BirdSpeciesEligibility,
    build_bird_species_keyword_csv,
    classify_image_row,
    ensure_birds_discovery_keyword,
    mark_species_classified_done,
    mark_species_exhausted,
    strip_legacy_exhausted_keyword,
)


def test_bird_species_incomplete_sql_excludes_exhausted_ips():
    sql = db_legacy.get_phase_incomplete_sql("bird_species", "i")
    assert "image_phase_status" in sql
    assert BIRD_SPECIES_NO_MATCH_SKIP_REASON in sql
    assert "birds:species-exhausted" not in sql or "OR" in sql


def test_classify_image_row_pending_vs_exhausted():
    assert (
        classify_image_row(
            image_id=1,
            has_birds=True,
            has_species=False,
            has_exhausted_marker=False,
            ips_status="not_started",
        )
        == BirdSpeciesEligibility.PENDING
    )
    assert (
        classify_image_row(
            image_id=2,
            has_birds=True,
            has_species=False,
            has_exhausted_marker=True,
            ips_status="done",
        )
        == BirdSpeciesEligibility.EXHAUSTED
    )
    assert (
        classify_image_row(
            image_id=4,
            has_birds=True,
            has_species=False,
            has_exhausted_marker=False,
            ips_status="skipped",
            ips_skip_reason=BIRD_SPECIES_NO_MATCH_SKIP_REASON,
        )
        == BirdSpeciesEligibility.EXHAUSTED
    )
    assert (
        classify_image_row(
            image_id=3,
            has_birds=False,
            has_species=False,
            has_exhausted_marker=False,
            ips_status=None,
        )
        == BirdSpeciesEligibility.NOT_IN_SCOPE
    )


def test_exhausted_keyword_constant():
    assert BIRDS_SPECIES_EXHAUSTED_NORM == "birds:species-exhausted"


def test_ensure_birds_discovery_keyword_idempotent():
    assert ensure_birds_discovery_keyword(["nature"]) == ["nature", "birds"]
    assert ensure_birds_discovery_keyword(["birds", "nature"]) == ["birds", "nature"]


def test_strip_legacy_exhausted_keyword():
    out = strip_legacy_exhausted_keyword(["birds", BIRDS_SPECIES_EXHAUSTED_NORM, "nature"])
    assert out == ["birds", "nature"]


def test_build_bird_species_keyword_csv_preserves_birds(monkeypatch):
    import modules.db as _db

    monkeypatch.setattr(
        _db,
        "get_resolved_image_keywords",
        lambda image_id, legacy_fallback=None, hide_internal=True: "birds,travel,species:Old Match",
    )
    merged = build_bird_species_keyword_csv(
        42,
        legacy_csv="",
        new_species=["species:American Robin"],
    )
    assert "birds" in merged
    assert "travel" in merged
    assert "species:American Robin" in merged
    assert "species:Old Match" not in merged
    assert BIRDS_SPECIES_EXHAUSTED_NORM not in merged


def test_mark_species_exhausted_ips_only(monkeypatch):
    import modules.db as _db

    kw_calls = []
    status_calls = []
    monkeypatch.setattr(
        _db,
        "update_image_keywords_for_image",
        lambda *a, **k: kw_calls.append((a, k)),
    )
    monkeypatch.setattr(
        _db,
        "set_image_phase_status",
        lambda *a, **k: status_calls.append((a, k)),
    )
    assert mark_species_exhausted(99) is True
    assert kw_calls == []
    assert len(status_calls) == 1
    args, kwargs = status_calls[0]
    assert args[0] == 99
    assert args[1] == "bird_species"
    assert args[2] == "skipped"
    assert kwargs.get("skip_reason") == BIRD_SPECIES_NO_MATCH_SKIP_REASON


def test_mark_species_classified_done_dry_run_skips_write():
    from modules import db

    called = []
    original = db.set_image_phase_status
    db.set_image_phase_status = lambda *a, **k: called.append((a, k))  # type: ignore[assignment]
    try:
        assert mark_species_classified_done(123, dry_run=True) is True
    finally:
        db.set_image_phase_status = original  # type: ignore[assignment]
    assert called == []


def test_mark_species_classified_done_writes_done_row():
    from modules import db

    captured = []
    original = db.set_image_phase_status
    db.set_image_phase_status = lambda *a, **k: captured.append((a, k))  # type: ignore[assignment]
    try:
        assert mark_species_classified_done(456) is True
    finally:
        db.set_image_phase_status = original  # type: ignore[assignment]
    assert len(captured) == 1
    args, kwargs = captured[0]
    assert args[0] == 456
    assert args[1] == "bird_species"
    assert args[2] == "done"
    assert kwargs.get("executor_version")


def test_folder_phase_summary_counts_classified_without_ips_row():
    """The bird_species aggregate must treat species:* images with no phase row as done."""
    import inspect

    src = inspect.getsource(db_legacy.get_folder_phase_summary)
    assert "bs_done_extra" in src
    assert "ips.status IS NULL" in src
    assert "species:%" in src
