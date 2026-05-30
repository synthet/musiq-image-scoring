#!/usr/bin/env python3
"""Read the seeded corpus from the E2E DB for experiments (read side).

All reads target ``image_scoring_test`` (pinned by ``common``). Returns plain
numpy / dict structures so experiments stay decoupled from the DB layer.
"""

from __future__ import annotations

import logging

import numpy as np

from scripts.research.clip_culling import common  # noqa: F401  (pins E2E env on import)
from modules import db_postgres
from modules.embedding_spaces import get_embedding_space_id

logger = logging.getLogger("clip_culling.data")

FOLDERS = [62, 44, 45, 676]
_FCSV = ",".join(str(f) for f in FOLDERS)


def _parse_vec(v) -> np.ndarray | None:
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip().lstrip("[").rstrip("]")
        if not s:
            return None
        return np.array([float(x) for x in s.split(",")], dtype=np.float32)
    if isinstance(v, (bytes, bytearray, memoryview)):
        return np.frombuffer(bytes(v), dtype=np.float32).copy()
    return np.asarray(v, dtype=np.float32)


def load_embeddings(space_code: str) -> dict[int, np.ndarray]:
    """image_id -> L2-normalized vector for ``space_code`` (seeded folders only)."""
    sid = get_embedding_space_id(space_code)
    if sid is None:
        return {}
    from modules.db_legacy import _pg_embedding_table_for_dim
    from modules.embedding_spaces import SPACE_DIMS

    dim = SPACE_DIMS.get(space_code)
    table = _pg_embedding_table_for_dim(dim)
    rows = db_postgres.execute_select(
        f"SELECT e.image_id, e.embedding FROM {table} e "
        f"JOIN images i ON i.id=e.image_id "
        f"WHERE e.embedding_space_id=%s AND i.folder_id IN ({_FCSV})",
        (sid,),
    )
    out = {}
    for r in rows:
        vec = _parse_vec(r["embedding"])
        if vec is not None:
            out[r["image_id"]] = vec
    return out


def load_meta() -> dict[int, dict]:
    """image_id -> metadata (scores, rating, label, cull, stack, paths)."""
    rows = db_postgres.execute_select(
        f"SELECT id, folder_id, stack_id, file_path, thumbnail_path, thumbnail_path_win, "
        f"score_general, score_technical, score_aesthetic, rating, label, cull_decision "
        f"FROM images WHERE folder_id IN ({_FCSV})"
    )
    return {r["id"]: dict(r) for r in rows}


def load_model_scores() -> dict[int, dict[str, float]]:
    """image_id -> {model_name: normalized} from image_model_scores."""
    rows = db_postgres.execute_select(
        f"SELECT s.image_id, s.model_name, s.normalized FROM image_model_scores s "
        f"JOIN images i ON i.id=s.image_id WHERE i.folder_id IN ({_FCSV})"
    )
    out: dict[int, dict[str, float]] = {}
    for r in rows:
        if r["normalized"] is None:
            continue
        out.setdefault(r["image_id"], {})[r["model_name"]] = float(r["normalized"])
    return out


def load_keywords(source: str | None = None) -> dict[int, set[str]]:
    """image_id -> set of keyword_norm. Optional ``source`` filter (auto/user/bioclip)."""
    q = (
        f"SELECT ik.image_id, kd.keyword_norm, ik.source FROM image_keywords ik "
        f"JOIN keywords_dim kd ON kd.keyword_id=ik.keyword_id "
        f"JOIN images i ON i.id=ik.image_id WHERE i.folder_id IN ({_FCSV})"
    )
    rows = db_postgres.execute_select(q)
    out: dict[int, set[str]] = {}
    for r in rows:
        if source and r["source"] != source:
            continue
        out.setdefault(r["image_id"], set()).add(r["keyword_norm"])
    return out


def stacks(min_size: int = 1) -> dict[int, list[int]]:
    """stack_id -> [image_id] for seeded folders, filtered by ``min_size``."""
    rows = db_postgres.execute_select(
        f"SELECT stack_id, id FROM images WHERE folder_id IN ({_FCSV}) AND stack_id IS NOT NULL"
    )
    out: dict[int, list[int]] = {}
    for r in rows:
        out.setdefault(r["stack_id"], []).append(r["id"])
    return {k: v for k, v in out.items() if len(v) >= min_size}


def species_images() -> set[int]:
    rows = db_postgres.execute_select(
        f"SELECT DISTINCT ik.image_id FROM image_keywords ik "
        f"JOIN keywords_dim kd ON kd.keyword_id=ik.keyword_id "
        f"JOIN images i ON i.id=ik.image_id "
        f"WHERE i.folder_id IN ({_FCSV}) AND kd.keyword_norm LIKE 'species:%%'"
    )
    return {r["image_id"] for r in rows}


def capture_times() -> dict[int, object]:
    """image_id -> capture datetime (date_time_original, else create_date)."""
    from datetime import datetime

    rows = db_postgres.execute_select(
        f"SELECT i.id AS image_id, e.date_time_original, e.create_date "
        f"FROM images i "
        f"JOIN image_exif e ON e.image_id = i.id "
        f"WHERE i.folder_id IN ({_FCSV})"
    )
    out: dict[int, object] = {}
    for r in rows:
        ts = r.get("date_time_original") or r.get("create_date")
        if ts is None:
            continue
        if isinstance(ts, str):
            for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                try:
                    ts = datetime.strptime(ts.strip(), fmt)
                    break
                except ValueError:
                    continue
            else:
                continue
        out[r["image_id"]] = ts
    return out


def images_by_folder() -> dict[int, list[int]]:
    """folder_id -> [image_id] for seeded folders."""
    rows = db_postgres.execute_select(
        f"SELECT id, folder_id FROM images WHERE folder_id IN ({_FCSV}) ORDER BY id"
    )
    out: dict[int, list[int]] = {}
    for r in rows:
        out.setdefault(r["folder_id"], []).append(r["id"])
    return out
