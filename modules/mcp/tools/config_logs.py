"""MCP tool implementations — config_logs (extracted from modules.mcp_server)."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
from typing import Any, Optional

from modules import config, db
from modules.mcp import tool_support as ts

logger = logging.getLogger(__name__)

    from modules import mcp_server as _ms
def get_model_status() -> dict:
    """Get status of registered scoring models, GPU availability, and CUDA/PyTorch/TensorFlow configuration."""
    status = {
        "models": {},
        "gpu": {},
        "scorer_available": False
    }

    try:
        # Registry-driven model list (topiq, qpt_v2, MUSIQ family, LIQE, LLM-judge).
        try:
            status["models"] = ts.registry_model_status()
        except Exception as e:
            status["models"]["registry_error"] = str(e)

        if _ms._scoring_runner and _scoring_runner.shared_scorer:
            status["scorer_available"] = True
            scorer = _scoring_runner.shared_scorer
            try:
                status["models"]["version"] = getattr(scorer, 'VERSION', 'unknown')
            except Exception:
                pass
        else:
            status["models"]["note"] = "Scorer not initialized (models load lazily on first scoring run)"

        try:
            import tensorflow as tf
            gpus = tf.config.list_physical_devices('GPU')
            status["gpu"]["tensorflow_available"] = True
            status["gpu"]["physical_gpus"] = len(gpus)
            status["gpu"]["cuda_built"] = tf.test.is_built_with_cuda()
            if gpus:
                status["gpu"]["gpu_names"] = [str(gpu) for gpu in gpus]
        except ImportError:
            status["gpu"]["tensorflow_available"] = False
        except Exception as e:
            status["gpu"]["error"] = str(e)

        try:
            import torch
            status["gpu"]["pytorch_available"] = True
            status["gpu"]["pytorch_cuda_available"] = torch.cuda.is_available()
            if torch.cuda.is_available():
                status["gpu"]["pytorch_device_count"] = torch.cuda.device_count()
                status["gpu"]["pytorch_device_name"] = torch.cuda.get_device_name(0)
        except ImportError:
            status["gpu"]["pytorch_available"] = False
        except Exception as e:
            status["gpu"]["pytorch_error"] = str(e)

        try:
            import subprocess
            result = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader'],
                                    capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                status["gpu"]["nvidia_driver"] = "available"
                lines = result.stdout.strip().split('\n')
                status["gpu"]["gpu_info"] = lines
            else:
                status["gpu"]["nvidia_driver"] = "not_available"
        except (OSError, Exception):
            status["gpu"]["nvidia_driver"] = "not_checked"

    except Exception as e:
        status["error"] = str(e)

    return status


    from modules import mcp_server as _ms
def get_config() -> dict:
    """Get current application configuration (config.json merged with environment.json). Sensitive keys are redacted."""
    from modules.redact_sensitive import redact_json_obj

    cfg = redact_json_obj(config.load_config())
    if not isinstance(cfg, dict):
        cfg = {"_raw": cfg}
    cfg = dict(cfg)
    cfg["_mcp_status"] = {
        "db_available": _ms._db_available,
        "last_db_error": _ms._last_db_error,
        "version": "1.0.1-resilient",
    }
    return cfg


    from modules import mcp_server as _ms
def validate_config() -> dict:
    """Validate config structure and referenced paths; optionally ping the database when available."""
    out = dict(config.validate_config())
    out["config_path"] = str(config.CONFIG_FILE)
    out["environment_path"] = str(config.ENVIRONMENT_FILE)
    if _ms._db_available:
        try:
            with db.connection() as conn:
                c = conn.cursor()
                c.execute("SELECT 1")
                c.fetchone()
            out["database_reachable"] = True
        except Exception as e:
            out["database_reachable"] = False
            out["database_error"] = str(e)
    else:
        out["database_reachable"] = None
        out["database_note"] = "Database not initialized; structural checks only."
    return out


def set_config_value(key: str, value: Any) -> dict:
    """Set a configuration value in config.json."""
    try:
        config.save_config_value(key, value)
        return {"success": True, "key": key, "value": value}
    except Exception as e:
        return {"success": False, "error": str(e)}


def read_debug_log(lines: int = 100) -> dict:
    """Read recent entries from debug.log (JSON lines); falls back to raw line in entries."""
    from modules.ui import log_views

    n = log_views.clamp_tail_lines(lines)
    path = log_views.resolve_debug_log_path()
    tail = log_views.read_log_tail(path, n)
    if not tail["exists"]:
        return {"error": "Debug log file not found", "path": tail["path"]}
    if tail.get("error"):
        return {"error": tail["error"], "path": tail["path"]}

    entries = []
    for line in tail["lines"]:
        try:
            entries.append(json.loads(line.strip()))
        except (json.JSONDecodeError, ValueError):
            entries.append({"raw": line.strip()})

    return {
        "path": tail["path"],
        "total_lines": tail["total_lines"],
        "returned_lines": len(entries),
        "entries": entries,
    }


def get_server_log_tail(sources: str = "all", lines: int = 100) -> dict:
    """Tail webui.log and/or debug.log (same paths and caps as GET /api/status/log-tails)."""
    from modules.ui import log_views

    try:
        return log_views.build_log_tails_payload(sources, lines)
    except ValueError as e:
        return {"error": str(e)}


def search_logs(
    pattern: str,
    sources: str = "all",
    context_lines: int = 2,
    max_lines_scan: int = 25000,
    max_matches_per_file: int = 40,
    case_insensitive: bool = True,
) -> dict:
    """Search the tail of ``webui.log`` / ``debug.log`` for a regex ``pattern``; returns matching lines with optional context."""
    from modules.ui import log_views

    spec = (sources or "all").strip().lower()
    if spec in ("all", "*", ""):
        file_ids = ("webui", "debug")
    elif spec in ("webui", "debug"):
        file_ids = (spec,)
    else:
        return {"error": "sources must be 'all', 'webui', or 'debug'"}

    ctx = max(0, min(int(context_lines), 50))
    max_scan = max(100, min(int(max_lines_scan), 100_000))
    cap = max(1, min(int(max_matches_per_file), 200))
    flags = re.IGNORECASE if case_insensitive else 0
    try:
        rx = re.compile(pattern, flags)
    except re.error as e:
        return {"error": f"invalid_regex: {e}"}

    out: dict[str, Any] = {"pattern": pattern, "matches": []}

    for sid in file_ids:
        path = log_views.resolve_webui_log_path() if sid == "webui" else log_views.resolve_debug_log_path()
        tail = log_views.read_log_tail(path, max_scan)
        lines = tail.get("lines") or []
        total = tail.get("total_lines")
        if not lines:
            continue
        base = int(total or len(lines)) - len(lines)
        n_matches = 0
        for i, line in enumerate(lines):
            if not rx.search(line):
                continue
            lo = max(0, i - ctx)
            hi = min(len(lines), i + ctx + 1)
            out["matches"].append(
                {
                    "source": sid,
                    "path": tail.get("path"),
                    "line_number": base + i + 1,
                    "line": line[:4000],
                    "context_before": lines[lo:i],
                    "context_after": lines[i + 1 : hi],
                }
            )
            n_matches += 1
            if n_matches >= cap:
                break

    return out

