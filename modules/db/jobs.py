import datetime
import json
import logging
from typing import Optional, List, Dict, Any

from modules.db._shared import (
    logger,
    JOB_TERMINAL_STATES,
    JOB_ALLOWED_TRANSITIONS,
    STALE_RUNNING_RECONCILED_MSG,
    GRACEFUL_PAUSE_MSG,
    _JOB_HISTORY_STATUSES,
    POST_RUN_AUDIT_SAMPLE_CAP,
    event_manager,
    record_pipeline_event,
)
from modules.db.engine import get_connector, get_db
from modules import config

# --- Cache ---
_phase_id_cache = {}

def parse_queue_payload_dict(raw) -> dict:
    """Best-effort parse of ``jobs.queue_payload`` into a dict."""
    if not raw:
        return {}
    try:
        p = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(p, str):
            p = json.loads(p)
        return p if isinstance(p, dict) else {}
    except Exception:
        return {}

def should_run_post_completion_audit(payload: dict) -> bool:
    """Whether to run ``build_validation_repair_plan`` after a job completes."""
    if not isinstance(payload, dict):
        return False
    if payload.get("post_run_audit") is False:
        return False
    # Use config.get for consistency with other parts of jobs.py if needed, 
    # but the previous version used config.get_config_value.
    # Actually, config.py has get_config_value.
    if bool(config.get_config_value("processing.post_run_data_quality_audit", False)):
        return True
    if payload.get("post_run_audit") is True:
        return True
    if (payload.get("run_mode") or "").strip() == "validate_and_repair":
        return True
    return False

def _cap_id_list(ids, cap: int):
    """Return (sorted unique int list capped to ``cap``, truncated bool)."""
    out: list = []
    seen = set()
    for x in ids or []:
        try:
            i = int(x)
        except (TypeError, ValueError):
            continue
        if i in seen:
            continue
        seen.add(i)
        out.append(i)
    out.sort()
    if len(out) <= cap:
        return out, False
    return out[:cap], True

def _append_job_log_line(job_id: int, message: str) -> None:
    get_connector().execute(
        "UPDATE jobs SET log = COALESCE(log, '') || ? WHERE id = ?",
        ("\n" + message, job_id),
    )

def _maybe_fail_job_on_post_audit_issues(job_id: int, post_run_audit: dict) -> None:
    """If ``processing.post_run_audit_fail_job_on_issues``, mark a completed job failed when issues remain."""
    if not isinstance(post_run_audit, dict):
        return
    if post_run_audit.get("status") != "issues_remaining":
        return
    if not bool(config.get_config_value("processing.post_run_audit_fail_job_on_issues", False)):
        return
    msg = (
        "\npost_run_audit_fail_job_on_issues: residual data-quality issues ??? "
        "see queue_payload.post_run_audit"
    )
    conn = get_connector()
    row = conn.query_one("SELECT status FROM jobs WHERE id = ?", (job_id,))
    if not row or (row.get("status") or "").strip().lower() != "completed":
        return
    conn.execute(
        "UPDATE jobs SET status = 'failed', runner_state = 'failed', log = COALESCE(log, '') || ? "
        "WHERE id = ? AND status = 'completed'",
        (msg, job_id),
    )
    try:
        record_pipeline_event(
            "error",
            f"Job #{job_id} marked failed after post-run audit (post_run_audit_fail_job_on_issues)",
            workflow_run=job_id,
            category="job",
            source="db.post_run_audit",
        )
    except Exception:
        pass



def get_phase_id(phase_code):
    """
    Look up pipeline_phases.id by code. Result is cached per-process.
    """
    code = phase_code.value if hasattr(phase_code, "value") else str(phase_code)
    
    if code in _phase_id_cache:
        return _phase_id_cache[code]

    row = get_connector().query_one("SELECT id FROM pipeline_phases WHERE code = ?", (code,))
    if row:
        _phase_id_cache[code] = row["id"]
        return row["id"]
    return None

def create_job(input_path, phase_code=None, job_type=None, status="pending", current_phase=None,
               next_phase_index=None, runner_state=None, queue_payload=None, description=None,
               priority=100, actor=None):
    """
    Create a new job record in the database.
    """
    if queue_payload is not None and not isinstance(queue_payload, str):
        queue_payload = json.dumps(queue_payload)

    # Resolve phase_code to phase_id FK
    phase_id = get_phase_id(phase_code) if phase_code else None

    # Note: updated_at and actor are not in the schema.
    # phase_code in jobs table is actually phase_id.
    sql = """
        INSERT INTO jobs (
            input_path, phase_id, job_type, status, current_phase,
            next_phase_index, runner_state, queue_payload, description,
            priority, created_at, enqueued_at, cancel_requested
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
    """
    now = datetime.datetime.now()
    params = (
        input_path, phase_id, job_type, status, current_phase,
        next_phase_index, runner_state, queue_payload, description,
        priority, now, now
    )
    
    result = get_connector().execute_returning(
        sql + " RETURNING id",
        params
    )
    job_id = result[0]["id"] if result else None

    if job_id:
        record_pipeline_event(
            "state-change",
            f"Job #{job_id} created ({status})",
            workflow_run=job_id,
            stage_run=phase_code or job_type or "pipeline",
            step_run="job:create",
            category="job",
            metadata={
                "status": status,
                "input_path": input_path,
                "job_type": job_type,
                "phase_code": phase_code,
                "description": description,
            },
            source="db.create_job",
        )
    return job_id

def get_job(job_id):
    """Retrieve a single job record by ID."""
    return get_connector().query_one("SELECT * FROM jobs WHERE id = ?", (job_id,))

def get_job_by_id(job_id):
    """Alias for get_job."""
    return get_job(job_id)

def update_job_status(job_id, status, log=None, current_phase=None, next_phase_index=None, runner_state=None):
    """
    Update job status and related fields with transition validation.
    """
    effect_status = (status or "").strip().lower()
    effect_log = log
    if effect_status == "completed":
        strict_fail = _strict_verify_resolved_ids_terminal_for_phase(job_id)
        if strict_fail:
            effect_status = "failed"
            effect_log = strict_fail if log is None else f"{log}\n{strict_fail}"

    # Normalize canceled -> cancelled for consistency
    if effect_status == "canceled":
        effect_status = "cancelled"

    def _tx(tx):
        row = tx.query_one(
            "SELECT status, current_phase, next_phase_index, runner_state, log, phase_id, job_type FROM jobs WHERE id = ?",
            (job_id,),
        )
        if not row:
            raise ValueError(f"Job not found: {job_id}")

        old_status = (row["status"] or "pending").strip().lower()
        new_status = effect_status
        root_job_type = row.get("job_type")

        allowed_next = JOB_ALLOWED_TRANSITIONS.get(old_status)
        if allowed_next is not None and old_status != new_status and new_status not in allowed_next:
            raise ValueError(f"Invalid job status transition: {old_status} -> {new_status} (job_id={job_id})")

        final_log = effect_log
        # Keep existing cursor values unless caller explicitly overrides
        final_phase = current_phase if current_phase is not None else row["current_phase"]
        final_next_idx = next_phase_index if next_phase_index is not None else row["next_phase_index"]
        final_runner_state = runner_state if runner_state is not None else row["runner_state"]

        now = datetime.datetime.now()
        count_row = tx.query_one("SELECT COUNT(*) AS cnt FROM job_phases WHERE job_id = ?", (job_id,))
        n_phases = int(count_row["cnt"]) if count_row else 0

        phase_state_map = {
            "queued": "queued",
            "running": "running",
            "paused": "paused",
            "cancel_requested": "cancel_requested",
            "restarting": "restarting",
            "completed": "completed",
            "failed": "failed",
            "canceled": "cancelled",
            "cancelled": "cancelled",
            "interrupted": "interrupted",
        }

        # Multi-phase support
        if new_status == "completed" and n_phases > 1:
            phase_state = phase_state_map.get(new_status, "running")
            multi = _resolve_multi_phase_job_phases_sync_code(job_id, new_status, tx=tx)
            if multi:
                set_job_phase_state(
                    job_id,
                    multi,
                    phase_state,
                    error_message=effect_log if new_status in {"failed", "interrupted"} else None,
                    tx=tx,
                )

            phases = get_job_phases(job_id, tx=tx)
            terminal_states = {"completed", "skipped", "canceled", "cancelled"}

            def _phase_terminal(p):
                return (p.get("state") or "").strip().lower() in terminal_states

            all_terminal = (not phases) or all(_phase_terminal(p) for p in phases)
            eff_log = effect_log if effect_log is not None else row.get("log")

            if not all_terminal:
                active = next(
                    (p for p in phases if (p.get("state") or "").strip().lower() == "running"),
                    None,
                )
                if active is None:
                    active = next((p for p in phases if not _phase_terminal(p)), None)
                if active is None:
                    pc_fallback = get_next_running_job_phase(job_id, tx=tx)
                    if pc_fallback:
                        po_fb = next(
                            (int(p["phase_order"]) for p in phases if (p.get("phase_code") or "") == pc_fallback),
                            0,
                        )
                        active = {"phase_code": pc_fallback, "phase_order": po_fb}
                if active:
                    pc = active.get("phase_code")
                    po = int(active.get("phase_order") or 0)
                    pid = get_phase_id(pc)
                    tx.execute(
                        "UPDATE jobs SET status = 'running', finished_at = NULL, completed_at = NULL, "
                        "log = ?, current_phase = ?, next_phase_index = ?, runner_state = 'running', "
                        "phase_id = COALESCE(?, phase_id) WHERE id = ?",
                        (eff_log, pc, po, pid, job_id),
                    )
                    return old_status, "running", pc, po, "running", root_job_type

            final_rs = runner_state if runner_state is not None else "completed"
            tx.execute(
                "UPDATE jobs SET status = ?, finished_at = ?, completed_at = ?, log = ?, current_phase = ?, next_phase_index = ?, runner_state = ? WHERE id = ?",
                ("completed", now, now, eff_log, final_phase, final_next_idx, final_rs, job_id),
            )
            return old_status, "completed", final_phase, final_next_idx, final_rs, root_job_type

        if new_status == "running":
            tx.execute(
                "UPDATE jobs SET status = ?, started_at = COALESCE(started_at, ?), log = ?, current_phase = ?, next_phase_index = ?, runner_state = ? WHERE id = ?",
                (new_status, now, final_log, final_phase, final_next_idx, final_runner_state, job_id),
            )
        elif new_status in JOB_TERMINAL_STATES:
            tx.execute(
                "UPDATE jobs SET status = ?, finished_at = ?, completed_at = ?, log = ?, current_phase = ?, next_phase_index = ?, runner_state = ? WHERE id = ?",
                (new_status, now, now, final_log, final_phase, final_next_idx, final_runner_state, job_id),
            )
        else:
            tx.execute(
                "UPDATE jobs SET status = ?, log = ?, current_phase = ?, next_phase_index = ?, runner_state = ? WHERE id = ?",
                (new_status, final_log, final_phase, final_next_idx, final_runner_state, job_id),
            )
        return old_status, new_status, final_phase, final_next_idx, final_runner_state, root_job_type

    return get_connector().run_transaction(_tx)

