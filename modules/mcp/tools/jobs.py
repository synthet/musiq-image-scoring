"""MCP tool implementations — jobs (extracted from modules.mcp_server)."""

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

def get_recent_jobs(limit: int = 10) -> list:
    """Get recent scoring/tagging jobs with their status."""
    rows = db.get_jobs(limit=limit)
    return [dict(row) for row in rows]


def get_job_details(job_id: int) -> dict:
    """Get one job/run by id (jobs.id): status, paths, timestamps, queue_payload summary, log tail. Same id as workflow run_id in the API."""
    row = db.get_job(int(job_id))
    if not row:
        return {"error": "Job not found", "job_id": int(job_id)}
    return ts.normalize_job_payload_for_mcp(row)


def get_job_phases(job_id: int) -> dict:
    """List phase rows (order, code, state, timestamps, errors) for a job/run id."""
    jid = int(job_id)
    phases = db.get_job_phases(jid)
    return {"job_id": jid, "count": len(phases), "phases": ts.sanitize_for_mcp(phases)}


def get_job_stage_images(
    job_id: int,
    phase_code: str,
    limit: int = 50,
    offset: int = 0,
    include_steps: bool = False,
) -> dict:
    """Paginate per-image phase status for a job+phase (image_phase_status). Optional include_steps adds job_steps telemetry for that phase."""
    jid = int(job_id)
    lim = max(1, min(int(limit), 500))
    off = max(0, int(offset))
    data = db.get_job_stage_images(jid, phase_code, offset=off, limit=lim)
    out = {
        "job_id": jid,
        "phase_code": phase_code,
        "offset": off,
        "limit": lim,
        "total": data.get("total", 0),
        "items": data.get("items", []),
    }
    if include_steps:
        out["steps"] = db.get_job_steps(jid, phase_code)
    return ts.sanitize_for_mcp(out)


def get_run_diagnostics(run_id: int) -> dict:
    """Post-run audit snapshot from queue_payload plus per-phase image_phase_status counts for this job/run id."""
    jid = int(run_id)
    data = db.get_run_diagnostics(jid)
    return ts.sanitize_for_mcp(data)


def get_drive_diagnostics() -> dict:
    """Auto-drive loop status, folder health, recent auto-drive jobs, and anomaly hints.

    Use when Driving mode stalls, re-queues folders, or stops unexpectedly.
    Complements ``get_recent_jobs`` and ``get_run_diagnostics`` for triage.
    """
    from modules import runs_autodrive

    return ts.sanitize_for_mcp(runs_autodrive.get_drive_diagnostics())


def get_job_execution_report(run_id: int, phase_code: Optional[str] = None, action: Optional[str] = None, offset: int = 0, limit: int = 20) -> dict:
    """Structured execution report for a job: what the run did to each image.

    Returns report_json summary (per-phase stats, before/after aggregates) and
    paginated per-image action log with before/after score snapshots.
    Filter with phase_code (scoring, metadata, indexing) and action (processed, skipped, failed).
    """
    jid = int(run_id)
    report = db.get_job_report(jid)
    actions = db.get_job_image_actions(jid, phase_code, action, offset, limit)
    summary: dict[str, Any] = {"action_counts": {}}
    try:
        conn = db.get_connector()
        act_rows = conn.query(
            """
            SELECT LOWER(TRIM(COALESCE(action, ''))) AS act, COUNT(*) AS c
            FROM job_image_actions
            WHERE job_id = ?
            GROUP BY LOWER(TRIM(COALESCE(action, '')))
            """,
            (jid,),
        )
        for r in act_rows or []:
            act = (r.get("act") or "").strip() or "unknown"
            summary["action_counts"][act] = int(r.get("c") or 0)
    except Exception as e:
        summary["error"] = str(e)

    return ts.sanitize_for_mcp({
        "job_id": jid,
        "report": report,
        "image_actions": actions,
        "summary": summary,
    })


