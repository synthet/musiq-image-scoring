"""Tests for bird species eligibility markers and incomplete SQL."""

from __future__ import annotations

from modules import db_legacy
from modules.bird_species_eligibility import (
    BIRDS_SPECIES_EXHAUSTED_NORM,
    BirdSpeciesEligibility,
    classify_image_row,
    mark_species_classified_done,
)


def test_bird_species_incomplete_sql_excludes_exhausted_marker():
    sql = db_legacy.get_phase_incomplete_sql("bird_species", "i")
    assert "birds:species-exhausted" in sql


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