def update_job_progress(job_id, percent):
    """Broadcast percent-complete progress for long-running maintenance jobs (Runs UI WebSocket)."""
    try:
        p = max(0, min(100, int(percent) if str(percent).isdigit() else 0))
    except (TypeError, ValueError):
        p = 0
    
    try:
        # Broadcast via event_manager for WebUI/WebSocket updates
        event_manager.broadcast_threadsafe(
            "job_progress",
            {
                "job_id": job_id,
                "job_type": "maintenance",
                "phase_code": "maintenance",
                "current": p,
                "total": 100,
            },
        )
    except Exception:
        logger.debug("update_job_progress: broadcast failed for job_id=%s", job_id, exc_info=True)

def update_job_log(job_id, log):
    """Update job log content."""
    def _tx(tx):
        row = tx.query_one("SELECT id FROM jobs WHERE id = ?", (job_id,))
        if not row:
            raise ValueError(f"Job not found: {job_id}")
        tx.execute("UPDATE jobs SET log = ? WHERE id = ?", (log, job_id))

    return get_connector().run_transaction(_tx)

def enqueue_job(input_path, phase_code=None, job_type=None, queue_payload=None, description=None):
    """Helper to create a 'pending' job."""
    return create_job(
        input_path=input_path,
        phase_code=phase_code,
        job_type=job_type,
        status="pending",
        queue_payload=queue_payload,
        description=description
    )

def dequeue_next_job():
    """Find and mark the next 'pending' job as 'running'."""
    def _tx(tx):
        sql = """
            SELECT id FROM jobs 
            WHERE status = 'pending' 
            ORDER BY priority DESC, created_at ASC
            LIMIT 1
        """
        job = tx.query_one(sql)
        if job:
            job_id = job["id"]
            tx.execute(
                "UPDATE jobs SET status = 'running', started_at = ? WHERE id = ?",
                (datetime.datetime.now(), job_id)
            )
            return job_id
        return None
    return get_connector().run_transaction(_tx)

def job_should_stop_processing(job_id) -> bool:
    """True if the job row indicates the worker should stop (pause, cancel, interrupt, or cancel_requested)."""
    if job_id is None:
        return False
    try:
        jid = int(job_id)
    except (TypeError, ValueError):
        return False
    row = get_job(jid)
    if not row:
        return False
    st = (row.get("status") or "").strip().lower()
    if st in ("paused", "canceled", "cancelled", "interrupted"):
        return True
    try:
        if int(row.get("cancel_requested") or 0) != 0:
            return True
    except (TypeError, ValueError):
        pass
    return False

def request_cancel_job(job_id):
    """Signal a job to stop."""
    get_connector().execute(
        "UPDATE jobs SET status = 'cancel_requested' WHERE id = ? AND status = 'running'",
        (job_id,)
    )

def set_job_phase_state(job_id, phase_code, state, error_message=None, tx=None):
    """Update state metadata for one phase of a job and auto-advance next pending phase."""
    allowed = {
        "pending": {"queued", "running", "skipped", "canceled", "failed"},
        "queued": {"running", "paused", "cancel_requested", "canceled", "failed"},
        "running": {
            "paused", "completed", "failed", "interrupted", "cancel_requested",
            "restarting", "canceled",
        },
        "paused": {"running", "restarting", "cancel_requested", "canceled"},
        "cancel_requested": {"canceled", "failed"},
        "restarting": {"queued", "running", "failed"},
        "completed": set(),
        "failed": {"skipped", "pending"},
        "interrupted": {"running", "failed", "skipped", "pending", "queued"},
        "skipped": set(),
        "canceled": set(),
    }
    now = datetime.datetime.now()

    def _tx(tx):
        row = tx.query_one(
            "SELECT id, state FROM job_phases WHERE job_id = ? AND phase_code = ?",
            (job_id, phase_code),
        )
        if not row:
            return None

        phase_id = row["id"]
        old_state = str(row["state"] or "pending").strip().lower()
        new_state = str(state or "").strip().lower()
        if old_state != new_state and new_state not in allowed.get(old_state, set()):
            if not (old_state == "failed" and new_state in ("skipped", "pending")):
                msg = f"Invalid job phase transition: {old_state} -> {new_state} (job_id={job_id}, phase={phase_code})"
                logger.warning(msg)
                raise ValueError(msg)

        fields = ["state = ?"]
        params = [state]
        if state == "running":
            fields.append("started_at = COALESCE(started_at, ?)")
            params.append(now)
            fields.append("error_message = NULL")
        if state in {"completed", "failed", "skipped", "interrupted"}:
            fields.append("completed_at = ?")
            params.append(now)
        if error_message is not None:
            fields.append("error_message = ?")
            params.append(error_message)

        params.append(phase_id)
        tx.execute(f"UPDATE job_phases SET {', '.join(fields)} WHERE id = ?", params)

        if state in {"completed", "skipped"}:
            next_row = tx.query_one(
                "SELECT id FROM job_phases WHERE job_id = ? AND phase_order > "
                "(SELECT phase_order FROM job_phases WHERE id = ?) AND state = 'pending' "
                "ORDER BY phase_order FETCH FIRST 1 ROWS ONLY",
                (job_id, phase_id),
            )
            if next_row:
                tx.execute(
                    "UPDATE job_phases SET state = 'running', started_at = COALESCE(started_at, ?), error_message = NULL WHERE id = ?",
                    (now, next_row["id"]),
                )
        return True

    if tx:
        return _tx(tx)
    
    result = get_connector().run_transaction(_tx)
    if result is None:
        return None
        
    try:
        from modules.run_log import emit_run_log
        st = str(state or "").strip().lower()
        lvl = "ERROR" if st == "failed" else "INFO"
        emit_run_log(int(job_id), f"Stage {phase_code}: {st}", lvl, phase=str(phase_code), step="workflow")
    except Exception:
        pass
    return get_job_phases(job_id)

def get_job_phases(job_id, tx=None):
    """Get ordered phase plan/status rows for a job."""
    conn = tx if tx else get_connector()
    return [dict(r) for r in conn.query(
        "SELECT phase_order, phase_code, state, started_at, completed_at, error_message "
        "FROM job_phases WHERE job_id = ? ORDER BY phase_order",
        (job_id,),
    )]

