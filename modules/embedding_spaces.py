"""
Registry of embedding / vector spaces stored in PostgreSQL (pgvector).

Each space has a fixed dimension; different dimensions use separate physical
storage (see docs/plans/database/DB_VECTORS_REFACTOR.md). Firebird remains
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
BIOCLIP_IMAGE_DIM = 512
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
        _space_id_cache = int(row["id"]) if row else None
        return _space_id_cache
    except (AttributeError, TypeError, ValueError) as e:
        logger.warning(f"Failed to load default embedding space: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error loading default embedding space: {e}")
        return None


def get_embedding_space_id(code: str) -> int | None:
    """Return embedding_spaces.id for ``code`` (Postgres only), cached by code."""
    if code == DEFAULT_EMBEDDING_SPACE_CODE:
        return get_default_embedding_space_id()
    if code in _space_id_by_code_cache:
        return _space_id_by_code_cache[code]
    try:
        from modules import db
        from modules import db_postgres

        if db._get_db_engine() != "postgres":
            _space_id_by_code_cache[code] = None
            return None
        row = db_postgres.execute_select_one(
            "SELECT id FROM embedding_spaces WHERE code = %s AND COALESCE(active, 1) = 1 LIMIT 1",
            (code,),
        )
        sid = int(row["id"]) if row else None
        _space_id_by_code_cache[code] = sid
        return sid
    except Exception as e:
        logger.error(f"Unexpected error loading embedding space {code!r}: {e}")
        _space_id_by_code_cache[code] = None
        return None


def invalidate_default_embedding_space_cache() -> None:
    global _space_id_cache
    _space_id_cache = None
    _space_id_by_code_cache.clear()
