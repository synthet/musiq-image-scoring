"""API routes: electron folders (extracted from electron.py)."""

from __future__ import annotations

import asyncio
import os

from fastapi import APIRouter, Body, HTTPException, Query

from modules import db
from modules.api_models import DeleteFolderCacheRequest


def create_electron_folders_router() -> APIRouter:
    router = APIRouter()

    @router.get(
        "/folders/tree",
        summary="Get hierarchical folder tree",
        description="""
        Returns the folder list as a nested tree structure (rather than the flat list
        returned by GET /api/folders). Suitable for rendering a sidebar tree widget in
        Electron without the HTML generation done by the Gradio UI.

        Each node: `{name, path, children: [...]}`. Root nodes are returned as a top-level
        array. Platform path normalisation is applied (WSL↔Windows) the same way the
        Gradio folder tree does it.
        """
    )
    async def get_folder_tree():
        from modules import db, utils
        from modules.ui_tree import build_tree_dict

        try:
            raw_folders = db.get_all_folders()
            folders = []
            for p in raw_folders:
                local_p = utils.convert_path_to_local(p) if hasattr(utils, 'convert_path_to_local') else p
                if not local_p:
                    continue
                norm = os.path.normpath(local_p)
                if os.name == 'nt':
                    if len(norm) < 2 or norm[1] != ':':
                        continue
                    if norm.startswith('\\mnt') or norm == '\\':
                        continue
                else:
                    if local_p.startswith('\\'):
                        continue
                basename = os.path.basename(norm).lower()
                if basename in ['.tmp.drivedownload', '.tmp.driveupload', 'keywords_output', '.']:
                    continue
                folders.append(local_p)

            folders = list(set(folders))
            tree = build_tree_dict(folders)
            return {"tree": tree, "count": len(folders)}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.delete(
        "/folders/cache",
        summary="Remove empty folder subtree from DB cache",
        description=(
            "Deletes the subtree rooted at ``path`` only when ``COUNT(images.folder_id ∈ subtree)==0``. "
            "Does not delete files on disk. Descendant rows are cleared via FK cascade."
        ),
    )
    async def delete_empty_folder_cache_route(request: DeleteFolderCacheRequest = Body(...)):
        try:
            res = await asyncio.to_thread(db.delete_empty_folder_cache_subtree, (request.path or "").strip())
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

        reason = res.get("reason")
        if reason == "invalid":
            raise HTTPException(status_code=400, detail=res.get("message") or "Invalid folder path.")
        if reason == "not_found":
            raise HTTPException(status_code=404, detail=res.get("message") or "Folder not found.")
        if reason == "not_empty":
            raise HTTPException(status_code=409, detail=res.get("message") or "Folder is not empty.")
        if reason == "error" or not res.get("success"):
            raise HTTPException(status_code=500, detail=res.get("message") or "Delete failed.")

        return {
            "success": True,
            "message": res.get("message"),
            "deleted_folders": int(res.get("deleted_folders") or 0),
        }

    @router.get(
        "/folders/phase-status",
        summary="Get pipeline phase aggregate for a folder",
        description="""
        Returns per-phase completion counts for all images in the given folder (and its
        sub-folders). This is the JSON equivalent of the Pipeline tab stepper/phase cards.

        Uses the same cached `phase_agg_json` column as the Gradio UI. Pass
        `force_refresh=true` to bypass the cache and recompute live counts.

        **Query Parameters:**
        - `path` (required): Absolute folder path.
        - `force_refresh` (optional, default false): Bypass cache.
        """
    )
    async def get_folder_phase_status(
        path: str = Query(..., description="Absolute folder path to query."),
        force_refresh: bool = Query(False, description="Bypass cache and recompute live counts."),
    ):
        from modules import db
        try:
            phases = db.get_folder_phase_summary(path, force_refresh=force_refresh)
            return {"folder_path": path, "phases": phases}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get(
        "/folders/{folder_id}",
        summary="Get folder by id",
        description=(
            "Returns a single folder row: id, path, parent_id, is_fully_scored, created_at, "
            "and a live image_count from images.folder_id (not the deprecated folders.image_count column)."
        ),
    )
    async def get_folder_by_id_endpoint(folder_id: int):
        from modules import db
        try:
            row = db.get_folder_detail_by_id(folder_id)
            if not row:
                raise HTTPException(status_code=404, detail=f"Folder {folder_id} not found")
            created = row.get("created_at")
            return {
                "id": row["id"],
                "path": row["path"],
                "parent_id": row.get("parent_id"),
                "is_fully_scored": bool(row.get("is_fully_scored")),
                "image_count": int(row.get("image_count") or 0),
                "created_at": created.isoformat() if hasattr(created, "isoformat") else created,
            }
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    from modules.api.handler_registry import register_handlers

    register_handlers(
        {
            "get_folder_tree": get_folder_tree,
            "get_folder_phase_status": get_folder_phase_status,
        }
    )

    return router
