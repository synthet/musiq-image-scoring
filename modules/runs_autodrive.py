from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any, Dict, Iterable, List, Optional, Sequence

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
        rows = db.get_jobs(limit=scan_limit, offset=0, history_only=True)
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
        limit=200,
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

    return {
        "dry_run": bool(dry_run),
        "run_mode": CANONICAL_RUN_MODE,
        "limit": limit,
        "scheduled": scheduled,
        "skipped": skipped,
        "candidates": len(candidates),
        "total_outstanding": planned["total"],
        "loop_detected": loop_detected,
        "bucket_counts": planned.get("bucket_counts", {}),
        "phase_counts": planned.get("phase_counts", {}),
    }
