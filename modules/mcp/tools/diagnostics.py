"""MCP tool implementations — diagnostics (extracted from modules.mcp_server)."""

from __future__ import annotations

import logging
import os
from typing import Any

from modules import config, db
from modules.mcp import tool_support as ts

logger = logging.getLogger(__name__)

def get_incomplete_images(limit: int = 100) -> list:
    """Images with missing composite scores, model scores, rating, or label (broader than get_failed_images)."""
    try:
        rows = db.get_incomplete_records(limit=limit)
        return [ts.sanitize_for_mcp(dict(row)) for row in rows]
    except Exception as e:
        return [{"error": str(e)}]


def get_failed_images(limit: int = 50, offset: int = 0) -> dict:
    """Images missing key quality scores (NULL or <= 0): general, technical, spaq, koniq, ava, paq2piq, liqe.

    Narrower than ``get_incomplete_images`` (no rating/label requirement). See also ``get_error_summary`` for counts.
    """
    lim = max(1, min(int(limit), 500))
    off = max(0, int(offset))
    or_parts = [f"(i.{col} IS NULL OR i.{col} <= 0)" for col, _ in ts.AGGREGATE_FAIL_COLUMNS]
    or_parts.extend(
        f"(ims.score_{name} IS NULL OR ims.score_{name} <= 0)" for name in ts.PER_MODEL_FAIL_LABELS
    )
    where_sql = "(" + " OR ".join(or_parts) + ")"
    conn = db.get_connector()
    try:
        count_row = conn.query_one(
            f"SELECT COUNT(*) AS c FROM images i LEFT JOIN ({ts.IMS_OVERLAY_SUBQUERY}) ims ON ims.image_id = i.id WHERE {where_sql}",
            (),
        )
        total = int((count_row or {}).get("c") or 0)
        rows = conn.query(
            f"""
            SELECT i.id, i.file_path, i.score_general, i.score_technical,
                   ims.score_spaq, ims.score_ava, ims.score_liqe,
                   ims.score_koniq, ims.score_paq2piq,
                   i.created_at
            FROM images i
            LEFT JOIN ({ts.IMS_OVERLAY_SUBQUERY}) ims ON ims.image_id = i.id
            WHERE {where_sql}
            ORDER BY i.created_at DESC NULLS LAST, i.id DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
            """,
            (off, lim),
        )
    except Exception as e:
        return {"error": str(e), "items": [], "total": 0}

    items = []
    for r in rows or []:
        d = dict(r)
        missing = []
        for col, label in ts.AGGREGATE_FAIL_COLUMNS:
            v = d.get(col)
            if v is None or (isinstance(v, (int, float)) and v <= 0):
                missing.append(label)
        for name in ts.PER_MODEL_FAIL_LABELS:
            v = d.get(f"score_{name}")
            if v is None or (isinstance(v, (int, float)) and v <= 0):
                missing.append(name)
        d["missing_scores"] = missing
        items.append(ts.sanitize_for_mcp(d))

    return {"total": total, "offset": off, "limit": lim, "items": items}


