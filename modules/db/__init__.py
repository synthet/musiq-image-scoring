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
        def is_image_bird_species_complete(image_id: int) -> bool:
            conn = mod.get_connector()
            row = conn.query_one("SELECT keywords FROM images WHERE id = ?", (image_id,))
            if not row:
                return False
            kw_str = str(row.get("keywords") or "").lower()
            cnt_birds = conn.query_one(
                "SELECT COUNT(*) AS c FROM image_keywords ik "
                "JOIN keywords_dim kd ON kd.keyword_id = ik.keyword_id "
                "WHERE ik.image_id = ? AND LOWER(kd.keyword_norm) LIKE '%birds%'",
                (image_id,),
            )
            has_birds = "birds" in kw_str or int((cnt_birds or {}).get("c") or 0) > 0
            if not has_birds:
                return True
            cnt_species = conn.query_one(
                "SELECT COUNT(*) AS c FROM image_keywords ik "
                "JOIN keywords_dim kd ON kd.keyword_id = ik.keyword_id "
                "WHERE ik.image_id = ? AND LOWER(kd.keyword_norm) LIKE 'species:%'",
                (image_id,),
            )
            return "species:" in kw_str or int((cnt_species or {}).get("c") or 0) > 0
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