def get_image_pipeline_failures(
    image_id: Optional[int] = None,
    file_path: Optional[str] = None,
    limit: int = 50,
) -> dict:
    """Recent ``job_image_actions`` rows with action ``failed`` for one image (by ``image_id`` or ``file_path``).

    Joins ``jobs`` for terminal status and log snippet. Use after locating an image via ``query_images`` / ``get_image_details``.
    """
    if not image_id and not (file_path and str(file_path).strip()):
        return {"error": "Provide image_id or file_path", "items": []}

    conn = db.get_connector()
    iid: int | None = int(image_id) if image_id is not None else None
    if iid is None and file_path:
        fp = os.path.normpath(str(file_path).strip())
        row = conn.query_one("SELECT id FROM images WHERE file_path = ?", (fp,))
        if not row:
            return {"error": "image_not_found", "file_path": fp, "items": []}
        iid = int(row["id"])

    lim = max(1, min(int(limit), 200))
    try:
        rows = conn.query(
            """
            SELECT jia.id, jia.job_id, jia.phase_code, jia.action, jia.reason,
                   jia.before_snapshot, jia.after_snapshot, jia.created_at,
                   j.status AS job_status, j.log AS job_log
            FROM job_image_actions jia
            LEFT JOIN jobs j ON j.id = jia.job_id
            WHERE jia.image_id = ?
              AND LOWER(TRIM(jia.action)) = 'failed'
            ORDER BY jia.created_at DESC NULLS LAST, jia.id DESC
            FETCH FIRST ? ROWS ONLY
            """,
            (iid, lim),
        )
    except Exception as e:
        return {"error": str(e), "image_id": iid, "items": []}

    items = []
    for r in rows or []:
        d = dict(r)
        for k in ("before_snapshot", "after_snapshot", "job_log"):
            v = d.get(k)
            if isinstance(v, str) and len(v) > 2000:
                d[k] = v[:2000] + "…"
        items.append(ts.sanitize_for_mcp(d))

    return {"image_id": iid, "items": items}


def get_location_stats() -> dict:
    """Summarize GPS and geocode coverage in ``image_exif`` (PostgreSQL; requires migration 0013 columns)."""
    if config.get_database_engine() != "postgres":
        return {"error": "get_location_stats is supported on PostgreSQL only.", "database_engine": config.get_database_engine()}
    conn = db.get_connector()
    try:
        row = conn.query_one(
            """
            SELECT
                COUNT(*) AS total_rows,
                COUNT(*) FILTER (WHERE gps_latitude IS NOT NULL AND gps_longitude IS NOT NULL) AS with_gps,
                COUNT(*) FILTER (WHERE geocoded_at IS NOT NULL) AS geocoded,
                COUNT(*) FILTER (
                    WHERE gps_latitude IS NOT NULL AND gps_longitude IS NOT NULL AND geocoded_at IS NULL
                ) AS gps_not_geocoded
            FROM image_exif
            """,
            (),
        )
    except Exception as e:
        return {"error": str(e), "note": "Ensure image_exif GPS/geocode columns exist (Alembic 0013)."}

    return ts.sanitize_for_mcp(dict(row) if row else {})


