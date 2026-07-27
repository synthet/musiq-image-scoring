"""API routes: debug (extracted from modules.api)."""

from __future__ import annotations

import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)


import sys


def _api_module():
    return sys.modules["modules.api"]



def create_debug_router() -> APIRouter:
    router = APIRouter()
    # ========== Debug / Profiling Endpoints ==========

    @router.get(
        "/debug/requests",
        summary="Request profiling dashboard",
        tags=["Debug"],
    )
    async def debug_requests():
        """In-flight requests, slow request history, and event loop health."""
        from modules.profiling import get_loop_monitor, get_tracker

        tracker = get_tracker()
        monitor = get_loop_monitor()
        if tracker is None:
            return {"error": "Profiling not initialized"}

        return {
            "request_stats": tracker.get_stats(),
            "in_flight": tracker.get_in_flight(),
            "slow_requests": tracker.get_slow_history(limit=30),
            "event_loop": monitor.get_stats() if monitor else {},
            "event_loop_recent": monitor.get_recent_lags(limit=30) if monitor else [],
        }

    @router.get(
        "/debug/loop-lag",
        summary="Current event loop lag",
        tags=["Debug"],
    )
    async def debug_loop_lag():
        """Quick event loop health check."""
        from modules.profiling import get_loop_monitor

        monitor = get_loop_monitor()
        if not monitor:
            return {"lag_ms": -1, "status": "monitor_not_running"}
        lag = monitor.current_lag_ms
        status = "healthy" if lag < 200 else "degraded" if lag < 1000 else "blocked"
        return {"lag_ms": round(lag, 1), "status": status}


    return router
