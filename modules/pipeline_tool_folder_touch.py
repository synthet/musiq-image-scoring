"""Persist per-folder last-touch times for Pipeline Tools (Postgres only).

Used to order heal/backfill work so recently processed folders sink to the back
of the queue (null / oldest touch first).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

logger = logging.getLogger(__name__)


def _postgres_engine() -> bool:
    try:
        from modules.db_legacy import _get_db_engine

        return _get_db_engine() == "postgres"
    except Exception:
        return False


def upsert_pipeline_tool_folder_touch(tool_key: str, folder_id: int | None) -> None:
    """Set last_touched_at = now() for (tool_key, folder_id). No-op if not Postgres or invalid id."""
    if not tool_key or folder_id is None or int(folder_id) <= 0:
        return
    upsert_pipeline_tool_folder_touch_many(tool_key, (int(folder_id),))


def touch_folders_for_image_ids(tool_key: str, image_ids: Iterable[int]) -> None:
    """Upsert last-touch for folders containing any of the given images (Postgres only)."""
    if not tool_key or not _postgres_engine():
        return
    ids = sorted({int(x) for x in image_ids if x is not None and int(x) > 0})
    if not ids:
        return
    try:
        from modules import db_postgres

        rows = db_postgres.execute_select(
            "SELECT DISTINCT folder_id FROM images WHERE id = ANY(%s) AND folder_id IS NOT NULL",
            (ids,),
        )
        fids = [int(r["folder_id"]) for r in rows if r.get("folder_id") is not None]
        upsert_pipeline_tool_folder_touch_many(tool_key, fids)
    except Exception:
        logger.debug(
            "touch_folders_for_image_ids failed (tool_key=%r image_ids=%s)",
            tool_key,
            ids,
            exc_info=True,
        )


def upsert_pipeline_tool_folder_touch_many(tool_key: str, folder_ids: Iterable[int]) -> None:
    """Batch upsert distinct folder ids for one tool_key."""
    if not tool_key or not _postgres_engine():
        return
    ids = sorted({int(x) for x in folder_ids if x is not None and int(x) > 0})
    if not ids:
        return
    try:
        from modules import db_postgres

        # Timestamptz + ON CONFLICT keeps round-robin bookkeeping cheap.
        sql = """
            INSERT INTO pipeline_tool_folder_last_touch (tool_key, folder_id, last_touched_at)
            VALUES (%s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (tool_key, folder_id)
            DO UPDATE SET last_touched_at = CURRENT_TIMESTAMP
        """
        for fid in ids:
            db_postgres.execute_write(sql, (tool_key, fid))
    except Exception:
        logger.debug(
            "pipeline_tool_folder_touch upsert failed (tool_key=%r folder_ids=%s)",
            tool_key,
            ids,
            exc_info=True,
        )
