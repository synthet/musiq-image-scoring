from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from typing import Any, Dict, Iterable, Optional, Sequence

from modules import db, utils
from modules.job_description import augment_queue_payload_for_audit, build_run_submit_description
from modules.phases import (
    PHASE_PREREQUISITES,
    PhaseCode,
    assert_prereqs_for_scope,
    sort_phase_value_strings,
)
from modules.run_modes import CANONICAL_RUN_MODE, resolve_run_mode_flags

logger = logging.getLogger(__name__)

DEFAULT_TARGET_PHASES: tuple[str, ...] = tuple(p.value for p in PhaseCode)
ACTIVE_JOB_STATUSES = {"pending", "queued", "running", "paused"}
ACTIVE_PHASE_STATUSES = {"queued", "running", "paused", "cancel_requested", "restarting"}
COMPLETE_PHASE_STATUSES = {"done", "skipped"}


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default


def _status(value: Any) -> str:
    return str(value or "not_started").strip().lower() or "not_started"


def _local_path(raw: str) -> str:
    path = str(raw or "").strip()
    if not path:
        return ""
    try:
        return utils.convert_path_to_local(path) or path
    except Exception:
        return path


def _path_key(raw: str) -> str:
    local = _local_path(raw)
    if not local:
        return ""
    return os.path.normpath(local).replace("\\", "/").rstrip("/").lower()


def _path_matches(path_key: str, root_key: str) -> bool:
    if not root_key:
        return True
    return path_key == root_key or path_key.startswith(root_key + "/")


def _path_intersects_active(path_key: str, active_keys: Iterable[str]) -> bool:
    for active in active_keys:
        if not active:
            continue
        if path_key == active or path_key.startswith(active + "/") or active.startswith(path_key + "/"):
            return True
    return False


def normalize_target_phases(raw: Optional[Sequence[Any]] = None) -> list[str]:
    aliases = {"score": "scoring", "tag": "keywords", "tagging": "keywords", "cluster": "culling"}
    values: list[str] = []
    allowed = {p.value for p in PhaseCode}
    for item in (raw or DEFAULT_TARGET_PHASES):
        code = aliases.get(str(item or "").strip().lower(), str(item or "").strip().lower())
        if code in allowed and code not in values:
            values.append(code)
    return sort_phase_value_strings(values)


def _default_phase_summary(code: str, total: int) -> dict[str, Any]:
    return {
        "code": code,
        "name": code.replace("_", " ").title(),
        "status": "not_started",
        "done_count": 0,
        "failed_count": 0,
        "running_count": 0,
        "queued_count": 0,
        "paused_count": 0,
        "cancel_requested_count": 0,
        "restarting_count": 0,
        "skipped_count": 0,
        "total_count": total,
        "optional": code in {"culling", "keywords", "bird_species"},
    }


def _phase_view(row: dict[str, Any], fallback_total: int) -> dict[str, Any]:
    total = _as_int(row.get("total_count") or row.get("total_images"), fallback_total)
    done = _as_int(row.get("done_count"))
    skipped = _as_int(row.get("skipped_count"))
    failed = _as_int(row.get("failed_count"))
    running = _as_int(row.get("running_count"))
    queued = _as_int(row.get("queued_count"))
    paused = _as_int(row.get("paused_count"))
    cancel_requested = _as_int(row.get("cancel_requested_count"))
    restarting = _as_int(row.get("restarting_count"))
    ready = done + skipped
    percent = round((ready / total) * 100.0, 1) if total > 0 else 0.0
    status = _status(row.get("status"))
    if status == "not_started" and total > 0 and failed > 0:
        status = "failed"
    return {
        "code": str(row.get("code") or "").strip().lower(),
        "name": row.get("name") or str(row.get("code") or "").replace("_", " ").title(),
        "status": status,
        "done": done,
        "skipped": skipped,
        "failed": failed,
        "running": running,
        "queued": queued,
        "paused": paused,
        "cancel_requested": cancel_requested,
        "restarting": restarting,
        "total": total,
        "percent": percent,
    }