def get_embedding_stats(
    folder_path: Optional[str] = None,
    embedding_space: Optional[str] = None,
) -> dict:
    """Counts of images with vs without a stored image embedding.

    By default reports coverage for the MobileNetV2 default space and a
    per-space breakdown of every row in ``embedding_spaces``. Pass
    ``embedding_space`` to get coverage counts for that specific space. Optional
    ``folder_path`` filters by exact ``folders.path`` match.
    """
    try:
        from modules.similar_search import EMBEDDING_DIM
        expected_dim = EMBEDDING_DIM
    except Exception:
        expected_dim = None

    conn = db.get_connector()
    folder_id = None
    if folder_path and str(folder_path).strip():
        norm = os.path.normpath(str(folder_path).strip())
        frow = conn.query_one("SELECT id FROM folders WHERE path = ?", (norm,))
        if not frow:
            return {"error": "folder_not_found", "folder_path": norm}
        folder_id = frow["id"]

    def _per_space_counts(is_postgres: bool) -> list[dict]:
        if not is_postgres:
            return []
        try:
            rows = db_postgres.execute_select(
                "SELECT id, code, dim FROM embedding_spaces WHERE COALESCE(active, 1) = 1 ORDER BY id"
            )
        except Exception:
            return []
        per_space: list[dict] = []
        for r in rows:
            dim = int(r.get("dim") or 0)
            try:
                table = db._pg_embedding_table_for_dim(dim)
            except ValueError:
                per_space.append({
                    "code": r.get("code"),
                    "dim": dim,
                    "error": "no fact table for dim",
                })
                continue
            params: list = [int(r.get("id"))]
            folder_clause = ""
            if folder_id is not None:
                folder_clause = (
                    " AND EXISTS ("
                    "  SELECT 1 FROM images i WHERE i.id = e.image_id AND i.folder_id = %s"
                    " )"
                )
                params.append(folder_id)
            try:
                row = db_postgres.execute_select_one(
                    f"SELECT COUNT(*) AS c FROM {table} e WHERE e.embedding_space_id = %s{folder_clause}",
                    tuple(params),
                )
                count = int((row or {}).get("c") or 0)
            except Exception as exc:  # noqa: BLE001
                per_space.append({
                    "code": r.get("code"),
                    "dim": dim,
                    "error": f"count failed: {exc}",
                })
                continue
            per_space.append({
                "code": r.get("code"),
                "dim": dim,
                "table": table,
                "count": count,
            })
        return per_space

    is_postgres = conn.type == 'postgres'

    # Per-space lookup for a specific embedding_space argument.
    if embedding_space:
        if not is_postgres:
            return {
                "error": "embedding_space queries require PostgreSQL (pgvector).",
                "embedding_space": embedding_space,
            }
        try:
            from modules.embedding_spaces import SPACE_DIMS, get_embedding_space_id

            dim = SPACE_DIMS.get(embedding_space)
            if dim is None:
                row = db_postgres.execute_select_one(
                    "SELECT dim FROM embedding_spaces WHERE code = %s",
                    (embedding_space,),
                )
                if not row:
                    return {"error": "unknown embedding_space", "embedding_space": embedding_space}
                dim = int(row["dim"])
            table = db._pg_embedding_table_for_dim(int(dim))
            space_id = get_embedding_space_id(embedding_space)
            if space_id is None:
                return {"error": "embedding_space not registered", "embedding_space": embedding_space}
        except ValueError as exc:
            return {"error": str(exc), "embedding_space": embedding_space}

        params_total: list = []
        total_clause = ""
        if folder_id is not None:
            total_clause = " WHERE folder_id = %s"
            params_total.append(folder_id)
        total_row = db_postgres.execute_select_one(
            f"SELECT COUNT(*) AS c FROM images{total_clause}",
            tuple(params_total) if params_total else None,
        )
        params_with: list = [space_id]
        with_clause = " WHERE e.embedding_space_id = %s"
        if folder_id is not None:
            with_clause += " AND EXISTS (SELECT 1 FROM images i WHERE i.id = e.image_id AND i.folder_id = %s)"
            params_with.append(folder_id)
        with_row = db_postgres.execute_select_one(
            f"SELECT COUNT(*) AS c FROM {table} e{with_clause}",
            tuple(params_with),
        )
        total = int((total_row or {}).get("c") or 0)
        with_emb = int((with_row or {}).get("c") or 0)
        return {
            "folder_path": os.path.normpath(folder_path) if folder_path and str(folder_path).strip() else None,
            "embedding_space": embedding_space,
            "embedding_dim": int(dim),
            "table": table,
            "total_images": total,
            "with_embedding": with_emb,
            "missing_embedding": max(0, total - with_emb),
        }

    # Default: MobileNet coverage + per-space summary.
    if is_postgres:
        sub = db._pg_default_embedding_space_subquery_sql()
        has_e = db._postgres_has_default_embedding_sql("i")
        if folder_id is not None:
            base = "i.folder_id = ?"
            params_t = (folder_id,)
            total_row = conn.query_one(
                f"SELECT COUNT(*) AS c FROM images i WHERE {base}",
                params_t
            )
            with_row = conn.query_one(
                f"""SELECT COUNT(*) AS c FROM images i
                   LEFT JOIN image_embeddings ie ON ie.image_id = i.id AND ie.embedding_space_id = {sub}
                   WHERE {base} AND {has_e}""",
                params_t,
            )
        else:
            total_row = conn.query_one("SELECT COUNT(*) AS c FROM images i", ())
            with_row = conn.query_one(
                f"""SELECT COUNT(*) AS c FROM images i
                   LEFT JOIN image_embeddings ie ON ie.image_id = i.id AND ie.embedding_space_id = {sub}
                   WHERE {has_e}""",
                (),
            )
    else:
        if folder_id is not None:
            base = "folder_id = ?"
            params_t = (folder_id,)
            total_row = conn.query_one(f"SELECT COUNT(*) AS c FROM images WHERE {base}", params_t)
            with_row = conn.query_one(
                f"SELECT COUNT(*) AS c FROM images WHERE {base} AND image_embedding IS NOT NULL",
                params_t,
            )
        else:
            total_row = conn.query_one("SELECT COUNT(*) AS c FROM images", ())
            with_row = conn.query_one(
                "SELECT COUNT(*) AS c FROM images WHERE image_embedding IS NOT NULL",
                (),
            )

    total = int((total_row or {}).get("c") or 0)
    with_emb = int((with_row or {}).get("c") or 0)
    missing = max(0, total - with_emb)
    legacy_column_rows = None
    if is_postgres and db._postgres_images_has_image_embedding_column():
        leg_row = conn.query_one(
            "SELECT COUNT(*) AS c FROM images WHERE image_embedding IS NOT NULL",
            (),
        )
        legacy_column_rows = int((leg_row or {}).get("c") or 0)
    return {
        "folder_path": os.path.normpath(folder_path) if folder_path and str(folder_path).strip() else None,
        "total_images": total,
        "with_embedding": with_emb,
        "missing_embedding": missing,
        "expected_embedding_dim": expected_dim,
        "per_space": _per_space_counts(is_postgres),
        "legacy_column_rows": legacy_column_rows,
    }


    from modules import mcp_server as _ms