def get_error_summary() -> dict:
    """Get summary of errors and issues in the database including failed jobs and missing scores."""
    with db.connection() as conn:
        c = conn.cursor()
        summary = {}

        try:
            c.execute("SELECT COUNT(*) FROM jobs WHERE status = 'failed'")
            summary["failed_jobs"] = c.fetchone()[0]

            c.execute("""
                SELECT COUNT(*) FROM images
                WHERE score_general IS NULL OR score_general = 0
            """)
            summary["images_missing_general_score"] = c.fetchone()[0]

            c.execute("""
                SELECT COUNT(*) FROM images
                WHERE score_technical IS NULL OR score_technical = 0
            """)
            summary["images_missing_technical_score"] = c.fetchone()[0]

            models = ["spaq", "koniq", "ava", "paq2piq", "liqe"]
            for model in models:
                col = f"score_{model}"
                key = f"images_missing_{model}"
                try:
                    # Postgres: per-model columns were dropped in Alembic 0023; compute
                    # missing counts from the normalized ``image_model_scores`` overlay.
                    c.execute(
                        f"""
                        SELECT COUNT(*)
                        FROM images i
                        LEFT JOIN ({ts.IMS_OVERLAY_SUBQUERY}) ims ON ims.image_id = i.id
                        WHERE ims.{col} IS NULL OR ims.{col} <= 0
                        """
                    )
                    summary[key] = c.fetchone()[0]
                except Exception as overlay_err:
                    try:
                        # Legacy fallback (Firebird/older Postgres installs).
                        c.execute(
                            f"""
                            SELECT COUNT(*)
                            FROM images
                            WHERE {col} IS NULL OR {col} = 0
                            """
                        )
                        summary[key] = c.fetchone()[0]
                    except Exception as legacy_err:
                        # Don't silently omit the key — surface the failure so callers
                        # can tell "no data" apart from "query broke".
                        logger.warning(
                            "get_error_summary: %s unavailable (overlay=%s, legacy=%s)",
                            col,
                            overlay_err,
                            legacy_err,
                        )
                        summary[key] = None
                        summary.setdefault("_errors", []).append(
                            {"field": key, "reason": str(legacy_err)[:200]}
                        )

            c.execute("SELECT COUNT(*) FROM images WHERE folder_id IS NULL")
            summary["orphaned_images"] = c.fetchone()[0]

            c.execute("""
                SELECT COUNT(*) FROM images WHERE file_path IS NULL OR file_path = ''
            """)
            summary["images_with_empty_paths"] = c.fetchone()[0]

            c.execute("""
                SELECT id, input_path, status, log, created_at
                FROM jobs
                WHERE status = 'failed'
                ORDER BY created_at DESC
                FETCH FIRST 10 ROWS ONLY
            """)
            summary["recent_failed_jobs"] = [dict(row) for row in c.fetchall()]

        except Exception as e:
            summary["error"] = str(e)

        try:
            stale = db.list_stale_running_image_phase_rows(min_age_seconds=3600, limit=1)
            summary["stale_running_count"] = int(stale.get("count_estimate") or 0)
        except Exception:
            summary["stale_running_count"] = None

        return summary


def check_database_health() -> dict:
    """Check database for inconsistencies, orphaned records, and data integrity issues."""
    with db.connection() as conn:
        c = conn.cursor()
        health = {
            "status": "healthy",
            "issues": [],
            "warnings": []
        }

        try:
            c.execute("""
                SELECT COUNT(*) FROM images i
                LEFT JOIN folders f ON i.folder_id = f.id
                WHERE i.folder_id IS NOT NULL AND f.id IS NULL
            """)
            orphaned_count = c.fetchone()[0]
            if orphaned_count > 0:
                health["issues"].append(f"{orphaned_count} images with invalid folder_id")
                health["status"] = "unhealthy"

            c.execute("""
                SELECT COUNT(*) FROM images i
                LEFT JOIN stacks s ON i.stack_id = s.id
                WHERE i.stack_id IS NOT NULL AND s.id IS NULL
            """)
            orphaned_stacks = c.fetchone()[0]
            if orphaned_stacks > 0:
                health["issues"].append(f"{orphaned_stacks} images with invalid stack_id")
                health["status"] = "unhealthy"

            c.execute("""
                SELECT file_path, COUNT(*) as cnt
                FROM images
                WHERE file_path IS NOT NULL
                GROUP BY file_path
                HAVING COUNT(*) > 1
            """)
            duplicates = c.fetchall()
            if duplicates:
                health["warnings"].append(f"{len(duplicates)} duplicate file paths found")

            c.execute("""
                SELECT COUNT(*) FROM images
                WHERE image_hash IS NOT NULL AND (file_path IS NULL OR file_path = '')
            """)
            hash_no_path = c.fetchone()[0]
            if hash_no_path > 0:
                health["warnings"].append(f"{hash_no_path} images with hash but no path")

            c.execute("""
                SELECT COUNT(*) FROM folders f
                LEFT JOIN images i ON f.id = i.folder_id
                WHERE i.id IS NULL
            """)
            empty_folders = c.fetchone()[0]
            if empty_folders > 0:
                health["warnings"].append(f"{empty_folders} folders with no images")

            c.execute("""
                SELECT COUNT(*) FROM stacks s
                LEFT JOIN images i ON s.id = i.stack_id
                WHERE i.id IS NULL
            """)
            empty_stacks = c.fetchone()[0]
            if empty_stacks > 0:
                health["warnings"].append(f"{empty_stacks} stacks with no images")

            try:
                stale_ph = db.list_stale_running_image_phase_rows(min_age_seconds=3600, limit=1)
                n_stale = int(stale_ph.get("count_estimate") or 0)
                if n_stale > 0:
                    health["warnings"].append(
                        f"{n_stale} image_phase_status row(s) stuck in running >3600s "
                        "(folder phase badges may drift; MCP tool get_stale_running_phase_status)"
                    )
            except Exception:
                pass

            health["summary"] = {
                "total_issues": len(health["issues"]),
                "total_warnings": len(health["warnings"])
            }

        except Exception as e:
            health["status"] = "error"
            health["error"] = str(e)

        return health