def _resolve_multi_phase_job_phases_sync_code(job_id, new_status, tx=None):
    """Determine which phase matches job status for multi-phase workflows."""
    phases = get_job_phases(job_id, tx=tx)
    if not phases or len(phases) <= 1:
        return None
    st = (new_status or "").strip().lower()
    if st == "running":
        for p in phases:
            if (p.get("state") or "").strip().lower() == "running":
                return p.get("phase_code")
        for p in phases:
            row_state = (p.get("state") or "").strip().lower()
            if row_state in ("queued", "pending"):
                return p.get("phase_code")
        return phases[0].get("phase_code")
    if st == "completed":
        terminal_states = {"completed", "skipped", "canceled", "cancelled"}
        for p in phases:
            if (p.get("state") or "").strip().lower() == "running":
                return p.get("phase_code")
        unstarted = [p for p in phases if p.get("started_at") is None and (p.get("state") or "").strip().lower() not in terminal_states]
        if unstarted:
            for p in reversed(phases):
                if (p.get("state") or "").strip().lower() not in terminal_states:
                    return p.get("phase_code")
            return unstarted[0].get("phase_code")
        if all((p.get("state") or "").strip().lower() in terminal_states for p in phases):
            return None
        for p in phases:
            pst = (p.get("state") or "").strip().lower()
            if pst not in terminal_states:
                return p.get("phase_code")
        return None
    if st in ("failed", "interrupted", "canceled", "cancelled"):
        for p in phases:
            if (p.get("state") or "").strip().lower() == "running":
                return p.get("phase_code")
        return phases[-1].get("phase_code")
    return None

def get_next_pending_job_phase(job_id, tx=None):
    """Find the next phase ready to run (state='pending')."""
    phases = get_job_phases(job_id, tx=tx)
    for p in phases:
        if (p.get("state") or "").strip().lower() == "pending":
            return p.get("phase_code")
    return None

def get_current_running_job_phase(job_id, tx=None):
    """Return current running phase for a job, if any (state='running')."""
    conn = tx if tx else get_connector()
    row = conn.query_one(
        "SELECT phase_code FROM job_phases WHERE job_id = ? AND state = 'running' ORDER BY phase_order FETCH FIRST 1 ROWS ONLY",
        (job_id,),
    )
    return row["phase_code"] if row else None

def _strict_verify_resolved_ids_terminal_for_phase(job_id):
    """Verify all images in a job reached a terminal state."""
    if not config.get_config_value("processing.strict_job_completion_verify", False):
        return None

    cnt = get_connector().query_one("SELECT COUNT(*) AS c FROM job_phases WHERE job_id = ?", (job_id,))
    n_phases = int((cnt or {}).get("c") or 0)
    if n_phases != 1:
        return None

    row = get_connector().query_one("SELECT queue_payload, phase_id, job_type FROM jobs WHERE id = ?", (job_id,))
    if not row:
        return None
    
    raw = row.get("queue_payload")
    payload = {}
    if raw:
        try:
            payload = json.loads(raw) if isinstance(raw, str) else {}
            if isinstance(payload, str):
                payload = json.loads(payload)
        except Exception:
            payload = {}
    
    resolved = payload.get("resolved_image_ids")
    if not resolved or not isinstance(resolved, (list, tuple)):
        return None
    
    image_ids = []
    for x in resolved:
        try:
            image_ids.append(int(x))
        except (TypeError, ValueError):
            continue
    if not image_ids:
        return None

    phase_code = None
    pid = row.get("phase_id")
    if pid:
        prow = get_connector().query_one("SELECT code FROM pipeline_phases WHERE id = ?", (pid,))
        if prow and prow.get("code"):
            phase_code = str(prow["code"]).strip().lower()
    
    if not phase_code:
        jt = (row.get("job_type") or "").strip().lower()
        phase_code = {
            "tagging": "keywords", "selection": "culling", "scoring": "scoring",
            "score": "scoring", "metadata": "metadata", "indexing": "indexing",
            "clustering": "culling", "cluster": "culling", "bird_species": "bird_species",
        }.get(jt, jt)
    
    if not phase_code:
        return None

    phase_id = get_phase_id(phase_code)
    if phase_id is None:
        return None

    terminal = ("done", "failed", "skipped")
    bad = 0
    for iid in image_ids:
        srow = get_connector().query_one(
            "SELECT status FROM image_phase_status WHERE image_id = ? AND phase_id = ?",
            (iid, phase_id),
        )
        st = (srow.get("status") or "not_started").strip().lower() if srow else "not_started"
        if st not in terminal:
            bad += 1

    if bad:
        return (f"strict_job_completion_verify: {bad}/{len(image_ids)} images non-terminal "
                f"for phase {phase_code!r} (job {job_id})")
    return None

def job_type_for_phase_dispatch(phase_code: str) -> str:
    """Map a phase code to its dispatcher job_type."""
    m = {
        "keywords": "tagging",
        "culling": "selection",
        "scoring": "scoring",
        "metadata": "metadata",
        "indexing": "indexing",
        "bird_species": "bird_species",
    }
    return m.get(phase_code, phase_code)

def get_running_job_for_phase_continuation():
    """Find a job currently marked 'running' that potentially needs continuation."""
    return get_connector().query_one(
        "SELECT * FROM jobs WHERE status = 'running' ORDER BY started_at DESC LIMIT 1"
    )

def update_job_payload(job_id: int, queue_payload):
    """Update queue_payload column for a job. Accepts dict or JSON string."""
    if isinstance(queue_payload, dict):
        queue_payload = json.dumps(queue_payload)
    elif not isinstance(queue_payload, str):
        # Allow None but reject other types
        if queue_payload is not None:
             raise TypeError(f"update_job_payload: expected str or dict, got {type(queue_payload)}")
    get_connector().run_transaction(
        lambda tx: tx.execute("UPDATE jobs SET queue_payload = ? WHERE id = ?", (queue_payload, job_id))
    )

def insert_job_image_actions(actions: List[dict]) -> None:
    """Batch insert into job_image_actions.
    Uses a multi-row INSERT for efficiency.
    Postgres-only (uses jsonb cast).
    """
    if not actions:
        return
    conn = get_connector()
    value_groups = []
    params: List = []
    for row in actions:
        value_groups.append("(?, ?, ?, ?, ?, ?::jsonb, ?::jsonb)")
        params.extend([
            row["job_id"],
            row["image_id"],
            row["phase_code"],
            row["action"],
            row.get("reason"),
            json.dumps(row["before_snapshot"]) if row.get("before_snapshot") is not None else None,
            json.dumps(row["after_snapshot"]) if row.get("after_snapshot") is not None else None,
        ])
    sql = (
        "INSERT INTO job_image_actions "
        "(job_id, image_id, phase_code, action, reason, before_snapshot, after_snapshot) "
        "VALUES " + ", ".join(value_groups)
    )
    conn.execute(sql, tuple(params))

def save_job_report(job_id: int, report: dict) -> None:
    """Write report_json JSONB to the jobs table."""
    get_connector().execute(
        "UPDATE jobs SET report_json = ?::jsonb WHERE id = ?",
        (json.dumps(report), int(job_id)),
    )

def get_job_report(job_id: int) -> Optional[dict]:
    """Read report_json from the jobs table."""
    row = get_connector().query_one(
        "SELECT report_json FROM jobs WHERE id = ?",
        (int(job_id),),
    )
    if not row:
        return None
    raw = row.get("report_json")
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
    if isinstance(raw, dict):
        return raw
    return None

def get_job_image_actions(
    job_id: int,
    phase_code: Optional[str] = None,
    action: Optional[str] = None,
    offset: int = 0,
    limit: int = 50,
) -> dict:
    """Query job_image_actions with filtering and pagination."""
    jid = int(job_id)
    where = ["jia.job_id = ?"]
    params: List = [jid]

    if phase_code:
        where.append("LOWER(TRIM(jia.phase_code)) = ?")
        params.append(phase_code.strip().lower())
    if action:
        where.append("LOWER(TRIM(jia.action)) = ?")
        params.append(action.strip().lower())

    where_sql = " AND ".join(where)
    conn = get_connector()

    count_row = conn.query_one(
        f"SELECT COUNT(*) AS c FROM job_image_actions jia WHERE {where_sql}",
        tuple(params),
    )
    total = int((count_row.get("c") or count_row.get("COUNT(*)") or 0) if count_row else 0)

    rows = conn.query(
        f"""
        SELECT jia.id, jia.image_id, i.file_path, jia.phase_code, jia.action,
               jia.reason, jia.before_snapshot, jia.after_snapshot, jia.created_at
        FROM job_image_actions jia
        LEFT JOIN images i ON i.id = jia.image_id
        WHERE {where_sql}
        ORDER BY jia.id
        OFFSET ? LIMIT ?
        """,
        tuple(params) + (offset, limit),
    )

    items = []
    for r in rows or []:
        before = r.get("before_snapshot")
        after = r.get("after_snapshot")
        if isinstance(before, str):
            try:
                before = json.loads(before)
            except Exception:
                pass
        if isinstance(after, str):
            try:
                after = json.loads(after)
            except Exception:
                pass
        items.append({
            "id": r.get("id"),
            "image_id": r.get("image_id"),
            "file_path": r.get("file_path"),
            "phase_code": (r.get("phase_code") or "").strip(),
            "action": (r.get("action") or "").strip(),
            "reason": r.get("reason"),
            "before_snapshot": before,
            "after_snapshot": after,
            "created_at": str(r.get("created_at") or ""),
        })

    return {"items": items, "total": total}