def _is_complete(phase: dict[str, Any]) -> bool:
    status = _status(phase.get("status"))
    if status in COMPLETE_PHASE_STATUSES:
        return True
    total = _as_int(phase.get("total"))
    if total <= 0:
        return False
    ready = _as_int(phase.get("done")) + _as_int(phase.get("skipped"))
    return ready >= total and _as_int(phase.get("failed")) == 0


def _is_active_phase(phase: dict[str, Any]) -> bool:
    return _status(phase.get("status")) in ACTIVE_PHASE_STATUSES or any(
        _as_int(phase.get(k)) > 0 for k in ("running", "queued", "paused", "cancel_requested", "restarting")
    )


def _active_job_path_keys() -> set[str]:
    keys: set[str] = set()
    try:
        with db.connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT input_path, status FROM jobs "
                "WHERE LOWER(TRIM(status)) IN ('pending', 'queued', 'running', 'paused') "
                "AND input_path IS NOT NULL AND input_path <> ''"
            )
            for row in cur.fetchall() or []:
                try:
                    keys.add(_path_key(row[0]))
                except Exception:
                    continue
    except Exception:
        logger.debug("runs_autodrive: active job query failed", exc_info=True)
    return {k for k in keys if k}


def _parse_payload(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="replace")
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, str):
                parsed = json.loads(parsed)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _recent_auto_attempt_counts(plan_keys: Iterable[str], *, scan_limit: int = 500) -> dict[str, dict[str, Any]]:
    wanted = {k for k in plan_keys if k}
    if not wanted:
        return {}
    counts: dict[str, dict[str, Any]] = {
        key: {"attempts": 0, "last_run_id": None, "last_status": None} for key in wanted
    }
    try:
        # Include active jobs so in-flight auto-drive runs count toward max_repeats.
        rows = db.get_jobs(limit=scan_limit, offset=0)
    except Exception:
        logger.debug("runs_autodrive: recent job query failed", exc_info=True)
        return counts
    for row in rows or []:
        payload = _parse_payload(row.get("queue_payload"))
        if payload.get("tool_id") != "runs_auto_drive":
            continue
        key = str(payload.get("auto_drive_plan_key") or "")
        if key not in counts:
            continue
        counts[key]["attempts"] += 1
        if counts[key]["last_run_id"] is None:
            counts[key]["last_run_id"] = row.get("id")
            counts[key]["last_status"] = row.get("status")
    return counts


def _plan_key(folder_path: str, phase_values: Sequence[str]) -> str:
    raw = f"{_path_key(folder_path)}|{','.join(phase_values)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _first_job_type(phase_values: Sequence[str]) -> tuple[str, str]:
    first = (phase_values[0] if phase_values else "scoring").strip().lower()
    job_type_map = {
        "indexing": "indexing",
        "metadata": "metadata",
        "scoring": "scoring",
        "culling": "selection",
        "keywords": "tagging",
        "bird_species": "bird_species",
    }
    return first, job_type_map.get(first, first)


def _phase_prereq_blockers(phase_values: Sequence[str], complete: set[str]) -> dict[str, list[str]]:
    requested = set(phase_values)
    out: dict[str, list[str]] = {}
    for code in phase_values:
        missing = [pre for pre in PHASE_PREREQUISITES.get(code, ()) if pre not in complete and pre not in requested]
        if missing:
            out[code] = missing
    return out


