"""Electron IPC bridge route (dispatches to registered API handlers)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from modules.api.handler_registry import get_handler
from modules.api_models import (
    IpcBridgeRequest,
    IpcBridgeResponse,
    PipelinePhaseControlRequest,
    PipelineSubmitRequest,
)


def create_ipc_bridge_router() -> APIRouter:
    router = APIRouter()

    @router.post(
        "/ipc/bridge",
        response_model=IpcBridgeResponse,
        summary="Electron IPC -> FastAPI bridge",
        description="""
        Bridges Electron-style IPC messages into FastAPI handlers so the desktop
        main process can forward a single contract to Python.

        Supported channels:
        - `pipeline:submit` -> POST /api/pipeline/submit
        - `pipeline:phase:skip` -> POST /api/pipeline/phase/skip
        - `pipeline:phase:retry` -> POST /api/pipeline/phase/retry
        - `tasks:active` -> GET /api/tasks/active
        - `jobs:queue` -> GET /api/jobs/queue
        - `folders:tree` -> GET /api/folders/tree
        - `folders:phase-status` -> GET /api/folders/phase-status
        """,
    )
    async def ipc_bridge(request: IpcBridgeRequest):
        channel = (request.channel or "").strip()
        payload = request.payload or {}

        if channel == "pipeline:submit":
            result = get_handler("submit_pipeline")(PipelineSubmitRequest(**payload))
            return IpcBridgeResponse(channel=channel, ok=result.success, data=result.model_dump())

        if channel == "pipeline:phase:skip":
            result = await get_handler("skip_pipeline_phase")(PipelinePhaseControlRequest(**payload))
            return IpcBridgeResponse(channel=channel, ok=True, data=result.model_dump())

        if channel == "pipeline:phase:retry":
            result = await get_handler("retry_pipeline_phase")(PipelinePhaseControlRequest(**payload))
            return IpcBridgeResponse(channel=channel, ok=True, data=result.model_dump())

        if channel == "tasks:active":
            limit = int(payload.get("limit", 200) or 200)
            result = await get_handler("get_tasks_active")(limit=limit)
            return IpcBridgeResponse(channel=channel, ok=True, data=result)

        if channel == "jobs:queue":
            limit = int(payload.get("limit", 200) or 200)
            result = await get_handler("get_jobs_queue")(limit=limit)
            return IpcBridgeResponse(channel=channel, ok=True, data=result)

        if channel == "folders:tree":
            result = await get_handler("get_folder_tree")()
            return IpcBridgeResponse(channel=channel, ok=True, data=result)

        if channel == "folders:phase-status":
            path = (payload.get("path") or payload.get("input_path") or "").strip()
            if not path:
                raise HTTPException(status_code=400, detail="payload.path is required for folders:phase-status")
            force_refresh = bool(payload.get("force_refresh", False))
            result = await get_handler("get_folder_phase_status")(path=path, force_refresh=force_refresh)
            return IpcBridgeResponse(channel=channel, ok=True, data=result)

        raise HTTPException(status_code=400, detail=f"Unsupported IPC channel: {channel}")

    return router