def get_runner_status() -> dict:
    """Get current status of scoring and tagging background runners including progress and recent logs."""
    status = {
        "scoring": {"available": False},
        "tagging": {"available": False},
        "clustering": {"available": False},
        "selection": {"available": False},
        "indexing": {"available": False},
        "metadata": {"available": False}
    }

    if _ms._scoring_runner:
        try:
            result = _scoring_runner.get_status()
            is_running, log, status_msg, current, total = result[:5]
            status["scoring"] = {
                "available": True,
                "is_running": is_running,
                "status_message": status_msg,
                "progress": {"current": current, "total": total},
                "recent_log": log[-2000:] if log else ""
            }
        except Exception as e:
            status["scoring"]["error"] = str(e)

    if _ms._tagging_runner:
        try:
            result = _tagging_runner.get_status()
            is_running, log, status_msg, current, total = result[:5]
            status["tagging"] = {
                "available": True,
                "is_running": is_running,
                "status_message": status_msg,
                "progress": {"current": current, "total": total},
                "recent_log": log[-2000:] if log else ""
            }
        except Exception as e:
            status["tagging"]["error"] = str(e)

    if _ms._clustering_runner:
        try:
            result = _clustering_runner.get_status()
            is_running, log, status_msg, current, total = result[:5]
            status["clustering"] = {
                "available": True,
                "is_running": is_running,
                "status_message": status_msg,
                "progress": {"current": current, "total": total},
                "recent_log": log[-2000:] if log else ""
            }
        except Exception as e:
            status["clustering"]["error"] = str(e)

    if _ms._selection_runner:
        try:
            result = _selection_runner.get_status()
            is_running, log, status_msg, current, total = result[:5]
            status["selection"] = {
                "available": True,
                "is_running": is_running,
                "status_message": status_msg,
                "progress": {"current": current, "total": total},
                "recent_log": log[-2000:] if log else ""
            }
        except Exception as e:
            status["selection"]["error"] = str(e)

    if _ms._indexing_runner:
        try:
            result = _indexing_runner.get_status()
            is_running, log, status_msg, current, total = result[:5]
            status["indexing"] = {
                "available": True,
                "is_running": is_running,
                "status_message": status_msg,
                "progress": {"current": current, "total": total},
                "recent_log": log[-2000:] if log else ""
            }
        except Exception as e:
            status["indexing"]["error"] = str(e)

    if _ms._metadata_runner:
        try:
            result = _metadata_runner.get_status()
            is_running, log, status_msg, current, total = result[:5]
            status["metadata"] = {
                "available": True,
                "is_running": is_running,
                "status_message": status_msg,
                "progress": {"current": current, "total": total},
                "recent_log": log[-2000:] if log else ""
            }
        except Exception as e:
            status["metadata"]["error"] = str(e)

    if _ms._maintenance_runner:
        try:
            if hasattr(_ms._maintenance_runner, "get_status"):
                result = _maintenance_runner.get_status()
                is_running, log, status_msg, current, total = result[:5]
                status["maintenance"] = {
                    "available": True,
                    "is_running": is_running,
                    "status_message": status_msg,
                    "progress": {"current": current, "total": total},
                    "recent_log": log[-2000:] if log else "",
                }
            else:
                running = bool(getattr(_ms._maintenance_runner, "is_running", False))
                status["maintenance"] = {
                    "available": True,
                    "is_running": running,
                    "status_message": "Running maintenance job" if running else "Idle",
                    "progress": {"current": 0, "total": 0},
                    "recent_log": "",
                }
        except Exception as e:
            status["maintenance"] = {"available": True, "error": str(e)}
    else:
        status["maintenance"] = {"available": False}

    if _ms._bird_species_runner:
        try:
            result = _bird_species_runner.get_status()
            is_running, log, status_msg, current, total = result[:5]
            status["bird_species"] = {
                "available": True,
                "is_running": is_running,
                "status_message": status_msg,
                "progress": {"current": current, "total": total},
                "recent_log": log[-2000:] if log else ""
            }
        except Exception as e:
            status["bird_species"] = {"available": True, "error": str(e)}
    else:
        status["bird_species"] = {"available": False}

    return status