def _build_bucket_from_summary(
    path: str,
    summary: Sequence[dict[str, Any]],
    *,
    image_count: int,
    target_phases: Sequence[str],
    active_path_keys: set[str],
) -> dict[str, Any]:
    by_code = {
        str(row.get("code") or "").strip().lower(): dict(row)
        for row in (summary or [])
        if str(row.get("code") or "").strip()
    }
    phase_rows: list[dict[str, Any]] = []
    for code in target_phases:
        row = by_code.get(code) or _default_phase_summary(code, image_count)
        phase_rows.append(_phase_view(row, image_count))

    path_key = _path_key(path)
    complete = {p["code"] for p in phase_rows if _is_complete(p)}
    active = _path_intersects_active(path_key, active_path_keys) or any(_is_active_phase(p) for p in phase_rows)

    first_needed_idx: Optional[int] = None
    current_phase: Optional[str] = None
    if not active:
        for idx, phase in enumerate(phase_rows):
            if not _is_complete(phase):
                first_needed_idx = idx
                current_phase = phase["code"]
                break
    else:
        current_phase = next((p["code"] for p in phase_rows if _is_active_phase(p)), None)

    next_phases = list(target_phases[first_needed_idx:]) if first_needed_idx is not None else []
    blockers = _phase_prereq_blockers(next_phases, complete) if next_phases else {}
    if active:
        bucket = "in_flight"
    elif blockers:
        bucket = "blocked"
    elif next_phases:
        bucket = f"awaiting_{next_phases[0]}"
    else:
        bucket = "complete"

    total_work = sum(_as_int(p.get("total")) for p in phase_rows)
    ready_work = sum(_as_int(p.get("done")) + _as_int(p.get("skipped")) for p in phase_rows)
    overall_percent = round((ready_work / total_work) * 100.0, 1) if total_work > 0 else 0.0
    plan_key = _plan_key(path, next_phases) if next_phases else None

    return {
        "path": path,
        "path_key": path_key,
        "image_count": image_count,
        "bucket": bucket,
        "current_phase": current_phase,
        "next_phases": next_phases,
        "blocked_by": blockers,
        "overall_percent": overall_percent,
        "phase_statuses": phase_rows,
        "plan_key": plan_key,
    }


def build_folder_buckets(
    *,
    root_path: Optional[str] = None,
    q: Optional[str] = None,
    bucket: Optional[str] = None,
    limit: int = 25,
    offset: int = 0,
    include_complete: bool = False,
    target_phases: Optional[Sequence[Any]] = None,
    folder_paths: Optional[Sequence[str]] = None,
) -> dict[str, Any]:
    limit = max(1, min(_as_int(limit, 25), 500))
    offset = max(0, _as_int(offset, 0))
    target = normalize_target_phases(target_phases)
    root_key = _path_key(root_path or "")
    q_norm = str(q or "").strip().lower()
    bucket_filter = str(bucket or "").strip().lower()
    explicit_path_keys = {_path_key(p) for p in (folder_paths or []) if _path_key(p)}

    direct_counts = db.get_folder_direct_image_counts_by_local_path_norm()
    summaries = db.get_all_folder_phase_summaries_bulk()
    active_keys = _active_job_path_keys()

    rows: list[dict[str, Any]] = []
    for raw_path, meta in direct_counts.items():
        path = _local_path(raw_path)
        path_key = _path_key(path)
        if not path_key:
            continue
        if explicit_path_keys and path_key not in explicit_path_keys:
            continue
        if root_key and not _path_matches(path_key, root_key):
            continue
        if q_norm and q_norm not in path_key:
            continue
        image_count = _as_int((meta or {}).get("direct_count"))
        if image_count <= 0:
            continue
        summary = (
            summaries.get(os.path.normpath(path))
            or summaries.get(os.path.normpath(raw_path))
            or summaries.get(path)
            or summaries.get(raw_path)
            or []
        )
        item = _build_bucket_from_summary(
            path,
            summary,
            image_count=image_count,
            target_phases=target,
            active_path_keys=active_keys,
        )
        if not include_complete and item["bucket"] == "complete":
            continue
        if bucket_filter and bucket_filter != "all" and item["bucket"] != bucket_filter:
            continue
        rows.append(item)

    phase_order = {code: i for i, code in enumerate(target)}
    bucket_order = {"blocked": -1, "in_flight": 99, "complete": 100}

    def _sort_key(item: dict[str, Any]):
        b = item["bucket"]
        phase = item.get("current_phase") or (item.get("next_phases") or [""])[0]
        return (
            bucket_order.get(b, phase_order.get(phase, 50)),
            -_as_int(item.get("image_count")),
            item.get("path_key") or "",
        )

    rows.sort(key=_sort_key)

    bucket_counts: dict[str, int] = {}
    phase_counts: dict[str, int] = {}
    for item in rows:
        bucket_counts[item["bucket"]] = bucket_counts.get(item["bucket"], 0) + 1
        phase = item.get("current_phase")
        if phase:
            phase_counts[phase] = phase_counts.get(phase, 0) + 1

    page = rows[offset: offset + limit]
    for item in page:
        item.pop("path_key", None)

    return {
        "items": page,
        "total": len(rows),
        "limit": limit,
        "offset": offset,
        "bucket_counts": bucket_counts,
        "phase_counts": phase_counts,
        "target_phases": target,
    }