def update_job_phase_counters(
    job_id: int,
    phase_code: str,
    *,
    in_scope: int = 0,
    targeted: int = 0,
    processed: int = 0,
    skipped: int = 0,
    failed: int = 0,
) -> None:
    """Update counter columns on a job_phases row."""
    get_connector().execute(
        """
        UPDATE job_phases
        SET images_in_scope = ?,
            images_targeted = ?,
            images_processed = ?,
            images_skipped = ?,
            images_failed = ?
        WHERE job_id = ? AND LOWER(TRIM(phase_code)) = ?
        """,
        (in_scope, targeted, processed, skipped, failed, int(job_id), phase_code.strip().lower()),
    )

def recover_running_jobs(mark_as="interrupted"):
    """Mark stale running jobs (and their in-flight job_phases) as interrupted."""
    rows = get_connector().query("SELECT id FROM jobs WHERE status = 'running'")
    recovered = [r["id"] for r in rows]
    if recovered:
        now = datetime.datetime.now()
        def _tx(tx):
            tx.execute(
                "UPDATE jobs SET status = ?, completed_at = ?, runner_state = ? WHERE status = 'running'",
                (mark_as, now, mark_as),
            )
            placeholders = ",".join("?" * len(recovered))
            tx.execute(
                f"UPDATE job_phases SET state = ?, completed_at = ? "
                f"WHERE job_id IN ({placeholders}) AND state = 'running'",
                [mark_as, now] + recovered,
            )
        get_connector().run_transaction(_tx)
        try:
            n = reconcile_stale_running_phases_for_jobs(
                recovered,
                error_message=f"stale_running_reconciled:job_{mark_as}",
                in_flight_to="not_started",
            )
            if n:
                logger.info("recover_running_jobs: reconciled %s stale image_phase_status rows", n)
        except Exception:
            logger.exception("recover_running_jobs: image_phase_status reconcile failed")
    return recovered

def count_reconcilable_terminal_job_phases() -> int:
    """Count image_phase_status rows in 'running' state for jobs that are terminal."""
    row = get_connector().query_one(
        """
        SELECT COUNT(*) as cnt
        FROM image_phase_status ips
        JOIN jobs j ON j.id = ips.job_id
        WHERE ips.status = 'running'
          AND j.status IN ('completed', 'failed', 'canceled', 'interrupted')
        """
    )
    return int(row["cnt"] if row else 0)

def reconcile_stale_running_phases_for_terminal_jobs(limit=5000) -> int:
    """Find jobs in terminal states and reset any stuck 'running' image phases to 'failed'."""
    rows = get_connector().query(
        """
        SELECT DISTINCT j.id
        FROM jobs j
        JOIN image_phase_status ips ON ips.job_id = j.id
        WHERE j.status IN ('completed', 'failed', 'canceled', 'interrupted')
          AND ips.status = 'running'
        LIMIT ?
        """,
        (limit,)
    )
    job_ids = [r["id"] for r in rows]
    if not job_ids:
        return 0
    
    return reconcile_stale_running_phases_for_jobs(
        job_ids, 
        error_message="reconcile_terminal:job_finished",
        in_flight_to="failed"
    )

def reconcile_stale_running_phases_for_jobs(job_ids, error_message=None, in_flight_to="failed"):
    """
    Resolve image_phase_status rows still ``running`` for the given job id(s).
    """
    msg = (error_message or STALE_RUNNING_RECONCILED_MSG).strip() or STALE_RUNNING_RECONCILED_MSG
    if not job_ids:
        return 0
    job_ids = [int(x) for x in job_ids]
    placeholders = ",".join("?" * len(job_ids))
    mode = (in_flight_to or "failed").strip().lower()
    if mode not in ("failed", "not_started"):
        mode = "failed"

    conn = get_connector()
    folder_rows = conn.query(
        f"""
        SELECT DISTINCT i.folder_id AS folder_id
        FROM image_phase_status ips
        JOIN images i ON i.id = ips.image_id
        WHERE ips.job_id IN ({placeholders}) AND ips.status = 'running'
        """,
        job_ids,
    )
    folder_ids = [r["folder_id"] for r in folder_rows if r and r.get("folder_id") is not None]

    now = datetime.datetime.now()
    if mode == "not_started":
        params = [msg, now] + job_ids
        rowcount = conn.execute(
            f"""
            UPDATE image_phase_status
            SET status = 'not_started', last_error = ?, finished_at = NULL, started_at = NULL, updated_at = ?
            WHERE job_id IN ({placeholders}) AND status = 'running'
            """,
            params,
        )
    else:
        params = [msg, now, now] + job_ids
        rowcount = conn.execute(
            f"""
            UPDATE image_phase_status
            SET status = 'failed', last_error = ?, finished_at = ?, updated_at = ?
            WHERE job_id IN ({placeholders}) AND status = 'running'
            """,
            params,
        )
    
    return int(rowcount or 0)

def reconcile_duplicate_running_job_phases(job_id=None, limit_jobs=500):
    """
    Fix ``job_phases`` rows where more than one phase is ``running`` for the same job.
    """
    try:
        limit_jobs = max(1, int(limit_jobs))
    except (TypeError, ValueError):
        limit_jobs = 500

    conn = get_connector()
    if job_id is not None:
        job_ids = [int(job_id)]
    else:
        rows = conn.query(
            """
            SELECT job_id FROM job_phases
            WHERE LOWER(TRIM(CAST(state AS VARCHAR(128)))) = 'running'
            GROUP BY job_id
            HAVING COUNT(*) > 1
            ORDER BY job_id
            FETCH FIRST ? ROWS ONLY
            """,
            (limit_jobs,),
        )
        job_ids = [int(r["job_id"]) for r in rows if r and r.get("job_id") is not None]

    if not job_ids:
        return {"jobs_fixed": 0, "phases_reset": 0}

    jobs_fixed = 0
    phases_reset = 0

    for jid in job_ids:
        rows = conn.query(
            "SELECT id, phase_order, phase_code, state FROM job_phases WHERE job_id = ? ORDER BY phase_order",
            (jid,),
        )
        if not rows:
            continue
        running_rows = [r for r in rows if (r.get("state") or "").strip().lower() == "running"]
        if len(running_rows) <= 1:
            continue
        keeper_id = int(running_rows[0]["id"])
        reset_ids = [int(r["id"]) for r in running_rows[1:]]

        def _tx(tx):
            for rid in reset_ids:
                tx.execute(
                    "UPDATE job_phases SET state = 'pending', started_at = NULL, "
                    "completed_at = NULL, error_message = NULL WHERE id = ?",
                    (rid,),
                )
        conn.run_transaction(_tx)
        jobs_fixed += 1
        phases_reset += len(reset_ids)
        logger.info(
            "reconcile_duplicate_running_job_phases: job_id=%s kept phase row id=%s, reset %s row(s)",
            jid, keeper_id, len(reset_ids),
        )

    return {"jobs_fixed": jobs_fixed, "phases_reset": phases_reset}

def get_interrupted_jobs(job_type=None, limit=100):
    try: limit = int(limit)
    except (TypeError, ValueError): limit = 100

    conn = get_connector()
    if job_type:
        rows = conn.query(
            "SELECT * FROM jobs WHERE status = 'interrupted' AND job_type = ? ORDER BY created_at DESC FETCH FIRST ? ROWS ONLY",
            (job_type, limit),
        )
    else:
        rows = conn.query(
            "SELECT * FROM jobs WHERE status = 'interrupted' ORDER BY created_at DESC FETCH FIRST ? ROWS ONLY",
            (limit,),
        )
    return [dict(r) for r in rows]

def count_jobs(*, history_only: bool = False, status_filter=None) -> int:
    """Return total job rows (all, terminal-only for history, or filtered by status)."""
    conn = get_connector()
    if status_filter:
        ph = ",".join(["?"] * len(status_filter))
        row = conn.query_one(
            f"SELECT COUNT(*) AS cnt FROM jobs WHERE status IN ({ph})",
            tuple(status_filter),
        )
    elif history_only:
        ph = ",".join(["?"] * len(_JOB_HISTORY_STATUSES))
        row = conn.query_one(
            f"SELECT COUNT(*) AS cnt FROM jobs WHERE status IN ({ph})",
            tuple(_JOB_HISTORY_STATUSES),
        )
    else:
        row = conn.query_one("SELECT COUNT(*) AS cnt FROM jobs", ())
    
    if not row: return 0
    return int(row.get("cnt") or row.get("count") or 0)