def get_pipeline_stats() -> dict:
    """Get statistics about the processing pipeline and active jobs. Runner status, queue sizes, dispatcher state, and active job info."""
    result = {
        "runners": get_runner_status(),
        "dispatcher": {"dispatcher_available": False},
        "queue_config": {}
    }

    # Dispatcher state (only when WebUI is running and api module has job_dispatcher)
    try:
        from modules import api
        dispatcher = getattr(api, "_job_dispatcher", None)
        if dispatcher is not None:
            state = dispatcher.get_state()
            result["dispatcher"] = {
                "dispatcher_available": True,
                "is_dispatcher_running": state.get("is_dispatcher_running", False),
                "active_runner": state.get("active_runner"),
                "queue_size": state.get("queue_size", 0),
                "queue": state.get("queue", [])
            }
    except ImportError:
        pass
    except Exception as e:
        result["dispatcher"]["error"] = str(e)

    # Queue config from config.json
    try:
        proc = config.get_config_section("processing") or {}
        result["queue_config"] = {
            "prep_queue_size": proc.get("prep_queue_size"),
            "scoring_queue_size": proc.get("scoring_queue_size"),
            "result_queue_size": proc.get("result_queue_size"),
            "clustering_batch_size": proc.get("clustering_batch_size"),
        }
    except Exception:
        pass

    return result