def _enqueue_auto_bucket(
    bucket: dict[str, Any],
    *,
    generate_captions: bool,
) -> tuple[Optional[int], Optional[int], Optional[dict[str, Any]]]:
    raw_path = str(bucket.get("path") or "")
    resolved, _candidates = utils.resolve_scope_input_path(raw_path)
    if not resolved or not os.path.isdir(resolved):
        return None, None, {"reason": "missing_on_disk", "folder_path": raw_path}

    phase_values = sort_phase_value_strings([str(p) for p in bucket.get("next_phases") or []])
    if not phase_values:
        return None, None, {"reason": "nothing_to_queue", "folder_path": raw_path}

    missing = assert_prereqs_for_scope(phase_values, [resolved])
    if missing:
        return None, None, {"reason": "missing_prerequisites", "folder_path": resolved, "missing": missing}

    mode_flags = resolve_run_mode_flags(CANONICAL_RUN_MODE)
    payload: dict[str, Any] = {
        "scope_type": "folder_recursive",
        "scope_paths": [resolved],
        "input_path": resolved,
        "run_mode": CANONICAL_RUN_MODE,
        "skip_done": mode_flags["skip_done"],
        "skip_existing": mode_flags["skip_existing"],
        "force_rerun": mode_flags["force_rerun"],
        "fix_incomplete_stages": mode_flags["fix_incomplete_stages"],
        "overwrite": mode_flags["overwrite"],
        "force_rescan": mode_flags["force_rescan"],
        "phases": phase_values,
        "target_phases": phase_values,
        "generate_captions": bool(generate_captions),
    }
    payload = augment_queue_payload_for_audit(payload, trigger="api", tool_id="runs_auto_drive")
    payload["auto_drive_plan_key"] = _plan_key(resolved, phase_values)
    payload["auto_drive_bucket"] = bucket.get("bucket")
    payload["auto_drive_overall_percent"] = bucket.get("overall_percent")

    repair_plan = db.build_validation_repair_plan([resolved], phase_values, False)
    payload["repair_plan_summary"] = repair_plan
    payload["resolved_image_ids_by_stage"] = repair_plan.get("stage_queues", {})
    first_ids = (repair_plan.get("stage_queues", {}) or {}).get(phase_values[0])
    if isinstance(first_ids, list):
        payload["resolved_image_ids"] = first_ids
    payload["skip_existing"] = False
    payload["post_run_audit"] = True

    first_phase, job_type = _first_job_type(phase_values)
    description = build_run_submit_description(
        scope_type="folder_recursive",
        scope_paths=[resolved],
        run_mode=CANONICAL_RUN_MODE,
        phase_values=phase_values,
        client_description="Auto-drive queued this folder from the Runs buckets planner.",
    )
    job_id, pos = db.enqueue_job_with_phases(
        resolved,
        first_phase,
        job_type,
        payload,
        description,
        phase_codes=phase_values,
        first_phase_state="queued",
    )
    return job_id, pos, None


