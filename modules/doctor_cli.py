"""
Local health checks for humans and CI (see scripts/doctor.py and docs/DIAGNOSTICS.md).

Reuses config validation and DB init paths; optional GPU section via MCP helper.
"""

from __future__ import annotations

import platform
import sys
from typing import Any

from modules.redact_sensitive import redact_json_obj

__all__ = [
    "aggregate_status",
    "format_report",
    "redact_json_obj",
    "run_doctor",
]


def aggregate_status(has_fail: bool, has_warn: bool) -> str:
    if has_fail:
        return "FAIL"
    if has_warn:
        return "WARN"
    return "PASS"


def _try_gpu_snapshot() -> dict[str, Any]:
    """Best-effort GPU info; never raises."""
    out: dict[str, Any] = {"skipped": False, "error": None, "available": None, "devices": []}
    try:
        import torch

        out["available"] = bool(torch.cuda.is_available())
        if out["available"]:
            n = torch.cuda.device_count()
            out["devices"] = [torch.cuda.get_device_name(i) for i in range(n)]
    except Exception as e:  # noqa: BLE001 — diagnostic helper
        out["error"] = str(e)
    return out


def _try_pgvector(conn) -> dict[str, Any]:
    """Return extension presence when on PostgreSQL connector; soft-fail otherwise."""
    out: dict[str, Any] = {"checked": False, "present": None, "note": None}
    try:
        row = conn.query_one("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector') AS ok")
        if row is not None and "ok" in row:
            out["checked"] = True
            out["present"] = bool(row.get("ok"))
        elif row is not None:
            out["checked"] = True
            out["present"] = bool(next(iter(row.values()), False))
    except Exception as e:  # noqa: BLE001
        out["note"] = str(e)
    return out


def run_doctor(*, include_gpu: bool = True) -> dict[str, Any]:
    """
    Run checks and return a structured report (no printing).

    Side effects: may call db.init_db() via prepare_mcp_embedded().
    """
    from modules import config
    from modules.mcp_server import get_database_engine_info, prepare_mcp_embedded

    lines: list[str] = []
    fails: list[str] = []
    warns: list[str] = []

    lines.append("Runtime")
    lines.append(f"- OS: {platform.system()} {platform.release()}")
    lines.append(f"- Python: {sys.version.split()[0]} ({sys.executable})")

    cfg = config.validate_config()
    lines.append("")
    lines.append("Configuration (structural)")
    if cfg.get("ok"):
        lines.append("- config validation: OK")
    else:
        lines.append("- config validation: FAIL")
        for issue in cfg.get("issues") or []:
            lines.append(f"  - {issue}")
            fails.append(f"config:{issue}")
    for w in cfg.get("warnings") or []:
        lines.append(f"- warning: {w}")
        warns.append(f"config:{w}")

    db_ok = prepare_mcp_embedded()
    lines.append("")
    lines.append("Database")
    if not db_ok:
        lines.append("- init_db / connector: not available")
        le = None
        try:
            from modules import mcp_server as _mcp

            le = getattr(_mcp, "_last_db_error", None)
        except Exception:
            pass
        if le:
            lines.append(f"  - last error: {le}")
        fails.append("database:unavailable")
    else:
        lines.append("- init_db / connector: OK")

    eng = get_database_engine_info()
    lines.append(f"- engine (config): {eng.get('database_engine_config')}")
    if eng.get("connector_error"):
        lines.append(f"- connector: ERROR {eng['connector_error']}")
        fails.append("database:connector")
    ping = eng.get("ping_ok")
    if ping is True:
        lines.append("- ping (simple query): OK")
    elif ping is False:
        lines.append(f"- ping: FAIL ({eng.get('ping_error')})")
        fails.append("database:ping")
    else:
        lines.append(f"- ping: skipped ({eng.get('ping_note', 'n/a')})")
        warns.append("database:ping_skipped")

    if db_ok and ping is True:
        try:
            from modules import db as _db

            conn = _db.get_connector()
            ctype = getattr(conn, "type", type(conn).__name__)
            if ctype == "postgres" or "postgres" in str(type(conn)).lower():
                pv = _try_pgvector(conn)
                if pv["checked"]:
                    lines.append(f"- pgvector extension: {'OK' if pv['present'] else 'MISSING'}")
                    if not pv["present"]:
                        fails.append("database:pgvector_missing")
                elif pv.get("note"):
                    lines.append(f"- pgvector extension: not checked ({pv['note']})")
                    warns.append("database:pgvector_unknown")
        except Exception as e:  # noqa: BLE001
            lines.append(f"- pgvector extension: check error ({e})")
            warns.append("database:pgvector_error")

    lines.append("")
    lines.append("GPU (optional)")
    if include_gpu:
        g = _try_gpu_snapshot()
        if g.get("error"):
            lines.append(f"- torch / CUDA: WARN ({g['error']})")
            warns.append("gpu:torch_error")
        elif g.get("available"):
            lines.append("- CUDA: available")
            for name in g.get("devices") or []:
                lines.append(f"  - {name}")
        else:
            lines.append("- CUDA: not available (CPU path)")
    else:
        lines.append("- skipped (--no-gpu)")

    overall = aggregate_status(bool(fails), bool(warns))
    return {
        "overall": overall,
        "lines": lines,
        "failures": fails,
        "warnings": warns,
        "config": cfg,
        "database_engine_info": eng,
    }


def format_report(result: dict[str, Any]) -> str:
    header = "Project Doctor Report\n====================="
    body = "\n".join(result.get("lines") or [])
    footer = f"\n\nOverall: {result.get('overall', '?')}\n"
    return f"{header}\n\n{body}{footer}"
