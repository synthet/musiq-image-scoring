"""Utilities for normalizing mixed API selectors into concrete database IDs."""

from __future__ import annotations

import os
from typing import Any

from modules import db, utils

_MAX_IN_PARAMS = 500


def _dedupe_ints(values: list[int] | None) -> list[int]:
    seen: set[int] = set()
    out: list[int] = []
    for value in values or []:
        try:
            i = int(value)
        except (TypeError, ValueError):
            continue
        if i > 0 and i not in seen:
            seen.add(i)
            out.append(i)
    return out


def _dedupe_strs(values: list[str] | None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values or []:
        if value is None:
            continue
        s = str(value).strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _fetch_image_ids_by_paths(conn, image_paths: list[str]) -> tuple[list[int], list[str]]:
    cur = conn.cursor()
    resolved: list[int] = []
    missing: list[str] = []

    for raw_path in image_paths:
        normalized = os.path.normpath(raw_path)
        variants = [raw_path, normalized]
        try:
            wsl_variant = utils.convert_path_to_wsl(raw_path)
            if wsl_variant not in variants:
                variants.append(wsl_variant)
        except Exception:
            pass

        row = None
        for candidate in variants:
            cur.execute("SELECT id FROM images WHERE file_path = ?", (candidate,))
            row = cur.fetchone()
            if row:
                break

        if row:
            resolved.append(int(row[0]))
        else:
            missing.append(raw_path)

    return resolved, missing


def _fetch_folder_ids_by_paths(conn, folder_paths: list[str]) -> tuple[list[int], list[str]]:
    cur = conn.cursor()
    resolved: list[int] = []
    missing: list[str] = []

    for raw_path in folder_paths:
        normalized = os.path.normpath(raw_path)
        variants = [raw_path, normalized]
        try:
            wsl_variant = utils.convert_path_to_wsl(raw_path)
            if wsl_variant not in variants:
                variants.append(wsl_variant)
        except Exception:
            pass

        row = None
        for candidate in variants:
            cur.execute("SELECT id FROM folders WHERE path = ?", (candidate,))
            row = cur.fetchone()
            if row:
                break

        if row:
            resolved.append(int(row[0]))
        else:
            missing.append(raw_path)

    return resolved, missing



def _expand_folder_ids(conn, folder_ids: list[int], recursive: bool) -> list[int]:
    if not recursive or not folder_ids:
        return folder_ids

    seen = set(folder_ids)
    frontier = list(folder_ids)
    cur = conn.cursor()

    while frontier:
        children: list[int] = []
        for i in range(0, len(frontier), _MAX_IN_PARAMS):
            batch = frontier[i:i + _MAX_IN_PARAMS]
            placeholders = ",".join("?" * len(batch))
            cur.execute(f"SELECT id FROM folders WHERE parent_id IN ({placeholders})", tuple(batch))
            children.extend(int(row[0]) for row in cur.fetchall())

        frontier = [fid for fid in children if fid not in seen]
        seen.update(frontier)

    return list(seen)


def _fetch_image_ids_by_folder_ids(conn, folder_ids: list[int]) -> list[int]:
    if not folder_ids:
        return []

    cur = conn.cursor()
    image_ids: list[int] = []
    for i in range(0, len(folder_ids), _MAX_IN_PARAMS):
        batch = folder_ids[i:i + _MAX_IN_PARAMS]
        placeholders = ",".join("?" * len(batch))
        cur.execute(f"SELECT id FROM images WHERE folder_id IN ({placeholders})", tuple(batch))
        image_ids.extend(int(row[0]) for row in cur.fetchall())
    return image_ids

def resolve_selectors(
    image_ids: list[int] | None = None,
    image_paths: list[str] | None = None,
    folder_ids: list[int] | None = None,
    folder_paths: list[str] | None = None,
    recursive: bool = True,
    index_missing: bool = True,
) -> dict[str, Any]:
    """Resolve mixed selectors and return deduplicated image IDs for execution.

    Note: `index_missing=True` uses `db.sync_folder_to_db`, which currently registers
    images from scoring JSON sidecars. Raw/unscored files may remain unresolved until
    they are imported/registered through an explicit ingest flow.
    """
    normalized_image_ids = _dedupe_ints(image_ids)
    normalized_folder_ids = _dedupe_ints(folder_ids)
    normalized_image_paths = _dedupe_strs(image_paths)
    normalized_folder_paths = _dedupe_strs(folder_paths)

    with db.connection() as conn:
        path_image_ids, missing_image_paths = _fetch_image_ids_by_paths(conn, normalized_image_paths)
        path_folder_ids, missing_folder_paths = _fetch_folder_ids_by_paths(conn, normalized_folder_paths)

        indexed_folder_ids: list[int] = []
        indexed_image_paths: list[str] = []

        if index_missing:
            for folder_path in missing_folder_paths:
                try:
                    if os.path.exists(folder_path) and os.path.isdir(folder_path):
                        db.sync_folder_to_db(folder_path)
                    indexed_folder_ids.append(int(db.get_or_create_folder(folder_path)))
                except Exception:
                    continue

            # Re-index missing image paths by scanning parent folders when files exist.
            for image_path in missing_image_paths:
                if not os.path.exists(image_path):
                    continue
                parent = os.path.dirname(image_path)
                if not parent:
                    continue
                try:
                    db.sync_folder_to_db(parent)
                    indexed_image_paths.append(image_path)
                except Exception:
                    continue

            if indexed_image_paths:
                reindexed_ids, still_missing = _fetch_image_ids_by_paths(conn, indexed_image_paths)
                path_image_ids.extend(reindexed_ids)
                missing_image_paths = [p for p in missing_image_paths if p in still_missing]

        all_folder_ids = _dedupe_ints(normalized_folder_ids + path_folder_ids + indexed_folder_ids)
        expanded_folder_ids = _expand_folder_ids(conn, all_folder_ids, recursive)
        folder_image_ids = _fetch_image_ids_by_folder_ids(conn, expanded_folder_ids)

        resolved_image_ids = _dedupe_ints(normalized_image_ids + path_image_ids + folder_image_ids)

        return {
            "resolved_image_ids": resolved_image_ids,
            "resolved_folder_ids": _dedupe_ints(expanded_folder_ids),
            "missing_image_paths": _dedupe_strs(missing_image_paths),
            "missing_folder_paths": _dedupe_strs(missing_folder_paths),
            "indexed_image_paths": _dedupe_strs(indexed_image_paths),
            "indexed_folder_ids": _dedupe_ints(indexed_folder_ids),
        }