def get_performance_metrics(days: int = 7) -> dict:
    """Get performance metrics from recent jobs: avg job duration, jobs completed/failed, success rate, jobs by status."""
    import datetime
    result = {
        "avg_job_duration_seconds": None,
        "jobs_completed_7d": 0,
        "jobs_failed_7d": 0,
        "jobs_cancelled_7d": 0,
        "jobs_interrupted_7d": 0,
        "success_rate": None,
        "jobs_by_status": {},
        "total_jobs_7d": 0,
        "images_processed_7d": None,
    }
    try:
        cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
        with db.connection() as conn:
            c = conn.cursor()
            c.execute(
                """
                SELECT status, started_at, finished_at, completed_at
                FROM jobs
                WHERE created_at >= ?
                """,
                (cutoff,),
            )
            rows = c.fetchall()

        jobs_by_status = {}
        durations = []
        for row in rows:
            status = (row[0] or "unknown").strip().lower()
            jobs_by_status[status] = jobs_by_status.get(status, 0) + 1
            started = row[1]
            finished = row[2] or row[3]
            if started and finished:
                try:
                    delta = (finished - started).total_seconds()
                    if delta >= 0:
                        durations.append(delta)
                except (TypeError, AttributeError):
                    pass

        result["jobs_by_status"] = jobs_by_status
        result["total_jobs_7d"] = len(rows)
        result["jobs_completed_7d"] = jobs_by_status.get("completed", 0)
        result["jobs_failed_7d"] = jobs_by_status.get("failed", 0)
        result["jobs_cancelled_7d"] = jobs_by_status.get("cancelled", 0) + jobs_by_status.get("canceled", 0)
        result["jobs_interrupted_7d"] = jobs_by_status.get("interrupted", 0)

        if durations:
            result["avg_job_duration_seconds"] = round(sum(durations) / len(durations), 1)

        terminal = result["jobs_completed_7d"] + result["jobs_failed_7d"] + result["jobs_cancelled_7d"] + result["jobs_interrupted_7d"]
        if terminal > 0:
            result["success_rate"] = round(100.0 * result["jobs_completed_7d"] / terminal, 1)

        result["period_days"] = days
    except Exception as e:
        result["error"] = str(e)
    return result


    from modules import mcp_server as _ms
def run_processing_job(job_type: str, input_path: str, args: dict = None) -> dict:
    """Trigger a background processing job (scoring, tagging, clustering/stacks, or bird_species).

    Creates a ``jobs`` row and returns integer ``job_id`` / ``jobs_id`` (same value) for use with
    ``get_job_details``, ``get_run_diagnostics``, and ``get_job_execution_report``.
    """
    if args is None:
        args = {}

    if not os.path.exists(input_path) and not (job_type == "clustering" and (not input_path or not input_path.strip())):
        return {"error": f"Input path not found: {input_path}"}

    from modules.run_manifest import REASON_SOURCE_MCP, attach_run_reason, build_legacy_api_summary

    def _mcp_queue_payload(job_kind: str, path: str, extra: Optional[dict] = None) -> dict:
        base = dict(extra or {})
        if path:
            base.setdefault("input_path", path)
        return attach_run_reason(
            base,
            source=REASON_SOURCE_MCP,
            summary=build_legacy_api_summary(
                job_kind=job_kind,
                input_path=path,
                extra="Triggered via MCP run_processing_job.",
            ),
            trigger="mcp",
            tool_id="run_processing_job",
        )

    def _ok_payload(res: str, jid: int) -> dict:
        return {"status": res, "job_id": jid, "jobs_id": jid}

    if job_type == "scoring":
        if not _ms._scoring_runner:
            return {"error": "Scoring runner not available"}
        if _scoring_runner.is_running:
            return {"error": "Scoring job already running"}
        jid = db.create_job(
            input_path,
            phase_code="scoring",
            queue_payload=_mcp_queue_payload("scoring", input_path),
        )
        db.create_job_phases(jid, ["scoring"])
        res = _scoring_runner.start_batch(
            input_path,
            jid,
            skip_existing=not args.get("rescore", False),
        )
        return _ok_payload(res, jid)

    if job_type == "tagging":
        if not _ms._tagging_runner:
            return {"error": "Tagging runner not available"}
        if _tagging_runner.is_running:
            return {"error": "Tagging job already running"}
        jid = db.create_job(
            input_path,
            phase_code="keywords",
            queue_payload=_mcp_queue_payload("tagging", input_path),
        )
        db.create_job_phases(jid, ["keywords"])
        custom_keywords = args.get("custom_keywords")
        generate_captions = config.get_config_section("tagging").get("captions_default", True)
        res = _tagging_runner.start_batch(
            input_path,
            jid,
            custom_keywords=custom_keywords,
            overwrite=args.get("overwrite", False),
            generate_captions=generate_captions,
        )
        return _ok_payload(res, jid)

    if job_type == "clustering":
        culling_runner = _ms._selection_runner or _ms._clustering_runner
        if not culling_runner:
            return {"error": "Clustering/selection runner not available (not initialized)"}
        if culling_runner.is_running:
            return {"error": "Clustering job already running"}
        cluster_path = input_path.strip() if input_path and input_path.strip() else None
        store_path = cluster_path or "CLUSTERING"
        jid = db.create_job(
            store_path,
            phase_code="culling",
            queue_payload=_mcp_queue_payload("clustering", cluster_path or store_path),
        )
        db.create_job_phases(jid, ["culling"])
        if _ms._selection_runner and culling_runner is _ms._selection_runner:
            res = _selection_runner.start_batch(
                input_path or "",
                job_id=jid,
                force_rescan=args.get("force_rescan", False),
            )
        else:
            res = _clustering_runner.start_batch(
                cluster_path,
                threshold=args.get("threshold"),
                time_gap=args.get("time_gap"),
                force_rescan=args.get("force_rescan", False),
                job_id=jid,
            )
        return _ok_payload(res, jid)

    if job_type == "bird_species":
        if not _ms._bird_species_runner:
            return {"error": "Bird species runner not available"}
        if _bird_species_runner.is_running:
            return {"error": "Bird species job already running"}
        jid = db.create_job(
            input_path or "BIRD_SPECIES",
            phase_code="bird_species",
            queue_payload=_mcp_queue_payload("bird species", input_path or "BIRD_SPECIES"),
        )
        db.create_job_phases(jid, ["bird_species"])
        res = _bird_species_runner.start_batch(
            input_path,
            job_id=jid,
            threshold=args.get("threshold", 0.1),
            top_k=args.get("top_k", 1),
            overwrite=args.get("overwrite", False),
            candidate_species=args.get("candidate_species"),
        )
        return _ok_payload(res, jid)

    return {"error": f"Unknown job type: {job_type}"}


    from modules import mcp_server as _ms
