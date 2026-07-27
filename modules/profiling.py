"""
Request profiling and event loop health monitoring for FastAPI.

Components:
- RequestTracker: tracks in-flight and slow requests
- EventLoopMonitor: measures event loop responsiveness (detects blocking)
- ProfilingMiddleware: Starlette middleware that times every request
- setup_profiling(): wires everything together
"""

import asyncio
import logging
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass

logger = logging.getLogger("image_scoring.performance")

# ---------------------------------------------------------------------------
# RequestRecord
# ---------------------------------------------------------------------------

@dataclass
class RequestRecord:
    request_id: str
    method: str
    path: str
    start_time: float        # perf_counter
    start_wall: float        # time.time
    loop_lag_at_start: float  # ms
    end_time: float | None = None
    status_code: int | None = None
    error: str | None = None

    @property
    def duration_ms(self) -> float:
        end = self.end_time or time.perf_counter()
        return (end - self.start_time) * 1000


# ---------------------------------------------------------------------------
# RequestTracker
# ---------------------------------------------------------------------------

class RequestTracker:
    """Thread-safe tracker for in-flight and recently completed requests."""

    def __init__(self, slow_threshold_ms: float = 1000,
                 very_slow_threshold_ms: float = 5000,
                 history_size: int = 200):
        self._lock = threading.Lock()
        self._in_flight: dict[str, RequestRecord] = {}
        self._slow_history: deque = deque(maxlen=history_size)
        self._total_requests = 0
        self._total_slow = 0
        self._total_errors = 0
        self._peak_concurrent = 0
        self.slow_threshold_ms = slow_threshold_ms
        self.very_slow_threshold_ms = very_slow_threshold_ms

    def start_request(self, record: RequestRecord):
        with self._lock:
            self._in_flight[record.request_id] = record
            self._total_requests += 1
            concurrent = len(self._in_flight)
            self._peak_concurrent = max(self._peak_concurrent, concurrent)

    def finish_request(self, request_id: str, status_code: int, error: str = None):
        with self._lock:
            record = self._in_flight.pop(request_id, None)
        if record is None:
            return
        record.end_time = time.perf_counter()
        record.status_code = status_code
        record.error = error
        duration = record.duration_ms

        if duration >= self.very_slow_threshold_ms:
            logger.error(
                "[SLOW REQUEST] %s %s -> %d in %.0fms (VERY SLOW, loop_lag=%.0fms)",
                record.method, record.path, status_code, duration,
                record.loop_lag_at_start,
            )
            with self._lock:
                self._total_slow += 1
                self._slow_history.append(record)
        elif duration >= self.slow_threshold_ms:
            logger.warning(
                "[SLOW REQUEST] %s %s -> %d in %.0fms (loop_lag=%.0fms)",
                record.method, record.path, status_code, duration,
                record.loop_lag_at_start,
            )
            with self._lock:
                self._total_slow += 1
                self._slow_history.append(record)
        else:
            logger.debug(
                "[REQUEST] %s %s -> %d in %.1fms",
                record.method, record.path, status_code, duration,
            )

        if error:
            with self._lock:
                self._total_errors += 1

    def get_in_flight(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "method": r.method,
                    "path": r.path,
                    "duration_ms": round(r.duration_ms, 1),
                    "started_ago_s": round(time.time() - r.start_wall, 1),
                    "loop_lag_at_start_ms": round(r.loop_lag_at_start, 1),
                }
                for r in self._in_flight.values()
            ]

    def get_slow_history(self, limit: int = 50) -> list[dict]:
        with self._lock:
            items = list(self._slow_history)[-limit:]
        return [
            {
                "method": r.method,
                "path": r.path,
                "duration_ms": round(r.duration_ms, 1),
                "status_code": r.status_code,
                "timestamp": r.start_wall,
                "loop_lag_at_start_ms": round(r.loop_lag_at_start, 1),
                "error": r.error,
            }
            for r in reversed(items)
        ]

    def get_stats(self) -> dict:
        with self._lock:
            return {
                "total_requests": self._total_requests,
                "in_flight": len(self._in_flight),
                "peak_concurrent": self._peak_concurrent,
                "total_slow": self._total_slow,
                "total_errors": self._total_errors,
            }


# ---------------------------------------------------------------------------
# EventLoopMonitor
# ---------------------------------------------------------------------------

