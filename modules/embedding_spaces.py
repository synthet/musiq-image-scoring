"""
Registry of embedding / vector spaces stored in PostgreSQL (pgvector).

Each space has a fixed dimension; different dimensions use separate physical
storage (see docs/planning/database/DB_VECTORS_REFACTOR.md). Firebird remains
single-blob on ``images.image_embedding`` until gallery migrates to Postgres.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

DEFAULT_EMBEDDING_SPACE_CODE = "mobilenet_v2_imagenet_gap"
DEFAULT_EMBEDDING_MODEL_DIM = 1280

# Non-default spaces persisted by piggyback during existing phases.
CLIP_IMAGE_SPACE_CODE = "clip_vit_b32_image"
CLIP_IMAGE_DIM = 512
BIOCLIP_IMAGE_SPACE_CODE = "bioclip_2_image"
# BioCLIP 2 uses ViT-L/14 (768-d), not ViT-B/32 (512-d).
BIOCLIP_IMAGE_DIM = 768
BLIP_IMAGE_SPACE_CODE = "blip_vit_b16_image"
BLIP_IMAGE_DIM = 768

# Per-code dimension map (registry mirror — keeps callers from hitting the DB
# to validate output shapes). Must agree with migration 0012 and init_db().
SPACE_DIMS: dict[str, int] = {
    DEFAULT_EMBEDDING_SPACE_CODE: DEFAULT_EMBEDDING_MODEL_DIM,
    CLIP_IMAGE_SPACE_CODE: CLIP_IMAGE_DIM,
    BIOCLIP_IMAGE_SPACE_CODE: BIOCLIP_IMAGE_DIM,
    BLIP_IMAGE_SPACE_CODE: BLIP_IMAGE_DIM,
}

_space_id_cache: int | None = None
_space_id_by_code_cache: dict[str, int | None] = {}


def get_default_embedding_space_id() -> int | None:
    """Return embedding_spaces.id for the default 1280-d space (Postgres only).

    Only positive results are cached. A miss (engine != postgres, registry row
    not found, or unexpected error) falls through to a fresh DB lookup on the
    next call so a process started before the relevant Alembic migration ran
    will recover automatically as soon as the registry catches up.
    """
    global _space_id_cache
    if _space_id_cache is not None:
        return _space_id_cache
    try:
        from modules import db
        from modules import db_postgres

        if db._get_db_engine() != "postgres":
            return None
        row = db_postgres.execute_select_one(
            "SELECT id FROM embedding_spaces WHERE code = %s AND COALESCE(active, 1) = 1 LIMIT 1",
            (DEFAULT_EMBEDDING_SPACE_CODE,),
        )
        if row:
            _space_id_cache = int(row["id"])
            return _space_id_cache
        return None
    except (AttributeError, TypeError, ValueError) as e:
        logger.warning(f"Failed to load default embedding space: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error loading default embedding space: {e}")
        return None


def get_embedding_space_id(code: str) -> int | None:
    """Return embedding_spaces.id for ``code`` (Postgres only).

    Only positive hits are cached — see ``get_default_embedding_space_id`` for
    the rationale. Lookup is a PK read on a tiny table so retrying on misses
    is essentially free.
    """
    if code == DEFAULT_EMBEDDING_SPACE_CODE:
        return get_default_embedding_space_id()
    cached = _space_id_by_code_cache.get(code)
    if cached is not None:
        return cached
    try:
        from modules import db
        from modules import db_postgres

        if db._get_db_engine() != "postgres":
            return None
        row = db_postgres.execute_select_one(
            "SELECT id FROM embedding_spaces WHERE code = %s AND COALESCE(active, 1) = 1 LIMIT 1",
            (code,),
        )
        if row:
            sid = int(row["id"])
            _space_id_by_code_cache[code] = sid
            return sid
        return None
    except Exception as e:
        logger.error(f"Unexpected error loading embedding space {code!r}: {e}")
        return None


def invalidate_default_embedding_space_cache() -> None:
    global _space_id_cache
    _space_id_cache = None
    _space_id_by_code_cache.clear()
