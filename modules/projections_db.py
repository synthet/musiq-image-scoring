"""
Projection-side DB readers for non-default embedding spaces.

The default 1280-d MobileNet path lives in ``db.get_embeddings_with_metadata``
(which COALESCEs the legacy ``images.image_embedding`` column with the
``image_embeddings`` fact table). For 512-d / 768-d spaces (CLIP, BioCLIP,
BLIP) there is **no** legacy column to fall back on — embeddings live only in
the per-dim fact table chosen by ``db._pg_embedding_table_for_dim``.

Postgres-only. Other engines return ``[]``.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def get_embeddings_with_metadata_for_space(
    space_code: str,
    folder_path: Optional[str] = None,
    limit: Optional[int] = None,
) -> list[dict]:
    """Return embedding vectors + display metadata for ``space_code``.

    Each row mirrors ``db.get_embeddings_with_metadata`` shape:
        ``image_id``, ``file_path``, ``embedding`` (bytes),
        ``thumbnail_path``, ``label``, ``rating``, ``score_general``,
        ``score_technical``, ``score_aesthetic``, ``score_spaq``,
        ``score_ava``, ``score_koniq``, ``score_paq2piq``, ``score_liqe``.

    Default space (``mobilenet_v2_imagenet_gap``) delegates to the legacy
    helper so the dual-read / legacy-column fallback still applies. All other
    spaces read straight from their per-dim fact table on Postgres and return
    ``[]`` on other engines.
    """
    from modules import db
    from modules.embedding_spaces import (
        DEFAULT_EMBEDDING_SPACE_CODE,
        SPACE_DIMS,
        get_embedding_space_id,
    )

    if space_code == DEFAULT_EMBEDDING_SPACE_CODE:
        return db.get_embeddings_with_metadata(folder_path=folder_path, limit=limit)

    expected_dim = SPACE_DIMS.get(space_code)
    if expected_dim is None:
        logger.warning(
            "get_embeddings_with_metadata_for_space: unknown space %r; "
            "add it to SPACE_DIMS in modules/embedding_spaces.py.",
            space_code,
        )
        return []

    if db._get_db_engine() != "postgres":
        return []

    space_id = get_embedding_space_id(space_code)
    if space_id is None:
        return []

    table = db._pg_embedding_table_for_dim(expected_dim)

    from modules import db_postgres

    params: list = [space_id]
    folder_clause = ""
    if folder_path:
        norm = os.path.normpath(folder_path)
        frow = db_postgres.execute_select_one(
            "SELECT id FROM folders WHERE path = %s", (norm,)
        )
        if not frow:
            return []
        folder_clause = " AND i.folder_id = %s"
        params.append(frow["id"])

    sql = (
        f"SELECT i.id AS image_id, i.file_path, e.embedding, "
        f"       i.thumbnail_path, i.label, i.rating, i.score_general, i.score_technical, "
        f"       i.score_aesthetic, "
        f"       ims.score_spaq, ims.score_ava, ims.score_liqe, "
        f"       ims.score_koniq, ims.score_paq2piq "
        f"FROM {table} e "
        f"JOIN images i ON i.id = e.image_id "
        f"LEFT JOIN ("
        f"  SELECT image_id,"
        f"    MAX(CASE WHEN model_name = 'spaq'    THEN COALESCE(normalized, raw_score) END) AS score_spaq,"
        f"    MAX(CASE WHEN model_name = 'ava'     THEN COALESCE(normalized, raw_score) END) AS score_ava,"
        f"    MAX(CASE WHEN model_name = 'liqe'    THEN COALESCE(normalized, raw_score) END) AS score_liqe,"
        f"    MAX(CASE WHEN model_name = 'koniq'   THEN COALESCE(normalized, raw_score) END) AS score_koniq,"
        f"    MAX(CASE WHEN model_name = 'paq2piq' THEN COALESCE(normalized, raw_score) END) AS score_paq2piq"
        f"  FROM image_model_scores"
        f"  WHERE model_name IN ('spaq','ava','liqe','koniq','paq2piq')"
        f"    AND is_shadow = FALSE AND status = 'success'"
        f"  GROUP BY image_id"
        f") ims ON ims.image_id = i.id "
        f"WHERE e.embedding_space_id = %s{folder_clause}"
    )
    if limit:
        sql += " LIMIT %s"
        params.append(int(limit))

    rows = db_postgres.execute_select(sql, tuple(params))

    import numpy as np

    out = []
    for r in rows:
        emb = r.get("embedding")
        if emb is None:
            continue
        emb_bytes = np.asarray(emb, dtype=np.float32).tobytes()
        out.append({
            "image_id": r["image_id"],
            "file_path": r["file_path"],
            "embedding": emb_bytes,
            "thumbnail_path": r.get("thumbnail_path"),
            "label": r.get("label"),
            "rating": r.get("rating"),
            "score_general": (
                float(r["score_general"]) if r.get("score_general") is not None else None
            ),
            "score_technical": (
                float(r["score_technical"]) if r.get("score_technical") is not None else None
            ),
            "score_aesthetic": (
                float(r["score_aesthetic"]) if r.get("score_aesthetic") is not None else None
            ),
            "score_spaq": float(r["score_spaq"]) if r.get("score_spaq") is not None else None,
            "score_ava": float(r["score_ava"]) if r.get("score_ava") is not None else None,
            "score_koniq": float(r["score_koniq"]) if r.get("score_koniq") is not None else None,
            "score_paq2piq": float(r["score_paq2piq"]) if r.get("score_paq2piq") is not None else None,
            "score_liqe": float(r["score_liqe"]) if r.get("score_liqe") is not None else None,
        })
    return out