class EventLoopMonitor:
    """Measures event loop responsiveness by scheduling periodic callbacks.

    If synchronous code blocks the loop, the actual sleep duration will far
    exceed the requested interval — the difference is the "lag".
    """

    def __init__(self, interval_ms: float = 200, lag_warn_ms: float = 500,
                 lag_error_ms: float = 2000, history_size: int = 300):
        self.interval_ms = interval_ms
        self.lag_warn_ms = lag_warn_ms
        self.lag_error_ms = lag_error_ms
        self._history: deque = deque(maxlen=history_size)
        self._current_lag: float = 0.0
        self._peak_lag: float = 0.0
        self._total_warnings: int = 0
        self._task: asyncio.Task | None = None
        self._running = False

    @property
    def current_lag_ms(self) -> float:
        return self._current_lag

    async def start(self):
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info(
            "[PROFILING] Event loop monitor started (interval=%dms, warn=%dms)",
            self.interval_ms, self.lag_warn_ms,
        )

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _monitor_loop(self):
        interval_s = self.interval_ms / 1000.0
        while self._running:
            t0 = time.perf_counter()
            await asyncio.sleep(interval_s)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            lag_ms = max(0, elapsed_ms - self.interval_ms)

            self._current_lag = lag_ms
            self._peak_lag = max(self._peak_lag, lag_ms)

            self._history.append((time.time(), lag_ms))

            if lag_ms >= self.lag_error_ms:
                logger.error(
                    "[EVENT LOOP BLOCKED] Lag: %.0fms (expected %dms, actual %.0fms)",
                    lag_ms, self.interval_ms, elapsed_ms,
                )
                self._total_warnings += 1
            elif lag_ms >= self.lag_warn_ms:
                logger.warning(
                    "[EVENT LOOP LAG] Lag: %.0fms (expected %dms, actual %.0fms)",
                    lag_ms, self.interval_ms, elapsed_ms,
                )
                self._total_warnings += 1

    def get_stats(self) -> dict:
        recent = list(self._history)
        lags = [lag for _, lag in recent]
        sorted_lags = sorted(lags) if lags else []
        return {
            "current_lag_ms": round(self._current_lag, 1),
            "peak_lag_ms": round(self._peak_lag, 1),
            "avg_lag_ms": round(sum(lags) / len(lags), 1) if lags else 0,
            "p95_lag_ms": round(sorted_lags[int(len(sorted_lags) * 0.95)], 1) if sorted_lags else 0,
            "total_warnings": self._total_warnings,
            "history_size": len(recent),
            "monitoring_interval_ms": self.interval_ms,
        }

    def get_recent_lags(self, limit: int = 60) -> list[dict]:
        items = list(self._history)[-limit:]
        return [{"timestamp": ts, "lag_ms": round(lag, 1)} for ts, lag in items]


# ---------------------------------------------------------------------------
# ProfilingMiddleware
# ---------------------------------------------------------------------------

# Paths to skip (Gradio internals, static assets)
_SKIP_PREFIXES = (
    "/gradio_api/queue/",
    "/gradio_api/upload",
    "/assets/",
    "/favicon.ico",
    "/static/",
)


class ProfilingMiddleware:
    """Pure ASGI middleware — does not wrap the response body.

    Starlette's ``BaseHTTPMiddleware`` buffers ASGI ``http.response.*`` messages and
    breaks streaming/SSE and some mounted apps (e.g. MCP over SSE), causing
    ``AssertionError: Unexpected message: http.response.start``.
    """

    def __init__(self, app, tracker: RequestTracker, loop_monitor: EventLoopMonitor):
        self.app = app
        self.tracker = tracker
        self.loop_monitor = loop_monitor

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "?")
        if any(path.startswith(p) for p in _SKIP_PREFIXES):
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex[:12]
        record = RequestRecord(
            request_id=request_id,
            method=scope.get("method", "GET"),
            path=path,
            start_time=time.perf_counter(),
            start_wall=time.time(),
            loop_lag_at_start=self.loop_monitor.current_lag_ms,
        )
        self.tracker.start_request(record)

        status_code: int | None = None

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status")
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
            self.tracker.finish_request(request_id, status_code or 200)
        except Exception as exc:
            self.tracker.finish_request(request_id, status_code or 500, error=str(exc))
            raise


# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------

_tracker: RequestTracker | None = None
_loop_monitor: EventLoopMonitor | None = None


def get_tracker() -> RequestTracker | None:
    return _tracker


def get_loop_monitor() -> EventLoopMonitor | None:
    return _loop_monitor


def setup_profiling(app) -> None:
    """Initialize and attach profiling to a FastAPI app.

    Call after CORS middleware so profiling wraps everything.
    The EventLoopMonitor must be started separately in the lifespan handler.
    """
    global _tracker, _loop_monitor

    from modules.config import get_config_section
    prof_cfg = get_config_section("profiling") or {}

    _loop_monitor = EventLoopMonitor(
        interval_ms=prof_cfg.get("loop_monitor_interval_ms", 200),
        lag_warn_ms=prof_cfg.get("loop_lag_warn_ms", 500),
        lag_error_ms=prof_cfg.get("loop_lag_error_ms", 2000),
    )
    _tracker = RequestTracker(
        slow_threshold_ms=prof_cfg.get("slow_threshold_ms", 1000),
        very_slow_threshold_ms=prof_cfg.get("very_slow_threshold_ms", 5000),
    )

    app.add_middleware(ProfilingMiddleware, tracker=_tracker, loop_monitor=_loop_monitor)
    logger.info("[PROFILING] Middleware installed")