def validate_file_paths(
    limit: int = 100,
    folder_path: str | None = None,
    missing_only: bool = False,
) -> dict:
    """Validate that image ``file_path`` values exist on disk. Optional ``folder_path`` restricts to images under that folder path (exact ``folders.path`` match or descendants). When ``missing_only`` is true, only missing files are listed (scans up to ``limit`` missing rows, expanding the DB fetch window)."""
    lim = max(1, min(int(limit), 5000))
    fetch_cap = lim if not missing_only else min(20_000, max(lim * 20, lim))
    conn = db.get_connector()
    results: dict[str, Any] = {
        "checked": 0,
        "exists": 0,
        "missing": 0,
        "missing_files": [],
        "folder_path": os.path.normpath(folder_path.strip()) if folder_path and str(folder_path).strip() else None,
        "missing_only": bool(missing_only),
    }

    try:
        if results["folder_path"]:
            norm = results["folder_path"]
            plike_u = norm + "/%"
            plike_w = norm + "\\%"
            rows = conn.query(
                """
                SELECT i.id, i.file_path FROM images i
                INNER JOIN folders f ON f.id = i.folder_id
                WHERE i.file_path IS NOT NULL AND TRIM(i.file_path) != ''
                  AND (f.path = ? OR f.path LIKE ? OR f.path LIKE ?)
                ORDER BY i.created_at DESC NULLS LAST, i.id DESC
                FETCH FIRST ? ROWS ONLY
                """,
                (norm, plike_u, plike_w, fetch_cap),
            )
        else:
            rows = conn.query(
                """
                SELECT id, file_path FROM images
                WHERE file_path IS NOT NULL AND TRIM(file_path) != ''
                ORDER BY created_at DESC NULLS LAST, id DESC
                FETCH FIRST ? ROWS ONLY
                """,
                (fetch_cap,),
            )
    except Exception as e:
        results["error"] = str(e)
        return results

    examined = 0
    for row in rows or []:
        rid = row.get("id")
        file_path = row.get("file_path")
        if not file_path:
            continue
        examined += 1
        if os.path.exists(file_path):
            results["exists"] += 1
            if missing_only:
                continue
        else:
            results["missing"] += 1
            results["missing_files"].append({"id": rid, "file_path": file_path})
        if missing_only:
            if results["missing"] >= lim:
                break
        elif examined >= lim:
            break

    results["checked"] = examined
    return results