def manage_runners(runner: str, operation: str) -> dict:
    """Request ``stop`` or read ``status`` for an in-process background runner (WebUI / SSE context). Starting jobs is not supported here — use ``run_processing_job`` or the UI."""
    r = (runner or "").strip().lower()
    op = (operation or "").strip().lower()
    if op == "start":
        return {
            "success": False,
            "error": "Starting jobs is not supported via manage_runners; use run_processing_job or the Web UI.",
        }
    if op not in ("stop", "status"):
        return {"success": False, "error": "operation must be 'stop' or 'status' (or 'start', which is rejected)."}

    mapping: dict[str, Any] = {
        "scoring": _ms._scoring_runner,
        "tagging": _ms._tagging_runner,
        "clustering": _ms._clustering_runner,
        "selection": _ms._selection_runner,
        "indexing": _ms._indexing_runner,
        "metadata": _ms._metadata_runner,
        "bird_species": _ms._bird_species_runner,
        "maintenance": _ms._maintenance_runner,
    }
    if r not in mapping:
        return {"success": False, "error": f"Unknown runner '{runner}'.", "known": sorted(mapping.keys())}

    obj = mapping[r]
    if obj is None:
        return {"success": False, "error": f"Runner '{r}' is not wired in this process."}

    if op == "status":
        is_running = bool(getattr(obj, "is_running", False))
        msg = str(getattr(obj, "status_message", "") or "")[:500]
        return {"success": True, "runner": r, "is_running": is_running, "status_message": msg}

    stop_fn = getattr(obj, "stop", None)
    if not callable(stop_fn):
        return {"success": False, "error": f"Runner '{r}' has no stop() method."}
    try:
        stop_fn()
        return {"success": True, "runner": r, "message": "stop() invoked"}
    except Exception as e:
        return {"success": False, "runner": r, "error": str(e)}