def get_recent_jobs(limit=50, offset=0):
    """Retrieve a list of recent jobs, ordered by creation time."""
    return get_jobs(limit=limit, offset=offset)

def get_jobs(limit=50, offset=0, *, history_only=False):
    try: limit = int(limit)
    except (ValueError, TypeError): limit = 50
    try: offset = int(offset)
    except (ValueError, TypeError): offset = 0
    limit = min(max(0, limit), 1000)
    offset = max(0, offset)
    
    conn = get_connector()
    if history_only:
        ph = ",".join(["?"] * len(_JOB_HISTORY_STATUSES))
        sql = (
            f"SELECT * FROM jobs WHERE status IN ({ph}) "
            "ORDER BY created_at DESC OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
        )
        params = (*_JOB_HISTORY_STATUSES, offset, limit)
    else:
        sql = "SELECT * FROM jobs ORDER BY created_at DESC OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
        params = (offset, limit)
    return [dict(r) for r in conn.query(sql, params)]

def enqueue_job_with_phases(input_path, phase_code=None, job_type=None, queue_payload=None, description=None, phase_codes=None, first_phase_state="queued"):
    """Atomically create a queued job and its phase plan in a single transaction."""
    if not phase_codes:
        return None, 0

    phase_id = get_phase_id(phase_code) if phase_code else None
    if job_type is None:
        job_type = phase_code

    now = datetime.datetime.now()
    payload_dict = {}
    if queue_payload is None:
        payload_json = None
    elif isinstance(queue_payload, dict):
        payload_dict = queue_payload
        payload_json = json.dumps(queue_payload)
    elif isinstance(queue_payload, str):
        payload_json = queue_payload
        try:
            parsed = json.loads(queue_payload)
            if isinstance(parsed, dict):
                payload_dict = parsed
        except Exception:
            payload_dict = {}
    else:
        payload_json = json.dumps(queue_payload)

    priority = int((payload_dict or {}).get("priority", 100))
    priority = max(1, min(priority, 999))
    target_scope = None
    if payload_dict:
        target_scope = payload_dict.get("target_scope") or payload_dict.get("scope")
    if not target_scope:
        target_scope = input_path

    def _tx(tx):
        rows = tx.execute_returning(
            """
            INSERT INTO jobs (
                input_path, phase_id, job_type, status, queue_position,
                created_at, enqueued_at, queue_payload, cancel_requested,
                priority, target_scope, retry_count, description
            ) VALUES (?, ?, ?, 'queued', NULL, ?, ?, ?, 0, ?, ?, 0, ?) RETURNING id
            """,
            (input_path, phase_id, job_type, now, now, payload_json, priority, target_scope, description),
        )
        job_id = rows[0]['id'] if rows else None
        if not job_id:
            raise RuntimeError("Failed to insert job row")

        tx.execute("UPDATE jobs SET queue_position = ? WHERE id = ?", (job_id, job_id))

        count_rows = tx.query(
            """
            SELECT COUNT(*) AS cnt FROM jobs
            WHERE status = 'queued' AND COALESCE(queue_position, id) <= ?
            """,
            (job_id,),
        )
        display_position = int((count_rows[0].get('cnt') or count_rows[0].get('COUNT(*)') or 0) if count_rows else 0)

        tx.execute("DELETE FROM job_phases WHERE job_id = ?", (job_id,))
        for idx, pc in enumerate(phase_codes):
            if idx > 0:
                state = "pending"
                started_at = None
            elif first_phase_state == "queued":
                state = "queued"
                started_at = None
            else:
                state = "running"
                started_at = now
            tx.execute(
                "INSERT INTO job_phases (job_id, phase_order, phase_code, state, started_at) VALUES (?, ?, ?, ?, ?)",
                (job_id, idx, pc, state, started_at),
            )
        return job_id, display_position

    try:
        return get_connector().run_transaction(_tx)
    except Exception:
        logger.exception("enqueue_job_with_phases failed")
        return None, 0

def force_reset_job_phase_to_queued(job_id: int, phase_code: str):
    """Admin reset: unconditionally set a phase back to queued."""
    def _tx(tx):
        tx.execute(
            "UPDATE job_phases SET state='queued', started_at=NULL, completed_at=NULL, error_message=NULL "
            "WHERE job_id=? AND phase_code=?",
            (job_id, phase_code),
        )
    get_connector().run_transaction(_tx)

def _maybe_fail_job_on_post_audit_issues(job_id: int, post_run_audit: dict) -> None:
    """Mark a completed job failed when residual issues remain."""
    if not isinstance(post_run_audit, dict):
        return
    if post_run_audit.get("status") != "issues_remaining":
        return
    if not bool(config.get_config_value("processing.post_run_audit_fail_job_on_issues", False)):
        return
    msg = (
        "\npost_run_audit_fail_job_on_issues: residual data-quality issues — "
        "see queue_payload.post_run_audit"
    )
    conn = get_connector()
    row = conn.query_one("SELECT status FROM jobs WHERE id = ?", (job_id,))
    if not row or (row.get("status") or "").strip().lower() != "completed":
        return
    conn.execute(
        "UPDATE jobs SET status = 'failed', runner_state = 'failed', log = COALESCE(log, '') || ? "
        "WHERE id = ? AND status = 'completed'",
        (msg, job_id),
    )

def adjust_job_priority(job_id, delta):
    """Increase/decrease job priority for queued/paused jobs."""
    try:
        d = int(delta)
    except Exception:
        d = 10

    def _tx(tx):
        rowcount = tx.execute(
            """
            UPDATE jobs
            SET priority = CASE
                WHEN COALESCE(priority, 100) + ? < 1 THEN 1
                WHEN COALESCE(priority, 100) + ? > 999 THEN 999
                ELSE COALESCE(priority, 100) + ?
            END
            WHERE id = ? AND status IN ('queued', 'paused')
            """,
            (d, d, d, job_id),
        )
        if rowcount > 0:
            row = tx.query_one("SELECT priority FROM jobs WHERE id = ?", (job_id,))
            new_priority = int(row["priority"]) if row and row["priority"] is not None else 100
        else:
            new_priority = None
        return {"success": rowcount > 0, "priority": new_priority}

    return get_connector().run_transaction(_tx)

def set_job_priority(job_id, priority):
    """Update job priority for queued/paused jobs."""
    try:
        p = max(1, min(int(priority), 999))
    except Exception:
        p = 100
    rowcount = get_connector().execute(
        "UPDATE jobs SET priority = ? WHERE id = ? AND status IN ('queued', 'paused')",
        (p, job_id),
    )
    return {"success": rowcount > 0, "priority": p}

def pause_queue_job(job_id):
    """Pause a queued job so it is temporarily skipped by dequeue."""
    now = datetime.datetime.now()
    rowcount = get_connector().execute(
        "UPDATE jobs SET status = 'paused', paused_at = ? WHERE id = ? AND status = 'queued'",
        (now, job_id),
    )
    return {"success": rowcount > 0}

def restart_failed_job(job_id):
    """Move failed job back to queued and increment retry_count."""
    now = datetime.datetime.now()
    rowcount = get_connector().execute(
        """
        UPDATE jobs
        SET status = 'queued', cancel_requested = 0, enqueued_at = ?, queue_position = id,
            retry_count = COALESCE(retry_count, 0) + 1, paused_at = NULL,
            started_at = NULL, finished_at = NULL, completed_at = NULL
        WHERE id = ? AND status = 'failed'
        """,
        (now, job_id),
    )
    if rowcount > 0:
        resume_job_phases(job_id)
    return {"success": rowcount > 0}

def create_job_phases(job_id, phase_codes, first_phase_state=None):
    """Persist ordered phase plan for a job."""
    if not phase_codes:
        return []

    now = datetime.datetime.now()
    rows = []
    for idx, phase_code in enumerate(phase_codes):
        if idx > 0:
            state = "pending"
            started_at = None
        elif first_phase_state == "queued":
            state = "queued"
            started_at = None
        else:
            state = "running"
            started_at = now
        rows.append((job_id, idx, phase_code, state, started_at))

    def _tx(tx):
        tx.execute("DELETE FROM job_phases WHERE job_id = ?", (job_id,))
        for row in rows:
            tx.execute(
                "INSERT INTO job_phases (job_id, phase_order, phase_code, state, started_at) VALUES (?, ?, ?, ?, ?)",
                row,
            )
    get_connector().run_transaction(_tx)

    return [
        {"phase_order": r[1], "phase_code": r[2], "state": r[3], "started_at": r[4], "completed_at": None, "error_message": None}
        for r in rows
    ]