def diagnose_phase_consistency(image_id: int, folder_path: str | None = None) -> dict:
    """Diagnose folder vs per-image phase status mismatch (e.g. folder shows 69/69 KEYWORDS done but image shows Pending).
    Returns image info, folder info, phase statuses, and whether the image is in the folder's phase aggregate set."""
    result = {"image_id": image_id, "image": None, "folder": None, "phase_statuses": None, "in_folder_set": None}
    try:
        with db.connection() as conn:
            c = conn.cursor()
            c.execute(
                "SELECT id, file_path, file_name, folder_id FROM images WHERE id = ?",
                (image_id,)
            )
            row = c.fetchone()
            if not row:
                result["error"] = f"Image {image_id} not found"
                return result

            result["image"] = {
                "id": row[0],
                "file_path": row[1],
                "file_name": row[2],
                "folder_id": row[3],
            }

            folder_id = row[3]
            if folder_id:
                c.execute("SELECT id, path FROM folders WHERE id = ?", (folder_id,))
                frow = c.fetchone()
                if frow:
                    result["folder"] = {"id": frow[0], "path": frow[1]}

            result["phase_statuses"] = db.get_image_phase_statuses(image_id)

            target_path = folder_path or (result.get("folder") or {}).get("path")
            if target_path:
                from modules import utils
                wsl_path = utils.convert_path_to_wsl(target_path) if hasattr(utils, "convert_path_to_wsl") else target_path
                path_like_unix = wsl_path + "/%"
                path_like_win = wsl_path + "\\%"
                c.execute(
                    """
                    SELECT COUNT(*) FROM images
                    WHERE folder_id IN (
                        SELECT id FROM folders
                        WHERE path = ? OR path LIKE ? OR path LIKE ?
                    )
                    """,
                    (wsl_path, path_like_unix, path_like_win),
                )
                folder_image_count = c.fetchone()[0]
                c.execute(
                    """
                    SELECT 1 FROM images i
                    JOIN folders f ON f.id = i.folder_id
                    WHERE i.id = ? AND (f.path = ? OR f.path LIKE ? OR f.path LIKE ?)
                    """,
                    (image_id, wsl_path, path_like_unix, path_like_win),
                )
                in_set = c.fetchone() is not None
                result["folder_aggregate"] = {
                    "folder_path_used": target_path,
                    "image_count_in_folder": folder_image_count,
                    "image_in_folder_set": in_set,
                }
    except Exception as e:
        result["error"] = str(e)
    return result


def get_stale_running_phase_status(min_age_seconds: int = 3600, limit: int = 50) -> dict:
    """Find image_phase_status rows stuck in ``running`` longer than ``min_age_seconds`` (folder rollup drift).

    Use after crashes or forced stops when folder badges still show ``running`` but jobs are terminal.
    """
    return db.list_stale_running_image_phase_rows(
        min_age_seconds=min_age_seconds,
        limit=limit,
    )


def get_database_engine_info() -> dict:
    """Summarize database.engine, connector mode, non-secret connection targets, and whether a simple query succeeds. Complements validate_config."""
    from modules import mcp_server as _ms

    engine = config.get_database_engine()
    out: dict[str, Any] = {
        "database_engine_config": engine,
        "mcp_db_initialized": bool(_ms._db_available),
        "connector_type": None,
        "targets": {},
        "ping_ok": None,
        "ping_error": None,
    }
    try:
        conn = db.get_connector()
        out["connector_type"] = getattr(conn, "type", type(conn).__name__)
    except Exception as e:
        out["connector_error"] = str(e)
        return out

    db_sec = config.get_config_section("database") or {}
    if engine == "api" or out.get("connector_type") == "api":
        out["targets"]["api_url"] = str(db_sec.get("api_url", "http://localhost:7860")).strip()
    if engine in ("postgres", "firebird") or out.get("connector_type") == "postgres":
        try:
            from modules import db_postgres as _dpg
            pg = _dpg.get_pg_config()
            out["targets"]["postgres"] = {
                "host": pg.get("host"),
                "port": pg.get("port"),
                "dbname": pg.get("dbname"),
                "user": pg.get("user"),
                "password_configured": bool(pg.get("password")),
            }
        except Exception as e:
            out["targets"]["postgres_error"] = str(e)

    if _ms._db_available:
        try:
            db.get_connector().query_one("SELECT 1 AS ok FROM images FETCH FIRST 1 ROWS ONLY")
            out["ping_ok"] = True
        except Exception as e:
            out["ping_ok"] = False
            out["ping_error"] = str(e)
    else:
        out["ping_ok"] = None
        out["ping_note"] = "Database not initialized in this MCP process."

    return out


