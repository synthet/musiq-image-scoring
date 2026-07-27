"""Bird Species ID eligibility — scope, pending work, and terminal no-match markers.

Images are in scope when tagged with a birds-related keyword (see ``_sql_image_has_birds_keyword``).
Species work is **pending** when in scope, no ``species:*`` keyword, and not marked
``birds:species-exhausted`` (BioCLIP found no prediction above threshold after a run).

Use the exhausted marker to exclude one-off misses from autodrive / folder backlog filters
without dropping the underlying ``birds`` tag used for discovery.
"""
from __future__ import annotations

from enum import Enum

# Canonical filter keyword (normalized to lowercase in keywords_dim).
BIRDS_SPECIES_EXHAUSTED_KEYWORD = "birds:species-exhausted"
BIRDS_SPECIES_EXHAUSTED_NORM = BIRDS_SPECIES_EXHAUSTED_KEYWORD.lower()


class BirdSpeciesEligibility(str, Enum):
    """Per-image classification for reporting and backfill."""

    NOT_IN_SCOPE = "not_in_scope"  # no birds tag — bird phase N/A
    COMPLETE = "complete"  # has species:* (or legacy species in keywords column)
    PENDING = "pending"  # birds, needs species run
    EXHAUSTED = "exhausted"  # attempted, no species — exclude from pending backlog
    FAILED = "failed"  # IPS failed — may retry
    SKIPPED_OTHER = "skipped_other"  # IPS skipped (e.g. file_missing) — review manually


def _sql_exhausted_marker(table_alias: str = "i") -> str:
    """True when the image carries the terminal no-match marker keyword."""
    from modules.db_legacy import _images_table_has_legacy_keywords_column

    prefix = f"{table_alias}." if table_alias else ""
    marker = BIRDS_SPECIES_EXHAUSTED_NORM.replace("'", "''")
    norm = f"""EXISTS (
        SELECT 1 FROM image_keywords ik_e
        JOIN keywords_dim kd_e ON kd_e.keyword_id = ik_e.keyword_id
        WHERE ik_e.image_id = {prefix}id
          AND kd_e.keyword_norm = '{marker}'
    )"""
    if not _images_table_has_legacy_keywords_column():
        return norm
    legacy = f"LOWER(CAST({prefix}keywords AS VARCHAR(2048))) LIKE '%birds:species-exhausted%'"
    return f"({norm} OR {legacy})"


def sql_bird_species_pending_predicate(table_alias: str = "i") -> str:
    """Images that still need (or may retry) species classification."""
    from modules.db_legacy import get_phase_incomplete_sql

    return f"({get_phase_incomplete_sql('bird_species', table_alias)})"


def classify_image_row(
    *,
    image_id: int,
    has_birds: bool,
    has_species: bool,
    has_exhausted_marker: bool,
    ips_status: str | None,
) -> BirdSpeciesEligibility:
    if not has_birds:
        return BirdSpeciesEligibility.NOT_IN_SCOPE
    if has_species:
        return BirdSpeciesEligibility.COMPLETE
    if has_exhausted_marker:
        return BirdSpeciesEligibility.EXHAUSTED
    st = (ips_status or "").strip().lower()
    if st == "failed":
        return BirdSpeciesEligibility.FAILED
    if st == "skipped":
        return BirdSpeciesEligibility.SKIPPED_OTHER
    return BirdSpeciesEligibility.PENDING


def mark_species_classified_done(image_id: int, *, dry_run: bool = False) -> bool:
    """Reconcile an already-classified image: set bird_species IPS to ``done``.

    For bird-tagged images that carry a ``species:*`` keyword (classified in an
    earlier run or import) but have **no** ``image_phase_status`` row for
    bird_species. Without a row the folder aggregate counts them as in-scope but
    not done, leaving the folder stuck in a phantom ``awaiting_bird_species``
    bucket (auto-drive churns ``nothing_to_queue`` on it forever). Writing the
    terminal ``done`` row makes per-image truth match keyword reality and marks
    the folder aggregate dirty so the bucket clears. Idempotent: callers select
    only rows missing the IPS row, and a re-run is a harmless ``done``→``done``.
    """
    if dry_run:
        return True
    from modules import db
    from modules.bird_species import BIRD_SPECIES_RUNNER_VERSION

    db.set_image_phase_status(
        image_id,
        "bird_species",
        "done",
        executor_version=BIRD_SPECIES_RUNNER_VERSION,
    )
    return True


def mark_species_exhausted(
    image_id: int,
    *,
    existing_keywords_csv: str = "",
    dry_run: bool = False,
) -> bool:
    """Tag an image as terminal no-match so backlog queries skip it."""
    from modules import db

    base = [k.strip() for k in (existing_keywords_csv or "").split(",") if k.strip()]
    if not any(k.lower() == BIRDS_SPECIES_EXHAUSTED_NORM for k in base):
        base.append(BIRDS_SPECIES_EXHAUSTED_KEYWORD)
    merged = ",".join(base)
    if dry_run:
        return True
    db.update_image_keywords_for_image(image_id, merged, source="auto")
    from modules.bird_species import BIRD_SPECIES_RUNNER_VERSION

    db.set_image_phase_status(
        image_id,
        "bird_species",
        "skipped",
        skip_reason="no_species_match",
        skipped_by="bird_species_eligibility",
        executor_version=BIRD_SPECIES_RUNNER_VERSION,
    )
    return True
