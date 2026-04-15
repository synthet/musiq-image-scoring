"""Shared log path resolution and tail reading for status HTML, JSON API, and MCP."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from modules import utils
from modules.config import BASE_DIR

DEFAULT_LOG_TAIL_LINES = 100
MAX_LOG_TAIL_LINES = 2000


def resolve_webui_log_path() -> Path:
    """Prefer BASE_DIR/webui.log; if missing, use cwd/webui.log (same as status page)."""
    candidates = [BASE_DIR / "webui.log", Path.cwd() / "webui.log"]
    return next((p for p in candidates if p.exists()), candidates[0])


def resolve_debug_log_path() -> Path:
    return Path(utils.get_debug_log_path())


def read_log_tail(resolved_path: Path, max_lines: int) -> dict[str, Any]:
    """Read the last max_lines from a text log file.

    Returns dict with: path (str), exists (bool), lines (list[str]), total_lines (int|None),
    error (str|None).
    """
    path_str = str(resolved_path)
    if not resolved_path.exists():
        return {
            "path": path_str,
            "exists": False,
            "lines": [],
            "total_lines": None,
            "error": None,
        }
    try:
        with open(resolved_path, "r", encoding="utf-8", errors="replace") as fh:
            all_lines = fh.readlines()
    except OSError as e:
        return {
            "path": path_str,
            "exists": True,
            "lines": [],
            "total_lines": None,
            "error": str(e),
        }
    total = len(all_lines)
    n = max(0, max_lines)
    chunk = all_lines[-n:] if n else []
    out = [line.rstrip("\n\r") for line in chunk]
    return {
        "path": path_str,
        "exists": True,
        "lines": out,
        "total_lines": total,
        "error": None,
    }


def clamp_tail_lines(lines: int) -> int:
    try:
        n = int(lines)
    except (TypeError, ValueError):
        n = DEFAULT_LOG_TAIL_LINES
    if n < 1:
        n = 1
    return min(n, MAX_LOG_TAIL_LINES)


def build_log_tails_payload(sources: str, lines: int) -> dict[str, Any]:
    """Build JSON-serialisable payload for GET /api/status/log-tails.

    Raises ValueError if ``sources`` is not one of: all, webui, debug.
    """
    n = clamp_tail_lines(lines)
    spec = (sources or "all").strip().lower()
    if spec in ("all", "*", ""):
        ids = ("webui", "debug")
    elif spec in ("webui", "debug"):
        ids = (spec,)
    else:
        raise ValueError("sources must be 'all', 'webui', or 'debug'")

    out_sources: list[dict[str, Any]] = []
    for sid in ids:
        path = resolve_webui_log_path() if sid == "webui" else resolve_debug_log_path()
        tail = read_log_tail(path, n)
        out_sources.append(
            {
                "id": sid,
                "path": tail["path"],
                "exists": tail["exists"],
                "lines": tail["lines"],
                "total_lines": tail["total_lines"],
                "error": tail["error"],
            }
        )

    return {
        "ts": datetime.now().strftime("%H:%M:%S"),
        "lines_requested": n,
        "sources": out_sources,
    }