def auto_drive_runs(
    *,
    root_path: Optional[str] = None,
    folder_paths: Optional[Sequence[str]] = None,
    limit: int = 50,
    dry_run: bool = False,
    target_phases: Optional[Sequence[Any]] = None,
    max_repeats: int = 2,
    generate_captions: bool = True,
) -> dict[str, Any]:
    limit = max(1, min(_as_int(limit, 50), 500))
    max_repeats = max(1, min(_as_int(max_repeats, 2), 20))
    resolve_run_mode_flags(CANONICAL_RUN_MODE)

    planned = build_folder_buckets(
        root_path=root_path,
        limit=limit,
        offset=0,
        include_complete=False,
        target_phases=target_phases,
        folder_paths=folder_paths,
    )
    candidates = [
        item for item in planned["items"]
        if item.get("next_phases") and item.get("bucket") not in {"blocked", "in_flight", "complete"}
    ][:limit]
    attempts = _recent_auto_attempt_counts([str(c.get("plan_key") or "") for c in candidates])

    scheduled: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    loop_detected = 0

    for item in candidates:
        plan_key = str(item.get("plan_key") or "")
        attempt_meta = attempts.get(plan_key) or {}
        if _as_int(attempt_meta.get("attempts")) >= max_repeats:
            loop_detected += 1
            skipped.append({
                "folder_path": item.get("path"),
                "phases": item.get("next_phases") or [],
                "reason": "loop_detected",
                "attempts": attempt_meta.get("attempts"),
                "last_run_id": attempt_meta.get("last_run_id"),
                "last_status": attempt_meta.get("last_status"),
            })
            continue
        if dry_run:
            scheduled.append({
                "folder_path": item.get("path"),
                "phases": item.get("next_phases") or [],
                "bucket": item.get("bucket"),
                "plan_key": plan_key,
                "dry_run": True,
            })
            continue
        try:
            job_id, position, skip = _enqueue_auto_bucket(
                item,
                generate_captions=generate_captions,
            )
            if skip:
                skipped.append({**skip, "phases": item.get("next_phases") or []})
                continue
            if not job_id:
                skipped.append({
                    "folder_path": item.get("path"),
                    "phases": item.get("next_phases") or [],
                    "reason": "enqueue_failed",
                })
                continue
            scheduled.append({
                "folder_path": item.get("path"),
                "phases": item.get("next_phases") or [],
                "bucket": item.get("bucket"),
                "plan_key": plan_key,
                "job_id": job_id,
                "queue_position": position,
            })
        except Exception as exc:
            logger.exception("runs_autodrive: failed to queue %s", item.get("path"))
            skipped.append({
                "folder_path": item.get("path"),
                "phases": item.get("next_phases") or [],
                "reason": "exception",
                "error": str(exc),
            })

    bucket_counts = planned.get("bucket_counts", {})
    return {
        "dry_run": bool(dry_run),
        "run_mode": CANONICAL_RUN_MODE,
        "limit": limit,
        "scheduled": scheduled,
        "skipped": skipped,
        "candidates": len(candidates),
        "total_outstanding": planned["total"],
        "loop_detected": loop_detected,
        "bucket_counts": bucket_counts,
        "phase_counts": planned.get("phase_counts", {}),
        "health": _bucket_health_from_counts(bucket_counts),
    }


# ---------------------------------------------------------------------------
# Durable server-side drive loop
# ---------------------------------------------------------------------------
# A user starts a "Drive to Complete" via the API; the JobDispatcher then calls
# ``drive_tick`` on every idle tick to top up the queue with the next batch of
# folder runs until nothing is outstanding (or the work stalls / hits the loop
# guard). State lives in-process: a backend restart stops an in-flight drive.

DRIVE_TICK_COOLDOWN_SEC = 15.0
DRIVE_MAX_NOPROGRESS_TICKS = 3

_DRIVE_LOCK = threading.RLock()
# Non-blocking guard so the dispatcher tick and the API "start" call never run
# two ``auto_drive_runs`` batches concurrently (which could double-enqueue).
_DRIVE_BATCH_LOCK = threading.Lock()
_DRIVE_STATE: Dict[str, Any] = {
    "enabled": False,
    "root_path": None,
    "limit": 50,
    "max_repeats": 2,
    "generate_captions": True,
    "target_phases": None,  # None => full pipeline (includes bird_species)
    "started_at": None,
    "last_tick_at": 0.0,
    "last_result": None,
    "stop_reason": None,
    "idle_no_progress_ticks": 0,
}


def _config_server_loop_enabled() -> bool:
    """Kill switch: ``auto_drive.server_loop_enabled`` (default True)."""
    try:
        from modules.config import get_config_value

        return bool(get_config_value("auto_drive.server_loop_enabled", default=True))
    except Exception:
        return True


def get_drive_state() -> Dict[str, Any]:
    with _DRIVE_LOCK:
        return dict(_DRIVE_STATE)


