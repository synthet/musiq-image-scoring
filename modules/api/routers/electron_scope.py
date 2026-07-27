"""API routes: electron scope and queue (extracted from electron.py)."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Body, HTTPException

from modules import db
from modules.api.routers.electron_models import QueueReorderRequest, ScopePreviewRequest
from modules.api.routers.electron_scope_helpers import (
    build_scope_tree_sync,
    compute_scope_preview_for_resolved_paths,
    normalize_scope_path_input,
    scope_resolve_path,
)


def create_electron_scope_router() -> APIRouter:
    router = APIRouter()

    @router.post("/scope/preview", summary="Preview scope before submitting a Run")
    async def scope_preview(request: ScopePreviewRequest = Body(...)):
        """Returns image count and per-stage phase statuses for the given paths.
        When a folder has no images in the DB (not yet indexed), scans the filesystem to show actual counts."""
        preview_paths = [normalize_scope_path_input(p) for p in request.paths]
        preview_paths = [p for p in preview_paths if p]
        if not preview_paths:
            raise HTTPException(status_code=400, detail="paths must not be empty")
        try:
            resolved: list[str] = []
            for path in preview_paths:
                resolved.append(scope_resolve_path(path))
            return compute_scope_preview_for_resolved_paths(resolved, request.recursive)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    @router.get("/scope/tree", summary="Folder tree with phase status overlays")
    async def scope_tree(include_phase_status: bool = True):
        """Enhanced folder tree with per-folder phase status for the Scope Navigator sidebar."""
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(build_scope_tree_sync, include_phase_status),
                timeout=60.0,
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Folder tree build timed out.")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/queue", summary="Get the current Run Queue")
    async def get_run_queue(limit: int = 100):
        try:
            queued = db.get_queued_jobs(limit=limit)
            return [
                {
                    "run_id": j.get("id"),
                    "position": j.get("queue_position"),
                    "input_path": j.get("input_path", ""),
                    "scope_paths": json.loads(j.get("scope_paths") or "[]") or [j.get("input_path", "")],
                    "created_at": j.get("created_at"),
                    "enqueued_at": j.get("enqueued_at"),
                }
                for j in (queued or [])
            ]
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/queue/reorder", summary="Reorder a queued Run")
    async def reorder_queue(request: QueueReorderRequest = Body(...)):
        try:
            db.reorder_queued_job(request.run_id, request.new_position)
            return {"success": True}
        except AttributeError:
            raise HTTPException(status_code=501, detail="Queue reordering not yet implemented")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    return router