def resume_job_phases(job_id):
    """Reset incomplete phases for resume. Completed/skipped stay; others -> pending.
    The first incomplete phase is set to 'queued' so the dispatcher picks it up.
    """
    rows = get_connector().query(
        "SELECT phase_order, phase_code, state FROM job_phases WHERE job_id = ? ORDER BY phase_order",
        (job_id,),
    )
    if not rows:
        return []

    keep_states = {"completed", "skipped"}
    first_incomplete_set = False
    updates = []
    for r in rows:
        state = (r["state"] or "").strip().lower()
        if state in keep_states:
            continue
        new_state = "queued" if not first_incomplete_set else "pending"
        first_incomplete_set = True
        updates.append((new_state, job_id, r["phase_code"]))

    if updates:
        def _tx(tx):
            for params in updates:
                tx.execute(
                    "UPDATE job_phases SET state = ?, started_at = NULL, completed_at = NULL, error_message = NULL "
                    "WHERE job_id = ? AND phase_code = ?",
                    params,
                )
        get_connector().run_transaction(_tx)

    return [dict(r) for r in get_connector().query(
        "SELECT phase_order, phase_code, state, started_at, completed_at, error_message "
        "FROM job_phases WHERE job_id = ? ORDER BY phase_order",
        (job_id,),
    )]

def get_job_steps(job_id, phase_code):
    """Return step-level telemetry rows for a job+phase from job_steps table."""
    try:
        rows = get_connector().query(
            "SELECT id, step_code, step_name, status, started_at, completed_at, "
            "items_total, items_done, throughput_rps, error_message "
            "FROM job_steps WHERE job_id = ? AND phase_code = ? ORDER BY id",
            (job_id, phase_code),
        )
        return [
            {
                "id": r["id"],
                "step_code": r["step_code"],
                "step_name": r["step_name"],
                "status": r["status"],
                "started_at": str(r["started_at"]) if r["started_at"] else None,
                "completed_at": str(r["completed_at"]) if r["completed_at"] else None,
                "items_total": r["items_total"] or 0,
                "items_done": r["items_done"] or 0,
                "throughput_rps": r["throughput_rps"],
                "error_message": r["error_message"],
            }
            for r in rows
        ]
    except Exception:
        return []

def upsert_job_step(job_id, phase_code, step_code, step_name, status="pending",
                    items_total=0, items_done=0, throughput_rps=None, error_message=None):
    """Insert or update a step telemetry row in job_steps."""
    now = datetime.datetime.now()
    def _tx(tx):
        row = tx.query_one(
            "SELECT id FROM job_steps WHERE job_id = ? AND phase_code = ? AND step_code = ?",
            (job_id, phase_code, step_code),
        )
        if row:
            tx.execute(
                "UPDATE job_steps SET status = ?, items_total = ?, items_done = ?, "
                "throughput_rps = ?, error_message = ?, "
                "started_at = CASE WHEN status = 'running' THEN COALESCE(started_at, ?) ELSE started_at END, "
                "completed_at = CASE WHEN ? IN ('completed','failed','skipped') THEN ? ELSE completed_at END "
                "WHERE id = ?",
                (status, items_total, items_done, throughput_rps, error_message,
                 now, status, now, row["id"]),
            )
        else:
            tx.execute(
                "INSERT INTO job_steps (job_id, phase_code, step_code, step_name, status, "
                "items_total, items_done, throughput_rps, error_message, started_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (job_id, phase_code, step_code, step_name, status,
                 items_total, items_done, throughput_rps, error_message,
                 now if status == "running" else None),
            )
    try:
        get_connector().run_transaction(_tx)
    except Exception:
        pass

def _duration_ms_from_phase_timestamps(started, finished):
    """Best-effort duration for work-item rows."""
    if not started or not finished:
        return None
    try:
        a, b = started, finished
        if isinstance(a, str):
            s = a.strip()
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            a = datetime.datetime.fromisoformat(s)
        if isinstance(b, str):
            t = b.strip()
            if t.endswith("Z"):
                t = t[:-1] + "+00:00"
            b = datetime.datetime.fromisoformat(t)
        delta = b - a
        return int(delta.total_seconds() * 1000)
    except Exception:
        return None

def get_job_stage_images(job_id, phase_code, offset=0, limit=50):
    """Return work items (images + their phase status) for a specific job+stage."""
    try:
        phase_row = get_connector().query_one(
            "SELECT id FROM pipeline_phases WHERE code = ?", (phase_code,))
        if not phase_row:
            return {"items": [], "total": 0}
        phase_id = phase_row["id"]
        
        conn = get_connector()
        count_row = conn.query_one(
            "SELECT COUNT(*) as c FROM image_phase_status WHERE job_id = ? AND phase_id = ?",
            (job_id, phase_id),
        )
        total = int((count_row.get("c") or count_row.get("COUNT(*)") or 0) if count_row else 0)
        
        rows = conn.query(
            """
            SELECT i.id, i.file_path, ips.status, ips.started_at, ips.updated_at, ips.last_error
            FROM image_phase_status ips
            JOIN images i ON i.id = ips.image_id
            WHERE ips.job_id = ? AND ips.phase_id = ?
            ORDER BY ips.updated_at DESC
            OFFSET ? LIMIT ?
            """,
            (job_id, phase_id, offset, limit),
        )
        
        items = []
        for r in rows:
            duration = _duration_ms_from_phase_timestamps(r["started_at"], r["updated_at"])
            items.append({
                "id": r["id"],
                "file_path": r["file_path"],
                "status": r["status"],
                "last_error": r["last_error"],
                "duration_ms": duration,
                "updated_at": str(r["updated_at"]),
            })
        return {"items": items, "total": total}
    except Exception:
        logger.exception("get_job_stage_images failed")
        return {"items": [], "total": 0}

def requeue_job(job_id):
    """Reset an existing job row to queued status (in-place resume).
    
    Resets started_at, finished_at, completed_at and bumps enqueued_at.
    Updates queue_position so it sorts after any already-queued jobs.
    Returns (job_id, display_position).
    """
    now = datetime.datetime.now()

    def _tx(tx):
        row = tx.query_one("SELECT status FROM jobs WHERE id = ?", (job_id,))
        if not row:
            raise ValueError(f"Job {job_id} not found")
        old_status = (row["status"] or "").strip().lower()
        allowed = JOB_ALLOWED_TRANSITIONS.get(old_status, set())
        if "queued" not in allowed:
            raise ValueError(f"Cannot requeue job from status '{old_status}'")

        tx.execute(
            """
            UPDATE jobs
            SET status = 'queued',
                started_at = NULL,
                finished_at = NULL,
                completed_at = NULL,
                enqueued_at = ?,
                queue_position = ?,
                runner_state = NULL,
                current_phase = NULL,
                cancel_requested = 0
            WHERE id = ?
            """,
            (now, job_id, job_id),
        )

        # Return dense user-facing queue position (1..N), not the internal sort key.
        count_rows = tx.query(
            """
            SELECT COUNT(*) AS cnt FROM jobs
            WHERE status = 'queued' AND COALESCE(queue_position, id) <= ?
            """,
            (job_id,),
        )
        display_position = int((count_rows[0].get('cnt') or 0) if count_rows else 0)
        return job_id, display_position

    try:
        return get_connector().run_transaction(_tx)
    except Exception:
        logger.exception("requeue_job failed for job_id=%s", job_id)
        return job_id, 0


def list_stale_running_image_phase_rows(min_age_seconds: int = 3600, limit: int = 50) -> dict:
    """Find image_phase_status rows stuck in 'running' longer than min_age_seconds.

    Used to detect folder phase badges stuck showing 'running' after crashes or forced stops.

    Returns:
        dict: {
            "count_estimate": int,  # Total count of stale running rows
            "rows": [               # Up to 'limit' rows
                {
                    "image_id": int,
                    "image_file_path": str,
                    "phase_code": str,
                    "status": str,
                    "updated_at": datetime,
                    "age_seconds": int,
                    "job_id": int or None,
                    "last_error": str or None
                },
                ...
            ]
        }
    """
    try:
        from datetime import datetime, timedelta
        cutoff_time = datetime.utcnow() - timedelta(seconds=min_age_seconds)

        # Count total stale running rows
        count_rows = get_connector().query(
            "SELECT COUNT(*) as cnt FROM image_phase_status ips "
            "WHERE ips.status = ? AND ips.updated_at < ?",
            ("running", cutoff_time),
        )
        count_estimate = count_rows[0]["cnt"] if count_rows else 0

        # Fetch up to 'limit' rows with full details
        rows = get_connector().query(
            "SELECT ips.id, ips.image_id, i.file_path, pp.code, ips.status, "
            "       ips.updated_at, ips.job_id, ips.last_error, "
            "       EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - ips.updated_at)) as age_seconds "
            "FROM image_phase_status ips "
            "JOIN images i ON i.id = ips.image_id "
            "JOIN pipeline_phases pp ON pp.id = ips.phase_id "
            "WHERE ips.status = ? AND ips.updated_at < ? "
            "ORDER BY ips.updated_at ASC "
            "LIMIT ?",
            ("running", cutoff_time, limit),
        )

        result_rows = []
        for r in rows:
            result_rows.append({
                "image_id": r["image_id"],
                "image_file_path": r["file_path"],
                "phase_code": (r["code"] or "").strip(),
                "status": (r["status"] or "").strip(),
                "updated_at": r["updated_at"],
                "age_seconds": int(r["age_seconds"] or 0),
                "job_id": r["job_id"],
                "last_error": r["last_error"],
            })

        return {
            "count_estimate": count_estimate,
            "rows": result_rows,
        }
    except Exception as e:
        logger.error(f"Failed to list stale running image phase rows: {e}", exc_info=True)
        return {"count_estimate": 0, "rows": [], "error": str(e)}

