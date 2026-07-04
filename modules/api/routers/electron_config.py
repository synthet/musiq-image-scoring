"""API routes: electron config (extracted from electron.py)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import FileResponse

from modules import db
from modules.api.routers.electron_helpers import (
    api_module,
    logger,
    _join_runner_threads,
    _stop_runner_for_job_row,
    _stop_runner_for_phase,
)
from modules.api_models import ApiResponse

def create_electron_config_router() -> APIRouter:
    router = APIRouter()

    @router.get(
        "/config/full",
        summary="Get full application configuration",
        description="""
        Returns merged `config.json` + `environment.json` contents for Settings integrations
        and Electron. Prefer `GET /api/config` for the React SPA feature-flag subset.
        Passwords and tokens may be present; callers should not expose this response publicly.
        """
    )
    async def get_config_full():
        from modules.config import load_config
        try:
            return load_config()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post(
        "/config/{section}",
        summary="Save a configuration section",
        description="""
        Persists a configuration section to `config.json`. Pass the section name as a
        path parameter (e.g. `scoring`, `ui`, `tagging`) and the section dict as the
        JSON body. Equivalent to clicking "Save All Configuration" in the Settings tab
        for a specific section.
        """
    )
    async def save_config(section: str, body: Dict[str, Any] = Body(...)):
        from modules.config import save_config_section
        from modules.ui.security import _check_rate_limit
        _check_rate_limit("config_save")
        valid_sections = {"scoring", "processing", "culling", "ui", "tagging"}
        if section not in valid_sections:
            raise HTTPException(status_code=400, detail=f"Unknown config section: {section!r}. Valid: {sorted(valid_sections)}")
        try:
            save_config_section(section, body)
            return ApiResponse(success=True, message=f"Config section '{section}' saved.", data={})
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    return router