def _broadcast_drive(event_type: str, extra: Optional[Dict[str, Any]] = None) -> None:
    try:
        from modules.events import event_manager

        payload: Dict[str, Any] = {"drive": get_drive_state()}
        if extra:
            payload.update(extra)
        event_manager.broadcast_threadsafe(event_type, payload)
    except Exception:
        logger.debug("runs_autodrive: broadcast %s failed", event_type, exc_info=True)


def _bucket_health_from_counts(bucket_counts: Dict[str, Any]) -> Dict[str, int]:
    """Derive folder health counters from planner bucket_counts."""
    in_flight = _as_int((bucket_counts or {}).get("in_flight"))
    blocked = _as_int((bucket_counts or {}).get("blocked"))
    schedulable = sum(
        _as_int(v)
        for k, v in (bucket_counts or {}).items()
        if k not in {"blocked", "in_flight", "complete"}
    )
    return {
        "in_flight_folders": in_flight,
        "blocked_folders": blocked,
        "schedulable_folders": schedulable,
    }


def _classify_drive_tick(
    *,
    outstanding: int,
    scheduled_n: int,
    candidates_n: int,
    health: Dict[str, int],
) -> tuple[Optional[str], str]:
    """Return (stop_reason or None, last_tick_reason)."""
    if outstanding <= 0:
        return "complete", "complete"
    if scheduled_n > 0:
        return None, "queued"
    in_flight = _as_int(health.get("in_flight_folders"))
    blocked = _as_int(health.get("blocked_folders"))
    schedulable = _as_int(health.get("schedulable_folders"))
    if in_flight > 0 and candidates_n == 0:
        return None, "waiting_in_flight"
    if blocked > 0 and schedulable == 0 and in_flight == 0:
        return "blocked", "blocked"
    if candidates_n > 0:
        return None, "no_enqueue_progress"
    return None, "idle"


def _summarize_result(result: Dict[str, Any], *, last_tick_reason: str = "") -> Dict[str, Any]:
    bucket_counts = result.get("bucket_counts", {}) or {}
    health = result.get("health") or _bucket_health_from_counts(bucket_counts)
    summary: Dict[str, Any] = {
        "scheduled": len(result.get("scheduled", []) or []),
        "skipped": len(result.get("skipped", []) or []),
        "candidates": _as_int(result.get("candidates")),
        "total_outstanding": _as_int(result.get("total_outstanding")),
        "loop_detected": _as_int(result.get("loop_detected")),
        "bucket_counts": bucket_counts,
        "health": health,
    }
    if last_tick_reason:
        summary["last_tick_reason"] = last_tick_reason
    return summary


def start_drive(
    *,
    root_path: Optional[str] = None,
    limit: int = 50,
    target_phases: Optional[Sequence[Any]] = None,
    generate_captions: bool = True,
    max_repeats: int = 2,
) -> Dict[str, Any]:
    """Enable the durable drive and immediately schedule the first batch."""
    with _DRIVE_LOCK:
        _DRIVE_STATE.update(
            {
                "enabled": True,
                "root_path": (str(root_path).strip() or None) if root_path else None,
                "limit": max(1, min(_as_int(limit, 50), 500)),
                "max_repeats": max(1, min(_as_int(max_repeats, 2), 20)),
                "generate_captions": bool(generate_captions),
                "target_phases": list(target_phases) if target_phases else None,
                "started_at": time.time(),
                "last_tick_at": 0.0,
                "last_result": None,
                "stop_reason": None,
                "idle_no_progress_ticks": 0,
            }
        )
    logger.info("runs_autodrive: drive started (root_path=%s)", get_drive_state().get("root_path"))
    _broadcast_drive("drive_started")
    result = _run_drive_batch(force=True)
    return {"state": get_drive_state(), "result": result}


def stop_drive(reason: str = "manual") -> Dict[str, Any]:
    with _DRIVE_LOCK:
        was_enabled = bool(_DRIVE_STATE["enabled"])
        _DRIVE_STATE["enabled"] = False
        _DRIVE_STATE["stop_reason"] = reason
    if was_enabled:
        logger.info("runs_autodrive: drive stopped (reason=%s)", reason)
        _broadcast_drive("drive_stopped", {"reason": reason})
    return get_drive_state()


