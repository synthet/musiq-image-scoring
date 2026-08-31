"""
Facade for the database module.

Historically, this project used a monolithic `modules.db_legacy.py`. 
To support cleaner imports and transition to a PostgreSQL-native 
architecture, we use this package as a facade that currently 
aliases back to the legacy monolith.

New PostgreSQL-native code should prefer the granular helpers that will 
migrate into a submodule when the surrounding area is extracted.
"""
import sys as _sys

from modules import db_legacy as _db_legacy


def _ensure_new_helpers(mod):
    if not hasattr(mod, "is_image_bird_species_complete"):
        def is_image_bird_species_complete(image_id: int, *, include_bbox: bool = True) -> bool:
            """Mirror of ``db_legacy.get_phase_incomplete_sql('bird_species')`` per image.

            Keep the two in step: when they disagree, auto-drive enqueues folders the
            runner then filters empty and the drive stalls on no-progress ticks.

            ``include_bbox=False`` answers the narrower question "is the *species* work
            done?", ignoring the bird box. ``BirdSpeciesRunner`` uses it to tell a row
            that needs full classification from one that only needs a detector rescan.
            """
            from modules.bird_detection import bbox_needs_scan
            from modules.bird_species_eligibility import (
                BIRDS_SPECIES_EXHAUSTED_NORM,
                _sql_exhausted_marker,
            )

            conn = mod.get_connector()
            cnt_birds = conn.query_one(
                "SELECT COUNT(*) AS c FROM image_keywords ik "
                "JOIN keywords_dim kd ON kd.keyword_id = ik.keyword_id "
                "WHERE ik.image_id = ? AND LOWER(kd.keyword_norm) LIKE '%birds%'",
                (image_id,),
            )
            has_birds = int((cnt_birds or {}).get("c") or 0) > 0

            kw_str = None
            if mod._images_table_has_legacy_keywords_column():
                row = conn.query_one(
                    "SELECT keywords FROM images WHERE id = ?", (image_id,)
                )
                if not row:
                    return False
                kw_str = str(row.get("keywords") or "").lower()
                has_birds = has_birds or "birds" in kw_str

            # Not birds-tagged => out of scope for this phase entirely.
            if not has_birds:
                return True

            # The bird box is a product of this phase, so a birds-tagged image that was
            # never scanned (or whose scan failed retryably) still owes work — even when
            # species are already assigned or the species search is exhausted. Postgres
            # only: ``bird_bbox`` does not exist on the legacy Firebird schema.
            if include_bbox and mod._get_db_engine() == "postgres":
                row_bbox = conn.query_one(
                    "SELECT bird_bbox FROM images WHERE id = ?", (image_id,)
                )
                if row_bbox is not None and bbox_needs_scan(row_bbox.get("bird_bbox")):
                    return False

            exhausted_sql = _sql_exhausted_marker("i")
            row_ex = conn.query_one(
                f"SELECT 1 AS x FROM images i WHERE i.id = ? AND ({exhausted_sql})",
                (image_id,),
            )
            if row_ex:
                return True
            if kw_str is not None and BIRDS_SPECIES_EXHAUSTED_NORM in kw_str:
                return True

            cnt_species = conn.query_one(
                "SELECT COUNT(*) AS c FROM image_keywords ik "
                "JOIN keywords_dim kd ON kd.keyword_id = ik.keyword_id "
                "WHERE ik.image_id = ? AND LOWER(kd.keyword_norm) LIKE 'species:%'",
                (image_id,),
            )
            has_species = int((cnt_species or {}).get("c") or 0) > 0
            if kw_str is not None:
                has_species = has_species or "species:" in kw_str
            return has_species
        mod.is_image_bird_species_complete = is_image_bird_species_complete

    if not hasattr(mod, "is_image_culling_complete"):
        def is_image_culling_complete(image_id: int) -> bool:
            row = mod.get_connector().query_one(
                "SELECT cull_decision FROM images WHERE id = ?", (image_id,)
            )
            return row is not None and str(row.get("cull_decision") or "").strip() != ""
        mod.is_image_culling_complete = is_image_culling_complete

    # Some call sites import `modules.db` very early (during module import),
    # before `modules.db_legacy` finishes defining all helpers. Provide a safe
    # fallback so those call sites don't crash on attribute access.
    if not hasattr(mod, "get_queued_jobs_count"):
        def get_queued_jobs_count() -> int:
            try:
                row = mod.get_connector().query_one(
                    "SELECT COUNT(*) AS cnt FROM jobs WHERE status = 'queued'"
                )
                return int((row or {}).get("cnt") or 0)
            except Exception:
                return 0
        mod.get_queued_jobs_count = get_queued_jobs_count


_ensure_new_helpers(_db_legacy)

# Alias the package to the monolith so `modules.db` IS `modules.db_legacy`.
_sys.modules[__name__] = _db_legacy