def run_post_completion_data_quality_audit(job_id: int):
    """
    After terminal completion: optional dry-run of ``build_validation_repair_plan`` for the run scope,
    merge results into ``queue_payload.post_run_audit``, optionally fail the job per config.
    Returns the audit dict, or None if skipped.
    """
    # Deferred import to avoid circular dependency with modules.db monolith
    from modules.db import build_validation_repair_plan
    
    row = get_connector().query_one(
        "SELECT id, queue_payload, status FROM jobs WHERE id = ?",
        (job_id,),
    )
    if not row:
        return None
    if (row.get("status") or "").strip().lower() != "completed":
        return None

    payload = parse_queue_payload_dict(row.get("queue_payload"))
    if not should_run_post_completion_audit(payload):
        return None

    scope_paths = payload.get("scope_paths") or []
    if not scope_paths:
        ip = payload.get("input_path")
        if ip:
            scope_paths = [ip]
    if not scope_paths:
        payload["post_run_audit"] = {
            "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "status": "skipped",
            "notes": "no scope_paths or input_path in queue_payload",
        }
        update_job_payload(job_id, json.dumps(payload))
        return payload["post_run_audit"]

    stages = payload.get("target_phases")
    if stages is None:
        stages = payload.get("phases")
    if stages is not None and not isinstance(stages, list):
        stages = None

    plan = build_validation_repair_plan(scope_paths, stages, dry_run=True)
    stage_queues_full = plan.get("stage_queues") or {}
    ic = plan.get("issue_counts") or {}

    has_issues = any(int(v or 0) > 0 for v in ic.values()) or any(
        len(v or []) > 0 for v in stage_queues_full.values()
    )

    stage_queues_out = {}
    for stage, ids in stage_queues_full.items():
        sample, truncated = _cap_id_list(ids, POST_RUN_AUDIT_SAMPLE_CAP)
        stage_queues_out[str(stage)] = {
            "sample_image_ids": sample,
            "total": len(ids or []),
            "truncated": truncated,
        }

    enq = payload.get("validation_repair_summary")
    delta_vs_enqueue = None
    if isinstance(enq, dict) and enq.get("stage_queues") is not None:
        prev_sq = enq.get("stage_queues") or {}
        delta_vs_enqueue = {}
        all_stages = set(prev_sq.keys()) | set(stage_queues_full.keys())
        for stage in sorted(all_stages, key=str):
            prev_set = set(prev_sq.get(stage) or [])
            cur_set = set(stage_queues_full.get(stage) or [])
            fixed_ids = prev_set - cur_set
            new_ids = cur_set - prev_set
            fs, ftr = _cap_id_list(fixed_ids, POST_RUN_AUDIT_SAMPLE_CAP)
            ns, ntr = _cap_id_list(new_ids, POST_RUN_AUDIT_SAMPLE_CAP)
            ss, strunc = _cap_id_list(cur_set, POST_RUN_AUDIT_SAMPLE_CAP)
            delta_vs_enqueue[str(stage)] = {
                "still_remaining_count": len(cur_set),
                "still_remaining_sample": ss,
                "still_remaining_truncated": strunc,
                "fixed_count": len(fixed_ids),
                "fixed_sample": fs,
                "fixed_truncated": ftr,
                "new_since_enqueue_count": len(new_ids),
                "new_since_enqueue_sample": ns,
                "new_truncated": ntr,
            }

    post_run_audit = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "status": "issues_remaining" if has_issues else "clean",
        "severity": "warning" if has_issues else "info",
        "issue_counts": ic,
        "stage_queues": stage_queues_out,
        "delta_vs_enqueue": delta_vs_enqueue,
        "notes": (
            "Point-in-time snapshot after job completion; other jobs or edits may change rows afterward."
        ),
    }

    payload["post_run_audit"] = post_run_audit
    update_job_payload(job_id, json.dumps(payload))

    _append_job_log_line(
        job_id,
        f"Post-run data quality audit: {post_run_audit['status']} "
        f"(see queue_payload.post_run_audit).",
    )
    _maybe_fail_job_on_post_audit_issues(job_id, post_run_audit)
    return post_run_audit

def get_run_diagnostics(job_id: int) -> dict:
    """
    Aggregated troubleshooting view: persisted ``post_run_audit`` plus per-phase ``image_phase_status``
    counts for rows tagged with this ``job_id``.
    """
    jid = int(job_id)
    job = get_job(jid)
    if not job:
        return {"error": "job_not_found", "job_id": jid}

    payload = parse_queue_payload_dict(job.get("queue_payload"))
    post_audit = payload.get("post_run_audit") if isinstance(payload, dict) else None

    by_phase: dict = {}
    try:
        rows = get_connector().query(
            """
            SELECT pp.code AS phase_code, ips.status AS st, COUNT(*) AS c
            FROM image_phase_status ips
            JOIN pipeline_phases pp ON pp.id = ips.phase_id
            WHERE ips.job_id = ?
            GROUP BY pp.code, ips.status
            """,
            (jid,),
        )
        for r in rows or []:
            pc = (r.get("phase_code") or "").strip().lower()
            st = (r.get("st") or "").strip().lower()
            by_phase.setdefault(pc, {})[st] = int(r.get("c") or 0)
    except Exception as e:
        logger.exception("get_run_diagnostics: aggregate query failed (job_id=%s)", jid)
        by_phase = {"_error": str(e)}

    return {
        "job_id": jid,
        "status": job.get("status"),
        "job_type": job.get("job_type"),
        "input_path": job.get("input_path"),
        "created_at": str(job.get("created_at")),
        "post_run_audit": post_audit,
        "phase_aggregates": by_phase,
    }

def get_queued_jobs(limit=200, include_related=False):
    """Retrieve list of queued, paused, or failed jobs for queue management UI."""
    try:
        limit = int(limit)
    except (ValueError, TypeError):
        limit = 200
    if limit <= 0:
        return []
    limit = min(limit, 1000)

    rows = [dict(r) for r in get_connector().query(
        """
        SELECT
            j.*,
            p.name AS phase_name,
            ph.selected_phases,
            ph.dependency_blockers
        FROM jobs j
        LEFT JOIN pipeline_phases p ON p.id = j.phase_id
        LEFT JOIN (
            SELECT
                jp.job_id,
                LIST(jp.phase_code, ', ') AS selected_phases,
                LIST(CASE WHEN jp.state IN ('blocked', 'waiting', 'pending_dependency') THEN jp.phase_code ELSE NULL END, ', ') AS dependency_blockers
            FROM job_phases jp
            GROUP BY jp.job_id
        ) ph ON ph.job_id = j.id
        WHERE j.status IN ('queued', 'paused', 'failed')
          AND (? = 1 OR j.status = 'queued')
        ORDER BY
            CASE j.status WHEN 'queued' THEN 0 WHEN 'paused' THEN 1 ELSE 2 END,
            COALESCE(j.priority, 100) DESC,
            COALESCE(j.queue_position, j.id) ASC,
            j.enqueued_at ASC,
            j.id ASC
        FETCH FIRST ? ROWS ONLY
        """,
        (1 if include_related else 0, limit),
    )]

    avg_seconds = 120
    try:
        avg_row = get_connector().query_one(
            """
            SELECT AVG(DATEDIFF(SECOND FROM started_at TO completed_at)) AS avg_sec
            FROM jobs
            WHERE status = 'completed' AND started_at IS NOT NULL AND completed_at IS NOT NULL
            """
        )
        if avg_row and avg_row.get("avg_sec"):
            avg_seconds = max(15, int(avg_row["avg_sec"]))
    except Exception:
        pass

    queue_idx = 0
    now = datetime.datetime.now()
    for row in rows:
        if row.get("status") in ("queued", "paused"):
            queue_idx += 1
            row["queue_position"] = queue_idx
            eta = now + datetime.timedelta(seconds=(queue_idx - 1) * avg_seconds)
            row["estimated_start"] = eta.isoformat(sep=" ", timespec="seconds")
        else:
            row["queue_position"] = "-"
            row["estimated_start"] = "-"
        row["target_scope"] = row.get("target_scope") or row.get("input_path") or "-"
        row["selected_phases"] = row.get("selected_phases") or row.get("phase_name") or row.get("job_type") or "-"
        row["dependency_blockers"] = row.get("dependency_blockers") or "None"
        row["retry_count"] = int(row.get("retry_count") or 0)
        row["priority"] = int(row.get("priority") or 100)
    return rows

