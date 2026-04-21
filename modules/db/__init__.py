"""
modules.db — thin facade over the monolithic modules.db_legacy.

The package structure exists so individual domain areas (jobs, images,
folders, engine, etc.) can be migrated out of the monolith incrementally.
Until a submodule is ready to take over, callers transparently get the
legacy monolith's implementation via a sys.modules alias — this keeps
`modules.db.X` and `modules.db_legacy.X` bound to the same function objects,
so tests patching `modules.db.X` and intra-monolith calls see each other.

Adding a new helper? Put it on modules.db_legacy (authoritative), then
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


_ensure_new_helpers(_db_legacy)

# Alias the package to the monolith so `modules.db` IS `modules.db_legacy`.
# Attribute lookups and monkey-patching on modules.db now hit the same
# module globals the legacy internal functions resolve against.
_sys.modules[__name__] = _db_legacy
