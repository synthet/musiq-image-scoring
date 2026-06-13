"""
api_db.py — Database API router for microservices architecture.

Provides REST endpoints for database operations, allowing remote scoring
and pipeline components to interact with the database.

Generic SQL endpoints (used by ApiConnector in modules/db_connector/api.py):
    GET  /api/db/ping              — connectivity probe
    POST /api/db/query             — execute read or write SQL
    POST /api/db/transaction       — execute a batch of write statements atomically
"""

from fastapi import APIRouter, HTTPException, Query, Body, Path, Response, Header
from typing import List, Dict, Any, Optional, Tuple
import logging
import json

from modules import db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/db", tags=["database"])


# =========================================================================
# Generic SQL bridge  (used by ApiConnector)
# =========================================================================

@router.get("/ping")
def ping():
    """Connectivity probe. Returns the active DB engine name."""
    return {"ok": True, "engine": db._get_db_engine()}


@router.post("/query")
def raw_query(
    payload: Dict[str, Any] = Body(...),
    x_db_write_token: Optional[str] = Header(None, alias="X-DB-Write-Token"),
):
    """Execute a SQL statement and return results.

    Body fields:
        sql         — SQL string with ``?`` (Firebird) placeholders
        params      — list of bound values (default [])
        write       — if true, treat as a mutating statement (default false)
        executemany — if true, ``params`` is a list-of-lists for batch execution

    Read queries require no authentication.
    Write queries require the ``X-DB-Write-Token`` header to match
    ``config.database.query_token``; if the token is empty/unset, writes
    are blocked.
    """
    sql = (payload.get("sql") or "").strip()
    params = payload.get("params") or []
    is_write = bool(payload.get("write", False))
    is_executemany = bool(payload.get("executemany", False))

    if not sql:
        raise HTTPException(status_code=400, detail="Missing 'sql' in request body")

    try:
        from modules import config as _cfg
    except Exception:
        _cfg = None

    if _cfg is not None and not _cfg.get_config_value("database.enable_api_db_query", True):
        raise HTTPException(
            status_code=403,
            detail="POST /api/db/query is disabled (database.enable_api_db_query)",
        )

    if is_write:
        # Verify write token
        token = ""
        if _cfg is not None:
            token = str(
                (_cfg.get_config_section("database") or {}).get("query_token", "") or ""
            ).strip()
        if not token:
            raise HTTPException(
                status_code=403,
                detail="Write queries are disabled: set database.query_token in config.json",
            )
        if x_db_write_token != token:
            raise HTTPException(status_code=403, detail="Invalid X-DB-Write-Token")

        try:
            if is_executemany:
                from modules.db_connector import get_connector
                get_connector().execute_many(sql, [list(p) for p in params])
                return {"rows": [], "rowcount": len(params)}

            rows = db.execute_write_sql_for_api(sql, params if params else None)
            return {"rows": rows, "data": rows, "rowcount": len(rows)}
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error("raw_query write error: %s", e)
            raise HTTPException(status_code=500, detail=str(e))

    # Read query
    max_rows = 5000
    if _cfg is not None:
        max_rows = int(_cfg.get_config_value("database.api_db_query_max_rows", 5000))
    try:
        rows = db.execute_readonly_sql_for_api(
            sql, params if params else None, max_rows=max_rows
        )
        return {"rows": rows, "data": rows, "rowcount": len(rows)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("raw_query read error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/transaction")
def raw_transaction(
    payload: Dict[str, Any] = Body(...),
    x_db_write_token: Optional[str] = Header(None, alias="X-DB-Write-Token"),
):
    """Execute a batch of write statements atomically.

    Body fields:
        statements  — list of {"sql": str, "params": list} objects

    All statements are executed inside a single transaction; the whole batch
    commits or rolls back together.  Requires ``X-DB-Write-Token``.
    """
    # Verify write token (same logic as /query)
    try:
        from modules import config as _cfg
        token = str(
            (_cfg.get_config_section("database") or {}).get("query_token", "") or ""
        ).strip()
    except Exception:
        token = ""
    if not token:
        raise HTTPException(
            status_code=403,
            detail="Transactions are disabled: set database.query_token in config.json",
        )
    if x_db_write_token != token:
        raise HTTPException(status_code=403, detail="Invalid X-DB-Write-Token")

    statements = payload.get("statements") or []
    if not statements:
        raise HTTPException(status_code=400, detail="Missing 'statements' in request body")

    def _tx(tx):
        for stmt in statements:
            sql = (stmt.get("sql") or "").strip()
            params = stmt.get("params") or []
            if not sql:
                continue
            err = db.validate_write_sql_for_api(sql)
            if err:
                raise ValueError(f"Statement rejected: {err}")
            if stmt.get("returning"):
                tx.execute_returning(sql, params)
            else:
                tx.execute(sql, params)

    try:
        from modules.db_connector import get_connector
        get_connector().run_transaction(_tx)
        return {"ok": True, "count": len(statements)}
    except Exception as e:
        logger.error("raw_transaction error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

# =========================================================================
# Image CRUD
# =========================================================================

@router.get("/images/by-path")
def get_image_details(file_path: str = Query(..., description="Full path to the image file")):
    details = db.get_image_details(file_path)
    if not details:
        raise HTTPException(status_code=404, detail="Image not found")
    return details

@router.get("/images/by-hash/{image_hash}")
def get_image_by_hash(
    image_hash: str = Path(..., description="Image content hash"),
    hash_version: Optional[int] = Query(None, description="images.hash_version"),
):
    details = db.get_image_by_hash(image_hash, hash_version=hash_version)
    if not details:
        raise HTTPException(status_code=404, detail="Image not found")
    return details

@router.post("/images/upsert")
def upsert_image(payload: Dict[str, Any] = Body(...)):
    job_id = payload.get("job_id")
    result = payload.get("result")
    if job_id is None or result is None:
        raise HTTPException(status_code=400, detail="Missing job_id or result")
    invalidate_agg = payload.get("invalidate_agg", True)
    db.upsert_image(job_id, result, invalidate_agg=bool(invalidate_agg))
    return {"success": True}

@router.delete("/images/by-path")
def delete_image(file_path: str = Query(..., description="Full path to the image file")):
    db.delete_image(file_path)
    return {"success": True}

@router.get("/images")
def get_images(
    limit: int = Query(-1),
    folder_path: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None)
):
    if keyword:
        rows = db.get_images_with_keyword(folder_path=folder_path, keyword=keyword)
        return rows[:limit] if limit and limit > 0 else rows
    if folder_path:
        return db.get_images_by_folder(folder_path)
    return db.get_all_images(limit=limit)

@router.get("/images/incomplete")
def get_incomplete_records():
    return db.get_incomplete_records()

@router.patch("/images/{image_id}")
def update_image_fields(image_id: int, updates: Dict[str, Any] = Body(...)):
    success = True
    for field, value in updates.items():
        if not db.update_image_field(image_id, field, value):
            success = False
    return {"success": success}

@router.post("/images/batch-update")
def update_image_fields_batch(payload: Dict[str, Any] = Body(...)):
    updates_raw = payload.get("updates", [])
    # Convert list of dicts to list of tuples
    updates = [(u["image_id"], u["fields"]) for u in updates_raw]
    db.update_image_fields_batch(updates)
    return {"success": True}

@router.post("/images/batch-embeddings")
def update_embeddings_batch(payload: List[Dict[str, Any]] = Body(...)):
    # payload: list of {"image_id": int, "embedding": list[float]}
    import numpy as np
    updates = [
        (item["image_id"], np.asarray(item["embedding"], dtype=np.float32).tobytes())
        for item in payload
    ]
    db.update_image_embeddings_batch(updates)
    return {"success": True}

@router.get("/images/{image_id}/paths")
def get_all_paths(image_id: int):
    return db.get_all_paths(image_id)

@router.get("/images/{image_id}/resolved-path")
def get_resolved_path(image_id: int, verified_only: bool = Query(False)):
    path = db.get_resolved_path(image_id, verified_only=verified_only)
    return {"path": path}

@router.get("/images/{image_id}/phases")
def get_image_phases(image_id: int):
    return db.get_image_phase_statuses(image_id)

# =========================================================================
# Job management
# =========================================================================

@router.get("/jobs")
def get_jobs(limit: int = Query(100)):
    return db.get_recent_jobs(limit=limit)

@router.post("/jobs")
def create_job(payload: Dict[str, Any] = Body(...)):
    input_path = payload.pop("input_path", "")
    job_type = payload.pop("job_type", "scoring")
    status = payload.pop("status", "queued")
    runner_state = payload.pop("runner_state", None)
    job_id = db.create_job(input_path, job_type=job_type, status=status, runner_state=runner_state, **payload)
    return {"job_id": job_id}

@router.patch("/jobs/{job_id}")
def update_job_status(job_id: int, payload: Dict[str, Any] = Body(...)):
    status = payload.pop("status", "running")
    log = payload.pop("log", None)
    runner_state = payload.pop("runner_state", None)
    db.update_job_status(job_id, status, log=log, runner_state=runner_state, **payload)
    return {"success": True}

@router.get("/jobs/{job_id}")
def get_job(job_id: int):
    job = db.get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.post("/jobs/dequeue")
def dequeue_job(payload: Dict[str, Any] = Body(...)):
    if payload.get("job_types"):
        raise HTTPException(status_code=400, detail="job_types filtering is not supported")
    return db.dequeue_next_job()

@router.post("/jobs/enqueue")
def enqueue_job(payload: Dict[str, Any] = Body(...)):
    input_path = payload.get("input_path", "")
    job_id, queue_position = db.enqueue_job(
        input_path,
        phase_code=payload.get("phase_code"),
        job_type=payload.get("job_type"),
        queue_payload=payload.get("queue_payload"),
        description=payload.get("description"),
    )
    return {"success": job_id is not None, "job_id": job_id, "queue_position": queue_position}

@router.post("/jobs/recover")
def recover_interrupted_jobs():
    return db.recover_interrupted_jobs()

@router.get("/jobs/{job_id}/phases")
def get_job_phases(job_id: int):
    return db.get_job_phases(job_id)

@router.post("/jobs/{job_id}/phases")
def create_job_phase(job_id: int, payload: Dict[str, Any] = Body(...)):
    phase_code = payload.get("phase_code")
    if not phase_code:
        raise HTTPException(status_code=400, detail="Missing phase_code")
    status = payload.get("status", "queued")
    db.create_job_phases(job_id, [phase_code], status)
    return {"success": True}

@router.put("/jobs/{job_id}/phases/{phase_code}")
def update_job_phase(job_id: int, phase_code: str, payload: Dict[str, Any] = Body(...)):
    status = payload.get("status")
    error_message = payload.get("error_message")
    db.set_job_phase_state(job_id, phase_code, status, error_message=error_message)
    return {"success": True}

# =========================================================================
# Folders
# =========================================================================

@router.get("/folders")
def get_folders():
    return db.get_all_folders()

@router.get("/folders/scored")
def is_folder_scored(folder_path: str = Query(...)):
    scored = db.is_folder_scored(folder_path)
    return {"scored": scored}

@router.post("/folders/get-or-create")
def get_or_create_folder(payload: Dict[str, Any] = Body(...)):
    folder_path = payload.get("folder_path")
    if not folder_path:
        raise HTTPException(status_code=400, detail="Missing folder_path")
    folder_id = db.get_or_create_folder(folder_path)
    return {"folder_id": folder_id}

@router.post("/folders/sync")
def sync_folders(payload: List[str] = Body(...)):
    db.sync_folders(payload)
    return {"success": True}

@router.get("/folders/phase-summary")
def get_folder_phase_summary(folder_path: str = Query(...)):
    return db.get_folder_phase_summary(folder_path)

@router.put("/folders/phase-status")
def update_folder_phase_status(payload: Dict[str, Any] = Body(...)):
    folder_path = payload.get("folder_path")
    phase_code = payload.get("phase_code")
    status = payload.get("status")
    db.set_folder_phase_status(folder_path, phase_code, status)
    return {"success": True}

# =========================================================================
# Stacks
# =========================================================================

@router.get("/stacks/count")
def get_stacks_count(folder_id: Optional[int] = Query(None)):
    count = db.get_stacks_count(folder_id=folder_id)
    return {"count": count}

@router.post("/stacks/by-image-ids")
def get_stacks_by_image_ids(payload: List[int] = Body(...)):
    return db.get_stacks_by_image_ids(payload)

@router.post("/stacks/batch-create")
def create_stacks_batch(payload: List[Dict[str, Any]] = Body(...)):
    # Each item: {"image_ids": [int], "folder_id": int, "stack_type": str}
    for item in payload:
        db.create_stack(item["image_ids"], item.get("folder_id"), item.get("stack_type", "similarity"))
    return {"success": True}

@router.post("/stacks/clear")
def clear_stacks(folder_id: int = Body(..., embed=True)):
    db.clear_stacks(folder_id)
    return {"success": True}

# =========================================================================
# Culling
# =========================================================================

@router.post("/culling/sessions")
def create_culling_session(payload: Dict[str, Any] = Body(...)):
    folder_path = payload.get("folder_path")
    if not folder_path:
        raise HTTPException(status_code=400, detail="Missing folder_path")
    mode = payload.get("mode", "automated")
    session_id = db.create_culling_session(folder_path, mode)
    return {"session_id": session_id}

@router.get("/culling/sessions/{session_id}")
def get_culling_session(session_id: int):
    session = db.get_culling_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session

# =========================================================================
# Utilities
# =========================================================================

@router.post("/utils/generate-uuid")
def generate_uuid(payload: Dict[str, Any] = Body(...)):
    metadata = payload.get("metadata", {})
    image_uuid = db.generate_image_uuid(metadata)
    return {"uuid": image_uuid}

@router.post("/backup")
def backup_database():
    message = db.backup_database()
    ok = not message.lower().startswith("failed to")
    return {"success": ok, "message": message}
