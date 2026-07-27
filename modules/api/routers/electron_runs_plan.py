"""API routes: electron runs planning and auto-drive (extracted from electron.py)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Body, HTTPException, Query

from modules import db
from modules.api.routers.electron_models import (
    RunsAutoDriveRequest,
    RunsDriveStartRequest,
    ValidationRepairPreviewRequest,
)
from modules.api.routers.electron_scope_helpers import normalize_scope_path_input


def create_electron_runs_plan_router() -> APIRouter:
    router = APIRouter()

    @router.post("/runs/plan/preview", summary="Preview stale/missing work for scope")
    @router.post("/runs/validation-repair/preview", summary="Preview stale/missing work for scope (alias)")
    async def preview_validation_repair(request: ValidationRepairPreviewRequest = Body(...)):
        scope_paths = [normalize_scope_path_input(p) for p in request.scope_paths]
        scope_paths = [p for p in scope_paths if p]
        if not scope_paths:
            raise HTTPException(status_code=400, detail="scope_paths must not be empty")
        include_stale = request.include_stale_executor
        if request.align_auto_drive:
            include_stale = False
        try:
            result = await asyncio.to_thread(
                db.build_validation_repair_plan,
                scope_paths,
                request.stages or [],
                True,
                include_stale_executor=include_stale,
            )
            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/runs/folder-buckets", summary="Paginated folder buckets for Runs auto-queue")
    async def get_run_folder_buckets(
        root_path: str | None = None,
        q: str | None = None,
        bucket: str | None = None,
        limit: int = Query(25, ge=1, le=200),
        offset: int = Query(0, ge=0),
        include_complete: bool = False,
        refresh_dirty_limit: int = Query(
            100,
            ge=0,
            le=500,
            description=(
                "Max folder phase summaries to force-refresh when bulk cache is missing "
                "or phase_agg_dirty=1 (0 = only refresh missing cache entries)."
            ),
        ),
        planner_preview_limit: int = Query(
            0,
            ge=0,
            le=100,
            description=(
                "Max folder-bucket rows on this page to compute JIT planner_next_phases "
                "(default 0; opt in for accurate enqueue preview, but each row runs a "
                "per-image plan_scope and can be slow on folders with many images)."
            ),
        ),
        planner_preview_max_images: int = Query(
            500,
            ge=0,
            le=100000,
            description=(
                "Skip planner preview on folders larger than this image count "
                "(0 disables the cap)."
            ),
        ),
    ):
        try:
            from modules import runs_autodrive

            return await asyncio.to_thread(
                runs_autodrive.build_folder_buckets,
                root_path=root_path,
                q=q,
                bucket=bucket,
                limit=limit,
                offset=offset,
                include_complete=include_complete,
                refresh_dirty_limit=refresh_dirty_limit,
                planner_preview_limit=planner_preview_limit,
                planner_preview_max_images=planner_preview_max_images,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("/runs/auto-drive", summary="Auto-queue folder runs from bucket planner")
    async def auto_drive_runs(request: RunsAutoDriveRequest = Body(...)):
        try:
            from modules import runs_autodrive

            return await asyncio.to_thread(
                runs_autodrive.auto_drive_runs,
                root_path=request.root_path,
                folder_paths=request.folder_paths,
                limit=request.limit,
                dry_run=request.dry_run,
                target_phases=request.target_phases,
                max_repeats=request.max_repeats,
                generate_captions=request.generate_captions,
                force=request.force,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("/runs/drive/start", summary="Start the durable auto-drive loop")
    async def start_runs_drive(request: RunsDriveStartRequest = Body(...)):
        try:
            from modules import runs_autodrive

            return await asyncio.to_thread(
                lambda: {
                    "state": runs_autodrive.arm_drive(
                        root_path=request.root_path,
                        limit=request.limit,
                        target_phases=request.target_phases,
                        generate_captions=request.generate_captions,
                        max_repeats=request.max_repeats,
                    ),
                    "batch": runs_autodrive.kick_drive_batch_async(force=True),
                },
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

    @router.post("/runs/drive/stop", summary="Stop the durable auto-drive loop")
    async def stop_runs_drive():
        from modules import runs_autodrive

        return {"state": await asyncio.to_thread(runs_autodrive.stop_drive, "manual")}

    @router.get("/runs/drive/status", summary="Auto-drive loop status + outstanding work")
    async def runs_drive_status():
        from modules import runs_autodrive

        return await asyncio.to_thread(runs_autodrive.get_drive_status_with_outstanding)
    return router