def _run_drive_batch(*, force: bool = False) -> Optional[Dict[str, Any]]:
    """Run one ``auto_drive_runs`` batch if due. Returns a summary or ``None``.

    ``force`` bypasses the cooldown (used by ``start_drive`` for an immediate
    first batch). A non-blocking batch lock ensures only one batch runs at a
    time across the dispatcher thread and API threads.
    """
    if not _DRIVE_BATCH_LOCK.acquire(blocking=False):
        return None
    try:
        with _DRIVE_LOCK:
            if not _DRIVE_STATE["enabled"]:
                return None
            now = time.time()
            if not force and (now - float(_DRIVE_STATE["last_tick_at"])) < DRIVE_TICK_COOLDOWN_SEC:
                return None
            _DRIVE_STATE["last_tick_at"] = now
            params = {
                "root_path": _DRIVE_STATE["root_path"],
                "limit": _DRIVE_STATE["limit"],
                "max_repeats": _DRIVE_STATE["max_repeats"],
                "generate_captions": _DRIVE_STATE["generate_captions"],
                "target_phases": _DRIVE_STATE["target_phases"],
            }

        try:
            result = auto_drive_runs(dry_run=False, **params)
        except Exception:
            logger.exception("runs_autodrive: drive batch failed")
            return None

        health = result.get("health") or _bucket_health_from_counts(result.get("bucket_counts", {}))
        outstanding = _as_int(result.get("total_outstanding"))
        scheduled_n = len(result.get("scheduled", []) or [])
        candidates_n = _as_int(result.get("candidates"))
        immediate_stop, tick_reason = _classify_drive_tick(
            outstanding=outstanding,
            scheduled_n=scheduled_n,
            candidates_n=candidates_n,
            health=health,
        )
        summary = _summarize_result(result, last_tick_reason=tick_reason)

        stop_reason: Optional[str] = None
        with _DRIVE_LOCK:
            _DRIVE_STATE["last_result"] = summary
            if immediate_stop == "complete":
                _DRIVE_STATE["idle_no_progress_ticks"] = 0
                stop_reason = "complete"
            elif immediate_stop == "blocked":
                _DRIVE_STATE["idle_no_progress_ticks"] = 0
                stop_reason = "blocked"
            elif tick_reason in {"waiting_in_flight", "queued"}:
                _DRIVE_STATE["idle_no_progress_ticks"] = 0
            elif tick_reason == "no_enqueue_progress":
                _DRIVE_STATE["idle_no_progress_ticks"] += 1
                if _DRIVE_STATE["idle_no_progress_ticks"] >= DRIVE_MAX_NOPROGRESS_TICKS:
                    stop_reason = "stalled"
            else:
                _DRIVE_STATE["idle_no_progress_ticks"] += 1
                if _DRIVE_STATE["idle_no_progress_ticks"] >= DRIVE_MAX_NOPROGRESS_TICKS:
                    stop_reason = "stalled"

        logger.debug(
            "runs_autodrive: drive tick reason=%s outstanding=%s scheduled=%s health=%s",
            tick_reason,
            outstanding,
            scheduled_n,
            health,
        )
    finally:
        _DRIVE_BATCH_LOCK.release()

    if stop_reason:
        logger.info(
            "runs_autodrive: drive stopping reason=%s summary=%s",
            stop_reason,
            summary,
        )
        stop_drive(stop_reason)
    else:
        _broadcast_drive("drive_progress")
    return summary


def drive_tick() -> Optional[Dict[str, Any]]:
    """Cheap no-op unless a drive is active. Called from the JobDispatcher idle path."""
    with _DRIVE_LOCK:
        if not _DRIVE_STATE["enabled"]:
            return None
    if not _config_server_loop_enabled():
        return None
    return _run_drive_batch(force=False)


