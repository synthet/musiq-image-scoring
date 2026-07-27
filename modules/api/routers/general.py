"""API routes: general (extracted from modules.api)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

from modules import config
from modules.api_models import (
    ConfigResponse,
    HealthResponse,
)

logger = logging.getLogger(__name__)


import sys


def _api_module():
    return sys.modules["modules.api"]



def create_general_router() -> APIRouter:
    router = APIRouter()
    # ========== General Endpoints ==========

    @router.get(
        "/status",
        response_model=dict[str, Any],
        summary="Get all runners status",
        description="""
        Returns the status of all runners (scoring and tagging) in a single response.
        
        Useful for monitoring the overall system state. Each runner's status includes:
        - Availability (whether runner is initialized)
        - Running state
        - Progress information
        - Status message
        - Recent log output (last 2000 characters)
        
        **Response Structure:**
        ```json
        {
            "scoring": {
                "available": true,
                "is_running": false,
                "status_message": "Idle",
                "progress": {"current": 0, "total": 0},
                "log": "",
                "job_type": null
            },
            "tagging": {
                "available": true,
                "is_running": false,
                "status_message": "Idle",
                "progress": {"current": 0, "total": 0},
                "log": ""
            }
        }
        ```
        """
    )
    async def get_all_status():
        """Get status of all runners."""
        status = {
            "scoring": {"available": False},
            "tagging": {"available": False},
            "clustering": {"available": False}
        }

        if _api_module()._scoring_runner:
            try:
                result = _api_module()._scoring_runner.get_status()
                is_running, log, status_msg, current, total = result[:5]
                status["scoring"] = {
                    "available": True,
                    "is_running": is_running,
                    "status_message": status_msg,
                    "progress": {"current": current, "total": total},
                    "log": log[-2000:] if log else "",  # Last 2000 chars
                    "job_type": getattr(_api_module()._scoring_runner, 'job_type', None)
                }
            except Exception as e:
                status["scoring"]["error"] = str(e)

        if _api_module()._tagging_runner:
            try:
                result = _api_module()._tagging_runner.get_status()
                is_running, log, status_msg, current, total = result[:5]
                status["tagging"] = {
                    "available": True,
                    "is_running": is_running,
                    "status_message": status_msg,
                    "progress": {"current": current, "total": total},
                    "log": log[-2000:] if log else ""
                }
            except Exception as e:
                status["tagging"]["error"] = str(e)

        if _api_module()._clustering_runner:
            try:
                result = _api_module()._clustering_runner.get_status()
                is_running, log, status_msg, current, total = result[:5]
                status["clustering"] = {
                    "available": True,
                    "is_running": is_running,
                    "status_message": status_msg,
                    "progress": {"current": current, "total": total},
                    "log": log[-2000:] if log else ""
                }
            except Exception as e:
                status["clustering"]["error"] = str(e)

        return status
    
    @router.get(
        "/health",
        response_model=HealthResponse,
        summary="Health check",
        description="""
        Simple health check endpoint to verify API availability and runner initialization.
        
        Returns:
        - status: "healthy" if API is operational
        - scoring_available: True if scoring runner is initialized
        - tagging_available: True if tagging runner is initialized
        
        Use this endpoint for:
        - Health monitoring
        - Service discovery
        - Initial API capability detection
        """
    )
    async def health_check():
        """Health check endpoint."""
        return HealthResponse(
            status="healthy",
            scoring_available=_api_module()._scoring_runner is not None,
            tagging_available=_api_module()._tagging_runner is not None,
            clustering_available=_api_module()._clustering_runner is not None
        )

    @router.get(
        "/config",
        response_model=ConfigResponse,
        summary="Get public configuration",
        description="Returns a safe subset of configuration flags for the frontend."
    )
    async def get_public_config():
        """Get public configuration flags."""
        return ConfigResponse(
            enable_culling=config.get_config_value("culling.enabled", False),
            embedding_map_enabled=config.get_config_value("embedding_map.enabled", False),
            db_explorer_enabled=config.get_config_value("database.db_explorer_enabled", True),
            scoring_models=config.get_config_value("scoring.models", {}) or {},
        )


    return router
