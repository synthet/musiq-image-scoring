"""
Remove folder subtrees that contain no Nikon NEF images (DB rows only).

Used by the maintenance CLI (``scripts/maintenance/prune_folders_without_nef.py``).
"""

from __future__ import annotations

import os
from typing import Any


def _norm_path_key(p: str) -> str:
    return os.path.normpath(str(p or "")).replace("\\", "/")


def _is_under_root(folder_path: str, root: str | None) -> bool:
    if not root or not str(root).strip():
        return True
    fp = _norm_path_key(folder_path).rstrip("/")
    rr = _norm_path_key(root).rstrip("/")
    return fp == rr or fp.startswith(rr + "/")


def _is_nef(file_type: str | None, file_path: str | None) -> bool:
    ft = (file_type or "").strip().lower()
    if ft == "nef":
        return True
    fp = (file_path or "").lower()
    return fp.endswith(".nef")


def _build_subtree_has_nef(
    folder_rows: list[dict],
    images_rows: list[dict],
) -> tuple[dict[int, bool], dict[int, list[int]]]:
    by_id: dict[int, dict] = {}
    children: dict[int, list[int]] = {}
    for r in folder_rows:
        try:
            fid = int(r["id"])
        except (TypeError, ValueError, KeyError):
            continue
        by_id[fid] = r
        children.setdefault(fid, [])
        pid = r.get("parent_id")
        if pid is not None:
            try:
                p = int(pid)
                children.setdefault(p, []).append(fid)
            except (TypeError, ValueError):
                pass

    direct_nef: dict[int, bool] = {fid: False for fid in by_id}
    for img in images_rows:
        try:
            fid = img.get("folder_id")
            if fid is None:
                continue
            fid = int(fid)
        except (TypeError, ValueError):
            continue
        if fid not in direct_nef:
            continue
        if _is_nef(img.get("file_type"), img.get("file_path")):
            direct_nef[fid] = True

    memo: dict[int, bool] = {}

    def subtree(fid: int) -> bool:
        if fid in memo:
            return memo[fid]
        ok = direct_nef.get(fid, False)
        for c in children.get(fid, ()):
            if subtree(c):
                ok = True
                break
        memo[fid] = ok
        return ok

    for fid in list(by_id.keys()):
        subtree(fid)
    return memo, children


def _prune_roots(prune_ids: set[int], by_id: dict[int, dict]) -> list[int]:
    roots: list[int] = []
    for fid in prune_ids:
        r = by_id.get(fid)
        if not r:
            continue
        pid = r.get("parent_id")
        try:
            p = int(pid) if pid is not None else None
        except (TypeError, ValueError):
            p = None
        if p is None or p not in prune_ids:
            roots.append(fid)
    return roots


def run_prune_folders_without_nef(
    *,
    root: str | None = None,
    dry_run: bool = True,
    limit_images: int = 0,
) -> dict[str, Any]:
    """
    Plan and optionally execute prune of non-NEF folder subtrees.

    Returns a JSON-friendly dict (for logging / API); does not print.
    """
    from modules.db import delete_folder_cache_entry, delete_image, get_connector

    conn = get_connector()
    folder_rows = conn.query("SELECT id, path, parent_id FROM folders")
    if not folder_rows:
        return {
            "success": True,
            "dry_run": dry_run,
            "message": "No folders in database.",
            "prune_folder_count": 0,
            "image_paths_count": 0,
            "deleted_images": 0,
            "deleted_folder_rows_reported": 0,
            "root_paths": [],
        }

    images_rows = conn.query(
        "SELECT folder_id, file_type, file_path FROM images WHERE folder_id IS NOT NULL"
    )

    by_id: dict[int, dict] = {}
    for r in folder_rows:
        try:
            by_id[int(r["id"])] = r
        except (TypeError, ValueError, KeyError):
            continue

    subtree_nef, _children = _build_subtree_has_nef(folder_rows, images_rows)

    prune_ids: set[int] = set()
    for fid, has_nef in subtree_nef.items():
        if has_nef:
            continue
        path = str(by_id.get(fid, {}).get("path") or "")
        if not _is_under_root(path, root):
            continue
        prune_ids.add(fid)

    prune_list = list(prune_ids)
    image_paths: list[str] = []
    chunk_size = 400
    for i in range(0, len(prune_list), chunk_size):
        chunk = prune_list[i : i + chunk_size]
        ph = ",".join(["?"] * len(chunk))
        rows = conn.query(
            f"SELECT file_path FROM images WHERE folder_id IN ({ph})",
            tuple(chunk),
        )
        for row in rows:
            p = row.get("file_path")
            if p:
                image_paths.append(str(p))

    roots = _prune_roots(prune_ids, by_id)
    root_paths = [str(by_id[r]["path"]) for r in roots if by_id.get(r, {}).get("path")]

    out: dict[str, Any] = {
        "success": True,
        "dry_run": dry_run,
        "prune_folder_count": len(prune_ids),
        "top_level_prune_roots": len(roots),
        "image_paths_count": len(image_paths),
        "root_paths": root_paths,
        "deleted_images": 0,
        "deleted_folder_rows_reported": 0,
    }

    if dry_run:
        out["message"] = (
            f"Dry-run: {len(prune_ids)} folder(s), {len(image_paths)} image row(s), "
            f"{len(roots)} top-level root(s)."
        )
        return out

    deleted = 0
    errors: list[str] = []
    for path in image_paths:
        if limit_images and deleted >= limit_images:
            out["limit_stopped_at"] = limit_images
            break
        ok, msg = delete_image(path)
        if ok:
            deleted += 1
        else:
            errors.append(f"{path}: {msg}")

    folder_deleted = 0
    for rp in root_paths:
        res = delete_folder_cache_entry(rp, delete_descendants=True)
        if res.get("success"):
            folder_deleted += int(res.get("deleted_folders") or 0)
        else:
            errors.append(f"folder {rp}: {res.get('message')}")

    out["deleted_images"] = deleted
    out["deleted_folder_rows_reported"] = folder_deleted
    out["errors"] = errors
    out["message"] = (
        f"Deleted {deleted} image row(s); folder cache rows removed (reported): {folder_deleted}."
    )
    return out