def check_stack_invariants(limit: int = 20) -> dict:
    """Detect common stack data issues: single-image stacks, images pointing at missing stacks, stacks with no images. Returns counts and small samples."""
    lim = max(1, min(int(limit), 200))
    conn = db.get_connector()

    singleton = conn.query_one(
        """
        SELECT COUNT(*) AS c FROM (
            SELECT stack_id FROM images WHERE stack_id IS NOT NULL
            GROUP BY stack_id
            HAVING COUNT(*) = 1
        ) AS singletons
        """
    )
    orphan_img = conn.query_one(
        """
        SELECT COUNT(*) AS c FROM images i
        WHERE i.stack_id IS NOT NULL
        AND NOT EXISTS (SELECT 1 FROM stacks s WHERE s.id = i.stack_id)
        """
    )
    empty_stacks = conn.query_one(
        """
        SELECT COUNT(*) AS c FROM stacks s
        WHERE NOT EXISTS (SELECT 1 FROM images i WHERE i.stack_id = s.id)
        """
    )

    sample_singletons = conn.query(
        """
        SELECT stack_id, COUNT(*) AS cnt FROM images
        WHERE stack_id IS NOT NULL
        GROUP BY stack_id
        HAVING COUNT(*) = 1
        ORDER BY stack_id
        FETCH FIRST ? ROWS ONLY
        """,
        (lim,),
    )
    sample_orphans = conn.query(
        """
        SELECT i.id AS image_id, i.stack_id, i.file_path FROM images i
        WHERE i.stack_id IS NOT NULL
        AND NOT EXISTS (SELECT 1 FROM stacks s WHERE s.id = i.stack_id)
        ORDER BY i.id
        FETCH FIRST ? ROWS ONLY
        """,
        (lim,),
    )

    return {
        "singleton_stack_count": int((singleton or {}).get("c") or 0),
        "images_orphan_stack_id_count": int((orphan_img or {}).get("c") or 0),
        "empty_stacks_count": int((empty_stacks or {}).get("c") or 0),
        "sample_singleton_stack_ids": [r.get("stack_id") for r in (sample_singletons or [])],
        "sample_orphan_stack_images": ts.sanitize_for_mcp(sample_orphans or []),
    }


def verify_environment() -> dict:
    """Comprehensive environment check: GPU, DB, Python, and system stats."""
    import platform
    import sys

    import psutil
    import torch

    from modules import mcp_server as _ms
    from modules.mcp_server import prepare_mcp_embedded

    # Try to refresh DB status if it's currently marked as unavailable
    if not _ms._db_available:
        prepare_mcp_embedded()

    status = {
        "os": platform.system(),
        "python_version": sys.version,
        "gpu": {
            "available": torch.cuda.is_available(),
            "count": torch.cuda.device_count(),
            "names": [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())] if torch.cuda.is_available() else []
        },
        "memory": {
            "total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
            "available_gb": round(psutil.virtual_memory().available / (1024**3), 2)
        },
        "database": {
            "engine": db._get_db_engine(),
            "available": _ms._db_available
        }
    }
    return status


def get_system_resources() -> dict:
    """CPU and RAM snapshot plus optional ``nvidia-smi`` GPU rows. Does not require database access."""
    out: dict[str, Any] = {"cpu_percent": None, "memory": {}, "gpu": {}}
    try:
        import psutil

        out["cpu_percent"] = round(psutil.cpu_percent(interval=0.1), 2)
        vm = psutil.virtual_memory()
        out["memory"] = {
            "total_gb": round(vm.total / (1024**3), 2),
            "available_gb": round(vm.available / (1024**3), 2),
            "percent_used": vm.percent,
        }
    except Exception as e:
        out["memory_error"] = str(e)

    try:
        import subprocess

        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.used,memory.total,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        gpus: list[dict[str, str]] = []
        if proc.returncode == 0 and proc.stdout.strip():
            for line in proc.stdout.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 4:
                    gpus.append(
                        {
                            "name": parts[0],
                            "memory_used_mb": parts[1],
                            "memory_total_mb": parts[2],
                            "utilization_gpu_pct": parts[3],
                        }
                    )
        out["gpu"]["nvidia_smi"] = gpus
    except Exception as e:
        out["gpu"]["error"] = str(e)

    return out


def get_thread_dump() -> dict:
    """Capture a full Python thread dump for backend diagnostic and stall debugging."""
    try:
        from modules.pipeline_diagnostics import get_thread_dump as _get_thread_dump
        return {"success": True, "thread_dump": _get_thread_dump()}
    except Exception as e:
        return {"error": str(e)}

