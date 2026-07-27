"""API routes: electron (composer for domain sub-routers)."""

from __future__ import annotations

from fastapi import APIRouter

from modules.api.routers.electron_config import create_electron_config_router
from modules.api.routers.electron_folders import create_electron_folders_router
from modules.api.routers.electron_images import create_electron_images_router
from modules.api.routers.electron_runs_lifecycle import (
    create_electron_runs_lifecycle_router,
)
from modules.api.routers.electron_runs_plan import create_electron_runs_plan_router
from modules.api.routers.electron_scope import create_electron_scope_router


def create_electron_router() -> APIRouter:
    router = APIRouter()
    router.include_router(create_electron_folders_router())
    router.include_router(create_electron_images_router())
    router.include_router(create_electron_config_router())
    router.include_router(create_electron_runs_plan_router())
    router.include_router(create_electron_runs_lifecycle_router())
    router.include_router(create_electron_scope_router())
    return router
