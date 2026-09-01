"""Bird Species ID eligibility — scope, pending work, and terminal no-match state.

Images are in scope when tagged with a birds-related keyword (see ``_sql_image_has_birds_keyword``).
Species work is **pending** when in scope, no ``species:*`` keyword, and bird_species IPS is not
``skipped`` with ``skip_reason=no_species_match`` (BioCLIP found no prediction above threshold).

The no-match terminal state lives in ``image_phase_status`` only — not as a user-facing keyword.
The underlying ``birds`` tag is preserved for discovery and filtering.
"""
from __future__ import annotations

from enum import Enum

# Legacy keyword marker — migration/backfill strip only; never written on new runs.
BIRDS_SPECIES_EXHAUSTED_KEYWORD = "birds:species-exhausted"
BIRDS_SPECIES_EXHAUSTED_NORM = BIRDS_SPECIES_EXHAUSTED_KEYWORD.lower()
BIRDS_DISCOVERY_KEYWORD = "birds"
BIRD_SPECIES_NO_MATCH_SKIP_REASON = "no_species_match"


class BirdSpeciesEligibility(str, Enum):
    """Per-image classification for reporting and backfill."""

    NOT_IN_SCOPE = "not_in_scope"  # no birds tag — bird phase N/A
    COMPLETE = "complete"  # has species:* (or legacy species in keywords column)
    PENDING = "pending"  # birds, needs species run
    EXHAUSTED = "exhausted"  # attempted, no species — exclude from pending backlog
    FAILED = "failed"  # IPS failed — may retry
    SKIPPED_OTHER = "skipped_other"  # IPS skipped (e.g. file_missing) — review manually


def _keyword_list_from_csv(keywords_csv: str) -> list[str]:
    return [k.strip() for k in (keywords_csv or "").split(",") if k.strip()]


def has_birds_discovery_keyword(keywords: list[str]) -> bool:
    return any(k.lower() == BIRDS_DISCOVERY_KEYWORD for k in keywords)


def ensure_birds_discovery_keyword(keywords: list[str]) -> list[str]:
    """Append canonical ``birds`` when absent (idempotent)."""
    if has_birds_discovery_keyword(keywords):
        return keywords
    return [*keywords, BIRDS_DISCOVERY_KEYWORD]


def strip_legacy_exhausted_keyword(keywords: list[str]) -> list[str]:
    """Remove deprecated ``birds:species-exhausted`` marker from a keyword list."""
    return [k for k in keywords if k.lower() != BIRDS_SPECIES_EXHAUSTED_NORM]


def build_bird_species_keyword_csv(
    image_id: int,
    *,
    legacy_csv: str | None = None,
    new_species: list[str] | None = None,
) -> str:
    """Merge species tags onto resolved keywords and preserve ``birds``."""
    from modules import db

    resolved = db.get_resolved_image_keywords(
        int(image_id), legacy_fallback=legacy_csv, hide_internal=False
    )
    base = strip_legacy_exhausted_keyword(_keyword_list_from_csv(resolved))
    base = [k for k in base if not k.lower().startswith("species:")]
    if new_species:
        base.extend(new_species)
    base = ensure_birds_discovery_keyword(base)
    return ",".join(base)


def _sql_bird_species_exhausted_ips(table_alias: str = "i") -> str:
    """True when bird_species IPS records a terminal no-species-match skip."""
    prefix = f"{table_alias}." if table_alias else ""
    reason = BIRD_SPECIES_NO_MATCH_SKIP_REASON.replace("'", "''")
    return f"""EXISTS (
        SELECT 1 FROM image_phase_status ips_e
        JOIN pipeline_phases pp_e ON pp_e.id = ips_e.phase_id
        WHERE ips_e.image_id = {prefix}id
          AND LOWER(TRIM(pp_e.code)) = 'bird_species'
          AND LOWER(TRIM(ips_e.status)) = 'skipped'
          AND LOWER(TRIM(COALESCE(ips_e.skip_reason, ''))) = '{reason}'
    )"""


def _sql_exhausted_marker(table_alias: str = "i") -> str:
    """True when the image is terminal no-match (IPS primary; legacy keyword during migration)."""
    ips = _sql_bird_species_exhausted_ips(table_alias)
    from modules.db_legacy import _images_table_has_legacy_keywords_column

    prefix = f"{table_alias}." if table_alias else ""
    marker = BIRDS_SPECIES_EXHAUSTED_NORM.replace("'", "''")
    legacy_kw = f"""EXISTS (
        SELECT 1 FROM image_keywords ik_e
        JOIN keywords_dim kd_e ON kd_e.keyword_id = ik_e.keyword_id
        WHERE ik_e.image_id = {prefix}id
          AND kd_e.keyword_norm = '{marker}'
    )"""
    if not _images_table_has_legacy_keywords_column():
        return f"({ips} OR {legacy_kw})"
    legacy_col = (
        f"LOWER(CAST({prefix}keywords AS VARCHAR(2048))) LIKE '%birds:species-exhausted%'"
    )
    return f"({ips} OR {legacy_kw} OR {legacy_col})"


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
    ips_skip_reason: str | None = None,
) -> BirdSpeciesEligibility:
    if not has_birds:
        return BirdSpeciesEligibility.NOT_IN_SCOPE
    if has_species:
        return BirdSpeciesEligibility.COMPLETE
    if has_exhausted_marker:
        return BirdSpeciesEligibility.EXHAUSTED
    st = (ips_status or "").strip().lower()
    skip = (ips_skip_reason or "").strip().lower()
    if st == "skipped" and skip == BIRD_SPECIES_NO_MATCH_SKIP_REASON:
        return BirdSpeciesEligibility.EXHAUSTED
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
    """Record terminal no-match in IPS so backlog queries skip the image.

    Does not mutate keywords — ``birds`` and other tags stay as-is.
    ``existing_keywords_csv`` is accepted for back-compat but ignored.
    """
    del existing_keywords_csv  # legacy callers; IPS-only path
    if dry_run:
        return True
    from modules import db
    from modules.bird_species import BIRD_SPECIES_RUNNER_VERSION

    db.set_image_phase_status(
        image_id,
        "bird_species",
        "skipped",
        skip_reason=BIRD_SPECIES_NO_MATCH_SKIP_REASON,
        skipped_by="bird_species_eligibility",
        executor_version=BIRD_SPECIES_RUNNER_VERSION,
    )
    return True


def strip_legacy_exhausted_keyword_csv(image_id: int, *, dry_run: bool = False) -> bool:
    """Remove deprecated ``birds:species-exhausted`` from keyword storage."""
    from modules import db

    resolved = db.get_resolved_image_keywords(int(image_id), hide_internal=False)
    cleaned = strip_legacy_exhausted_keyword(_keyword_list_from_csv(resolved))
    if len(cleaned) == len(_keyword_list_from_csv(resolved)):
        return False
    if dry_run:
        return True
    db.update_image_keywords_for_image(int(image_id), ",".join(cleaned), source="auto")
    return True