def get_drive_status_with_outstanding() -> Dict[str, Any]:
    """Drive state plus a light snapshot of outstanding work for the UI."""
    state = get_drive_state()
    try:
        # ``build_folder_buckets`` computes totals/bucket_counts over all rows
        # before paginating, so limit=1 is enough for the summary.
        planned = build_folder_buckets(
            root_path=state.get("root_path"),
            limit=1,
            include_complete=False,
            target_phases=state.get("target_phases"),
        )
        bucket_counts = planned.get("bucket_counts", {})
        outstanding = {
            "total_outstanding": planned.get("total", 0),
            "bucket_counts": bucket_counts,
            "phase_counts": planned.get("phase_counts", {}),
            "health": _bucket_health_from_counts(bucket_counts),
        }
    except Exception:
        logger.debug("runs_autodrive: outstanding snapshot failed", exc_info=True)
        outstanding = {
            "total_outstanding": None,
            "bucket_counts": {},
            "phase_counts": {},
            "health": _bucket_health_from_counts({}),
        }
    return {"state": state, "outstanding": outstanding}


def _recent_auto_drive_jobs(*, scan_limit: int = 20) -> list[dict[str, Any]]:
    """Recent jobs queued by auto-drive (active + terminal)."""
    out: list[dict[str, Any]] = []
    try:
        rows = db.get_jobs(limit=scan_limit, offset=0)
    except Exception:
        logger.debug("runs_autodrive: recent auto-drive job query failed", exc_info=True)
        return out
    for row in rows or []:
        payload = _parse_payload(row.get("queue_payload"))
        if payload.get("tool_id") != "runs_auto_drive":
            continue
        out.append({
            "job_id": row.get("id"),
            "status": row.get("status"),
            "input_path": row.get("input_path"),
            "plan_key": payload.get("auto_drive_plan_key"),
            "bucket": payload.get("auto_drive_bucket"),
            "phases": payload.get("target_phases") or payload.get("phases"),
        })
    return out


def _active_auto_drive_plan_key_duplicates(jobs: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Active auto-drive jobs sharing the same plan_key."""
    active_statuses = ACTIVE_JOB_STATUSES
    by_key: dict[str, list[dict[str, Any]]] = {}
    for job in jobs:
        status = _status(job.get("status"))
        if status not in active_statuses:
            continue
        key = str(job.get("plan_key") or "")
        if not key:
            continue
        by_key.setdefault(key, []).append(job)
    duplicates: list[dict[str, Any]] = []
    for key, group in by_key.items():
        if len(group) > 1:
            duplicates.append({
                "plan_key": key,
                "job_ids": [j.get("job_id") for j in group],
                "count": len(group),
            })
    return duplicates


def get_drive_diagnostics() -> Dict[str, Any]:
    """Drive status, health, recent auto-drive jobs, and anomaly hints for MCP/CLI."""
    status = get_drive_status_with_outstanding()
    recent_jobs = _recent_auto_drive_jobs(scan_limit=50)
    duplicates = _active_auto_drive_plan_key_duplicates(recent_jobs)
    state = status.get("state") or {}
    last_result = state.get("last_result") or {}
    health = last_result.get("health") or status.get("outstanding", {}).get("health") or {}
    loop_detected = _as_int(last_result.get("loop_detected"))
    stop_reason = state.get("stop_reason")
    schedulable = _as_int(health.get("schedulable_folders"))
    anomalies: list[dict[str, Any]] = []
    if loop_detected > 0:
        anomalies.append({
            "code": "loop_detected",
            "message": f"Last tick skipped {loop_detected} repeated folder plan(s).",
            "severity": "warning",
        })
    if duplicates:
        anomalies.append({
            "code": "duplicate_active_plan_keys",
            "message": f"{len(duplicates)} plan key(s) have multiple active auto-drive jobs.",
            "severity": "error",
            "details": duplicates,
        })
    if stop_reason == "stalled" and schedulable > 0:
        anomalies.append({
            "code": "stalled_with_schedulable_work",
            "message": "Drive stopped as stalled but schedulable folders remain.",
            "severity": "error",
            "schedulable_folders": schedulable,
        })
    return {
        "status": status,
        "recent_auto_drive_jobs": recent_jobs[:20],
        "duplicate_active_plan_keys": duplicates,
        "anomalies": anomalies,
        "healthy": len(anomalies) == 0,
    }