def bump_job_priority(job_id, delta=10):
    """Increase/decrease job priority for queued/paused jobs."""
    try:
        d = int(delta)
    except Exception:
        d = 10

    def _tx(tx):
        rowcount = tx.execute(
            """
            UPDATE jobs
            SET priority = CASE
                WHEN COALESCE(priority, 100) + ? < 1 THEN 1
                WHEN COALESCE(priority, 100) + ? > 999 THEN 999
                ELSE COALESCE(priority, 100) + ?
            END
            WHERE id = ? AND status IN ('queued', 'paused')
            """,
            (d, d, d, job_id),
        )
        return int(rowcount or 0)

    try:
        return get_connector().run_transaction(_tx)
    except Exception:
        logger.exception("bump_job_priority failed for job_id=%s", job_id)
        return 0


def reset_image_phase_status(image_ids: List[int], phase_code: str) -> int:
    """
    Bulk reset image phase status to 'not_started' for the specified images and phase.
    Returns the number of rows updated.
    """
    if not image_ids:
        return 0

    conn = get_db()
    try:
        c = conn.cursor()
        # Find phase_id
        c.execute("SELECT id FROM pipeline_phases WHERE LOWER(TRIM(code)) = ?", (phase_code.lower(),))
        row = c.fetchone()
        if not row:
            logger.warning("reset_image_phase_status: unknown phase code '%s'", phase_code)
            return 0
        phase_id = row[0]

        updated_total = 0
        chunk_size = 900
        for i in range(0, len(image_ids), chunk_size):
            chunk = image_ids[i:i + chunk_size]
            placeholders = ",".join(["?"] * len(chunk))
            sql = f"UPDATE image_phase_status SET status = 'not_started', updated_at = CURRENT_TIMESTAMP " \
                  f"WHERE phase_id = ? AND image_id IN ({placeholders})"
            params = [phase_id] + list(chunk)
            c.execute(sql, tuple(params))
            updated_total += c.rowcount

        conn.commit()
        return updated_total
    finally:
        conn.close()


def set_image_phase_status(image_id, phase_code, status,
                            app_version=None, executor_version=None,
                            job_id=None, error=None, skip_reason=None, skipped_by=None):
    """
    Upsert a row in IMAGE_PHASE_STATUS for (image_id, phase).

    Increments attempt_count on reruns (done/failed/skipped → running).
    Sets started_at on 'running', finished_at on terminal states.
    """
    from modules.phases import PhaseStatus

    phase_id = get_phase_id(phase_code)
    if phase_id is None:
        logger.warning("set_image_phase_status: unknown phase '%s'", phase_code)
        return

    now = datetime.datetime.now()

    def _tx(tx):
        # Check existing row
        existing = tx.query_one(
            "SELECT id, status, attempt_count FROM image_phase_status "
            "WHERE image_id = ? AND phase_id = ?",
            (image_id, phase_id)
        )

        if existing:
            row_id = existing["id"]
            old_status = (existing["status"] or "not_started").strip()
            attempt_count = existing["attempt_count"] or 0

            # Guard: running → running is not allowed (duplicate job protection)
            if old_status == PhaseStatus.RUNNING and status == PhaseStatus.RUNNING:
                logger.warning(
                    "set_image_phase_status: running→running guard triggered "
                    "(img=%s, phase=%s) — skipping duplicate update", image_id, phase_code
                )
                return None

            # Increment attempt on rerun transitions
            if status == PhaseStatus.RUNNING and old_status in (
                PhaseStatus.DONE, PhaseStatus.FAILED, PhaseStatus.SKIPPED
            ):
                attempt_count += 1

            # Build UPDATE
            fields = ["status = ?", "updated_at = ?", "attempt_count = ?"]
            params = [status, now, attempt_count]

            if status == PhaseStatus.RUNNING:
                fields.append("started_at = ?")
                params.append(now)
            elif status in (PhaseStatus.DONE, PhaseStatus.FAILED, PhaseStatus.SKIPPED):
                fields.append("finished_at = ?")
                params.append(now)

            if app_version is not None:
                fields.append("app_version = ?")
                params.append(app_version)
            if executor_version is not None:
                fields.append("executor_version = ?")
                params.append(executor_version)
            if job_id is not None:
                fields.append("job_id = ?")
                params.append(job_id)
            if error is not None:
                fields.append("last_error = ?")
                params.append(error)
            elif status == PhaseStatus.DONE:
                fields.append("last_error = NULL")

            if status == PhaseStatus.SKIPPED:
                fields.append("skip_reason = ?")
                params.append(skip_reason)
                fields.append("skipped_by = ?")
                params.append(skipped_by)
            elif status == PhaseStatus.RUNNING:
                fields.append("skip_reason = NULL")
                fields.append("skipped_by = NULL")

            params.append(row_id)
            tx.execute(f"UPDATE image_phase_status SET {', '.join(fields)} WHERE id = ?", params)
        else:
            # INSERT new row
            started = now if status == PhaseStatus.RUNNING else None
            finished = now if status in (PhaseStatus.DONE, PhaseStatus.FAILED, PhaseStatus.SKIPPED) else None

            tx.execute(
                "INSERT INTO image_phase_status "
                "(image_id, phase_id, status, app_version, executor_version, "
                " job_id, attempt_count, last_error, started_at, finished_at, updated_at, skip_reason, skipped_by) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (image_id, phase_id, status, app_version, executor_version,
                 job_id, 0, error, started, finished, now,
                 skip_reason if status == PhaseStatus.SKIPPED else None,
                 skipped_by if status == PhaseStatus.SKIPPED else None)
            )

        frow = tx.query_one("SELECT folder_id FROM images WHERE id = ?", (image_id,))
        return frow["folder_id"] if frow else None

    tx_ok = False
    try:
        folder_id = get_connector().run_transaction(_tx)
        tx_ok = True
    except Exception as e:
        logger.error("set_image_phase_status failed (img=%s, phase=%s): %s", image_id, phase_code, e)
        folder_id = None

    # Record pipeline event for observability (incident recording and folder invalidation
    # are handled in the monolithic db.py stubs for backward compatibility)
    phase_text = phase_code.value if hasattr(phase_code, "value") else str(phase_code)
    event_type = "progress" if status == PhaseStatus.RUNNING else "state-change"
    severity = "error" if status == PhaseStatus.FAILED else ("warning" if status == PhaseStatus.SKIPPED else "info")
    record_pipeline_event(
        "error" if status == PhaseStatus.FAILED else event_type,
        f"Image #{image_id} phase {phase_text}: {status}",
        workflow_run=job_id,
        stage_run=phase_text,
        step_run=f"image:{image_id}",
        category="phase",
        severity=severity,
        metadata={"image_id": image_id, "phase": phase_text, "status": status, "error": error, "skip_reason": skip_reason},
        critical=status == PhaseStatus.FAILED,
        noisy=True,
        source="db.set_image_phase_status",
    )


def seed_pipeline_phases():
    """
    Insert default pipeline phases into PIPELINE_PHASES table.
    Idempotent — skips existing codes.
    """
    from modules.phases import SEED_PHASES

    try:
        def _tx(tx):
            # Fix any broken rows accidentally inserted as "PhaseCode.INDEXING"
            tx.execute("UPDATE pipeline_phases SET code = REPLACE(code, 'PhaseCode.', '') WHERE code LIKE 'PhaseCode.%'")

            for phase in SEED_PHASES:
                code = phase["code"].value if hasattr(phase["code"], "value") else str(phase["code"])
                existing = tx.query_one("SELECT id FROM pipeline_phases WHERE code = ?", (code,))
                if existing is None:
                    tx.execute(
                        "INSERT INTO pipeline_phases (code, name, description, sort_order, enabled, optional, default_skip) "
                        "VALUES (?, ?, ?, ?, 1, ?, ?)",
                        (code, phase["name"], phase.get("description", ""), phase["sort_order"],
                         1 if phase.get("optional") else 0, 1 if phase.get("default_skip") else 0))
                else:
                    tx.execute(
                        "UPDATE pipeline_phases SET optional = ?, default_skip = ? WHERE code = ?",
                        (1 if phase.get("optional") else 0, 1 if phase.get("default_skip") else 0, code))

        get_connector().run_transaction(_tx)
        logger.info("Pipeline phases seeded successfully.")
    except Exception as e:
        logger.error("Failed to seed pipeline phases: %s", e)
    # Clear cache so it's rebuilt on next access
    _phase_id_cache.clear()
