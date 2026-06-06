from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
import threading
import time
from collections import Counter
from typing import Any, Dict, Iterable, Optional, Sequence

from modules import db, utils
from modules.job_description import augment_queue_payload_for_audit, build_run_submit_description
from modules.run_manifest import (
    REASON_SOURCE_AUTO_DRIVE,
    attach_run_reason,
    build_auto_drive_summary,
)
from modules.phases import (
    PHASE_PREREQUISITES,
    PhaseCode,
    assert_prereqs_for_scope,
    sort_phase_value_strings,
)
from modules.run_modes import CANONICAL_RUN_MODE, resolve_run_mode_flags

logger = logging.getLogger(__name__)

_LOG_SCHEDULED_CAP = 15


def _format_skip_summary(skipped: Sequence[dict[str, Any]]) -> str:
    counts = Counter(str(item.get("reason") or "unknown") for item in skipped)
    return ", ".join(f"{reason}={count}" for reason, count in sorted(counts.items()))


def _log_scheduled_runs(scheduled: Sequence[dict[str, Any]]) -> None:
    if not scheduled:
        return
    logger.info("runs_autodrive: queued %d folder run(s)", len(scheduled))
    for entry in scheduled[:_LOG_SCHEDULED_CAP]:
        phases = entry.get("phases") or []
        phase_label = ",".join(str(p) for p in phases) if phases else "?"
        logger.info(
            "runs_autodrive:   job %s — %s [%s] phases=%s",
            entry.get("job_id"),
            entry.get("folder_path"),
            entry.get("bucket"),
            phase_label,
        )
    overflow = len(scheduled) - _LOG_SCHEDULED_CAP
    if overflow > 0:
        logger.info("runs_autodrive:   … and %d more queued folder(s)", overflow)


def _log_drive_tick_result(
    *,
    tick_reason: str,
    summary: Dict[str, Any],
    stop_reason: Optional[str] = None,
) -> None:
    health = summary.get("health") or {}
    msg = (
        "runs_autodrive: drive tick reason=%s outstanding=%s scheduled=%s skipped=%s "
        "candidates=%s in_flight=%s schedulable=%s blocked=%s idle_no_progress=%s"
    )
    args: list[Any] = [
        tick_reason,
        summary.get("total_outstanding"),
        summary.get("scheduled"),
        summary.get("skipped"),
        summary.get("candidates"),
        health.get("in_flight_folders"),
        health.get("schedulable_folders"),
        health.get("blocked_folders"),
        get_drive_state().get("idle_no_progress_ticks"),
    ]
    if stop_reason:
        msg += " stop=%s"
        args.append(stop_reason)
    logger.info(msg, *args)


DEFAULT_TARGET_PHASES: tuple[str, ...] = tuple(p.value for p in PhaseCode)
ACTIVE_JOB_STATUSES = {"pending", "queued", "running", "paused"}
ACTIVE_PHASE_STATUSES = {"queued", "running", "paused", "cancel_requested", "restarting"}
COMPLETE_PHASE_STATUSES = {"done", "skipped"}
# Terminal failures count toward loop guard; completed runs are forgiven only when the folder
# made measurable progress since the last completed run (see _recent_auto_attempt_counts).
_LOOP_GUARD_TERMINAL_STATUSES = frozenset({
    "failed",
    "canceled",
    "cancelled",
    "interrupted",
})
# Completed auto-drive job statuses — re-queued only when progress advanced, otherwise they
# count toward max_repeats so a stuck folder cannot be enqueued forever.
_LOOP_GUARD_COMPLETED_STATUSES = frozenset({"completed", "done", "success", "succeeded"})
# Minimum overall_percent gain (0–100 scale) that counts as "the folder advanced" between passes.
_PROGRESS_EPS = 0.0
AUTODRIVE_CANDIDATE_SCAN_CAP = 500
BIRD_BACKLOG_QUOTA_THRESHOLD = 50


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


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
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
        if path_key == active or path_key.startswith(active + "/"):
            return True
    return False


def _is_leaf_folder_for_autodrive(path_key: str, all_path_keys: Iterable[str]) -> bool:
    if not path_key:
        return False
    for other in all_path_keys:
        if other and other != path_key and other.startswith(path_key + "/"):
            return False
    return True


def _subtree_total_from_summary(summary: Sequence[dict[str, Any]]) -> int:
    totals = [_as_int(row.get("total_count")) for row in (summary or [])]
    return max(totals) if totals else 0


def _reconcile_stale_ips_for_drive() -> None:
    try:
        db.reconcile_stale_running_phases_for_terminal_jobs(limit=500)
    except Exception:
        logger.debug("runs_autodrive: reconcile terminal job IPS failed", exc_info=True)
    try:
        db.reconcile_stale_running_image_phases(limit=500)
    except Exception:
        logger.debug("runs_autodrive: reconcile stale running IPS failed", exc_info=True)
    # Phantom-complete reconcile: images already scored / tagged whose IPS row never
    # advanced to ``done`` make a folder look ``awaiting_scoring`` / ``awaiting_keywords``
    # while the planner correctly finds no work → nothing_to_queue / loop_detected churn.
    # Marking them done lets the drive reach genuinely-incomplete folders.
    try:
        db.reconcile_phantom_complete_image_phases(("scoring", "keywords"), limit=5000)
    except Exception:
        logger.debug("runs_autodrive: reconcile phantom-complete IPS failed", exc_info=True)


AUTODRIVE_DIRTY_REFRESH_LIMIT = 100
# Default for GET /runs/folder-buckets so dirty aggregates refresh instead of synthetic not_started.
FOLDER_BUCKETS_DIRTY_REFRESH_DEFAULT = AUTODRIVE_DIRTY_REFRESH_LIMIT

_DEFAULT_NEW_FOLDER_DAYS = 7


def _autodrive_prioritize_new_folders() -> bool:
    try:
        from modules.config import get_config_value

        return bool(get_config_value("auto_drive.prioritize_new_folders", default=True))
    except Exception:
        return True


def _autodrive_new_folder_days() -> int:
    try:
        from modules.config import get_config_value

        return max(1, _as_int(get_config_value("auto_drive.new_folder_days", default=_DEFAULT_NEW_FOLDER_DAYS), _DEFAULT_NEW_FOLDER_DAYS))
    except Exception:
        return _DEFAULT_NEW_FOLDER_DAYS


def _new_folder_cutoff_ts(*, days: Optional[int] = None) -> float:
    window = _autodrive_new_folder_days() if days is None else max(1, int(days))
    cutoff = datetime.datetime.now() - datetime.timedelta(days=window)
    return cutoff.timestamp()


def _folder_created_at_sort_ts(created_at: Any) -> float:
    if created_at is None:
        return 0.0
    if isinstance(created_at, (int, float)):
        return float(created_at)
    if isinstance(created_at, datetime.datetime):
        dt = created_at
        if dt.tzinfo is None:
            return dt.timestamp()
        return dt.timestamp()
    raw = str(created_at).strip()
    if not raw:
        return 0.0
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.datetime.fromisoformat(raw)
        return dt.timestamp()
    except ValueError:
        return 0.0


def _format_folder_created_at(created_at: Any) -> Optional[str]:
    if created_at is None:
        return None
    if isinstance(created_at, datetime.datetime):
        return created_at.isoformat()
    raw = str(created_at).strip()
    return raw or None


def _is_newly_imported_folder(created_at: Any, *, cutoff_ts: float) -> bool:
    ts = _folder_created_at_sort_ts(created_at)
    if ts <= 0:
        return False
    return ts >= cutoff_ts


def _folder_bucket_sort_key(
    item: dict[str, Any],
    *,
    phase_order: dict[str, int],
    bucket_order: dict[str, int],
    prioritize_new: bool,
    new_cutoff_ts: float,
) -> tuple:
    b = str(item.get("bucket") or "")
    path_key = item.get("path_key") or ""
    if b == "blocked":
        return (-1, 0, 0, 0, 0, path_key)
    if b in bucket_order:
        return (bucket_order[b], 0, 0, 0, 0, path_key)

    phase = item.get("current_phase") or (item.get("next_phases") or [""])[0]
    if prioritize_new and item.get("is_newly_imported"):
        ts = _folder_created_at_sort_ts(item.get("folder_created_at"))
        return (
            0,
            -ts,
            float(item.get("overall_percent") or 0),
            _as_int(item.get("image_count")),
            0,
            path_key,
        )
    return (
        1,
        phase_order.get(phase, 50),
        -_as_int(item.get("image_count")),
        0,
        0,
        path_key,
    )

# ``clustering`` is a legacy alias queue key; culling is canonical in target_phases.
_REPAIR_PLAN_QUEUE_SKIP = frozenset({"clustering"})


def normalize_target_phases(raw: Optional[Sequence[Any]] = None) -> list[str]:
    aliases = {"score": "scoring", "tag": "keywords", "tagging": "keywords", "cluster": "culling"}
    values: list[str] = []
    allowed = {p.value for p in PhaseCode}
    for item in (raw or DEFAULT_TARGET_PHASES):
        code = aliases.get(str(item or "").strip().lower(), str(item or "").strip().lower())
        if code in allowed and code not in values:
            values.append(code)
    return sort_phase_value_strings(values)


def phases_with_work_from_repair_plan(
    scope_paths: Sequence[str],
    stage_codes: Sequence[str],
    *,
    dry_run: bool = True,
    include_stale_executor: bool = False,
) -> list[str]:
    """Return target phases with real unfinished work, not executor-version-only drift."""
    paths = [str(p) for p in scope_paths if str(p or "").strip()]
    stages = sort_phase_value_strings([str(s) for s in stage_codes if str(s or "").strip()])
    if not paths or not stages:
        return []
    repair = db.build_validation_repair_plan(
        paths,
        stages,
        dry_run,
        include_stale_executor=include_stale_executor,
    )
    queues = repair.get("stage_queues") or {}
    out: list[str] = []
    for code in stages:
        if code in _REPAIR_PLAN_QUEUE_SKIP:
            continue
        ids = queues.get(code)
        if isinstance(ids, list) and len(ids) > 0:
            out.append(code)
    return out


def resolve_auto_drive_enqueue_phases(
    resolved: str,
    phase_candidates: Sequence[str],
    *,
    dry_run: bool = True,
) -> list[str]:
    """Return phases for an auto-drive job: prefix through last stage with repair-plan work.

    ``phases_with_work_from_repair_plan`` lists only stages with non-empty queues.
    Downstream stages (e.g. scoring) still require earlier stages (metadata) to appear
    in the same submission for ``assert_prereqs_for_scope`` — include the contiguous
    pipeline prefix from the bucket's first candidate through the last stage with work.
    """
    candidates = sort_phase_value_strings([str(p) for p in phase_candidates if str(p or "").strip()])
    if not candidates:
        return []
    repair_phases = phases_with_work_from_repair_plan(
        [resolved],
        candidates,
        dry_run=dry_run,
        include_stale_executor=False,
    )
    if not repair_phases:
        return []
    indices = [candidates.index(p) for p in repair_phases if p in candidates]
    if not indices:
        return sort_phase_value_strings(list(repair_phases))
    return candidates[: max(indices) + 1]


PLANNER_PREVIEW_BUDGET_SEC = 5.0
# Hard wall-clock cap on per-row planner previews so a slow ``build_validation_repair_plan``
# can't turn ``/api/runs/folder-buckets`` into a 90-second hang. Items past the budget get
# ``planner_next_phases: []`` and a ``planner_preview_skipped`` flag so the UI can show
# "preview unavailable" instead of pretending there's no work.


def _attach_planner_preview_to_bucket_items(
    items: list[dict[str, Any]],
    *,
    target_phases: Sequence[str],
    planner_preview_limit: int,
    budget_sec: float = PLANNER_PREVIEW_BUDGET_SEC,
    max_images: int = 500,
) -> None:
    """Populate ``planner_next_phases`` on bucket rows (JIT dry-run, auto-drive rules)."""
    preview_cap = max(0, _as_int(planner_preview_limit, 0))
    image_cap = max(0, _as_int(max_images, 0))
    deadline = time.monotonic() + max(0.0, float(budget_sec)) if budget_sec else None
    budget_exhausted = False
    for idx, item in enumerate(items):
        item["planner_next_phases"] = []
        if idx >= preview_cap:
            continue
        if item.get("bucket") in ("blocked", "complete"):
            continue
        if image_cap and _as_int(item.get("image_count")) > image_cap:
            # plan_scope is O(images × stages × DB round trips); skip giant folders to
            # keep ``/api/runs/folder-buckets`` snappy. UI can fetch lazily per row.
            item["planner_preview_skipped"] = "too_many_images"
            continue
        if deadline is not None and time.monotonic() >= deadline:
            budget_exhausted = True
            item["planner_preview_skipped"] = "budget_exhausted"
            continue
        candidates = sort_phase_value_strings(
            [str(p) for p in item.get("next_phases") or list(target_phases)]
        )
        if not candidates:
            continue
        resolved, _ = utils.resolve_scope_input_path(str(item.get("path") or ""))
        if not resolved:
            continue
        try:
            item["planner_next_phases"] = phases_with_work_from_repair_plan(
                [resolved],
                candidates,
                dry_run=True,
                include_stale_executor=False,
            )
        except Exception:
            logger.debug(
                "runs_autodrive: planner preview failed for %s",
                item.get("path"),
                exc_info=True,
            )
    if budget_exhausted:
        logger.info(
            "runs_autodrive: planner preview budget %.1fs exhausted; skipped remaining items",
            float(budget_sec),
        )


def _resolve_folder_phase_summary(
    path: str,
    *,
    norm_path: str,
    norm_raw: str,
    raw_path: str,
    summaries: dict[str, Any],
    dirty_paths: set[str],
    refresh_dirty_limit: int,
    dirty_refreshed: list[int],
) -> list[dict[str, Any]]:
    """Load folder phase summary from bulk cache, refreshing when missing or dirty."""
    summary = (
        summaries.get(norm_path)
        or summaries.get(norm_raw)
        or summaries.get(path)
        or summaries.get(raw_path)
        or []
    )
    is_dirty = norm_path in dirty_paths or norm_raw in dirty_paths
    missing = not summary
    if not missing and not is_dirty:
        return summary

    limit = max(0, _as_int(refresh_dirty_limit, 0))
    may_refresh = missing or (is_dirty and limit > 0 and dirty_refreshed[0] < limit)
    if not may_refresh:
        return summary

    try:
        refreshed = db.get_folder_phase_summary(path, force_refresh=True) or []
        dirty_refreshed[0] += 1
        return refreshed
    except Exception:
        logger.debug(
            "runs_autodrive: force_refresh failed for %s",
            path,
            exc_info=True,
        )
    return summary


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


def _job_counts_toward_loop_guard(status: str) -> bool:
    """Whether a prior auto-drive job should count against ``max_repeats``."""
    norm = _status(status)
    if norm in ACTIVE_JOB_STATUSES:
        return True
    if norm in _LOOP_GUARD_TERMINAL_STATUSES:
        return True
    # Completed runs that made partial progress (e.g. bird_species) may need another pass.
    return False


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
    """Per ``plan_key`` attempt accounting for the progress-gated loop guard.

    Returns for each key:
      - ``failure_attempts``     active + terminal-failure jobs (always count toward max_repeats)
      - ``completed_attempts``   completed jobs (count only when the folder made no progress)
      - ``last_completed_percent`` max ``auto_drive_overall_percent`` recorded across completed runs
    """
    wanted = {k for k in plan_keys if k}
    if not wanted:
        return {}
    counts: dict[str, dict[str, Any]] = {
        key: {
            "failure_attempts": 0,
            "completed_attempts": 0,
            "last_completed_percent": 0.0,
            "last_run_id": None,
            "last_status": None,
        }
        for key in wanted
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
        status = str(row.get("status") or "")
        norm = _status(status)
        entry = counts[key]
        if _job_counts_toward_loop_guard(status):
            entry["failure_attempts"] += 1
        elif norm in _LOOP_GUARD_COMPLETED_STATUSES:
            entry["completed_attempts"] += 1
            pct = _as_float(payload.get("auto_drive_overall_percent"))
            if pct > float(entry["last_completed_percent"]):
                entry["last_completed_percent"] = pct
        else:
            continue
        if entry["last_run_id"] is None:
            entry["last_run_id"] = row.get("id")
            entry["last_status"] = status
    return counts


def _autodrive_buckets_cache_ttl_sec() -> float:
    try:
        from modules.config import get_config_value

        return max(5.0, float(get_config_value("auto_drive.buckets_cache_ttl_sec", default=45)))
    except Exception:
        return 45.0


def _bird_backlog_quota_threshold() -> int:
    try:
        from modules.config import get_config_value

        return max(
            1,
            _as_int(
                get_config_value(
                    "auto_drive.bird_backlog_quota_threshold",
                    default=BIRD_BACKLOG_QUOTA_THRESHOLD,
                ),
            ),
        )
    except Exception:
        return BIRD_BACKLOG_QUOTA_THRESHOLD


def _bird_backlog_reserved_slots(*, batch_limit: int, bird_backlog: int) -> int:
    try:
        from modules.config import get_config_value

        ratio = float(get_config_value("auto_drive.bird_backlog_reserve_ratio", default=0.6))
    except Exception:
        ratio = 0.6
    if bird_backlog <= 0:
        return 0
    return min(bird_backlog, batch_limit, max(1, int(batch_limit * ratio)))


_BUCKETS_CACHE_LOCK = threading.Lock()
_BUCKETS_CACHE: Dict[str, Any] = {"key": None, "built_at": 0.0, "planned": None}


def invalidate_autodrive_buckets_cache() -> None:
    with _BUCKETS_CACHE_LOCK:
        _BUCKETS_CACHE["key"] = None
        _BUCKETS_CACHE["planned"] = None


def _copy_planned_buckets(planned: dict[str, Any]) -> dict[str, Any]:
    """Defensive copy so callers can't mutate the shared cache entry.

    Item dicts are treated as read-only by callers, so copying the ``items`` list and the count
    dicts (not deep-copying every item) is enough to keep the cached scan immutable.
    """
    out = dict(planned)
    if isinstance(out.get("items"), list):
        out["items"] = list(out["items"])
    for k in ("bucket_counts", "phase_counts"):
        if isinstance(out.get(k), dict):
            out[k] = dict(out[k])
    return out


def _autodrive_buckets_cache_key(
    *,
    root_path: Optional[str],
    target_phases: Optional[Sequence[Any]],
    folder_paths: Optional[Sequence[str]],
) -> str:
    phases = tuple(normalize_target_phases(target_phases))
    explicit = tuple(sorted(_path_key(p) for p in (folder_paths or []) if _path_key(p)))
    root_key = _path_key(root_path or "")
    return f"{root_key}|{phases}|{explicit}"


# ---------------------------------------------------------------------------
# Productivity-aware candidate cooldown
# ---------------------------------------------------------------------------
# Folders that return ``nothing_to_queue`` / ``loop_detected`` are demoted for a
# short window so the batch fills with plannable work instead of re-evaluating the
# same empty/stuck folders every tick. The cooldown is voided early if the folder's
# ``overall_percent`` advances (it likely became plannable again). Library drives
# only — explicit/scoped requests always honor the user's chosen folders.
_UNPRODUCTIVE_SKIP_REASONS = frozenset({"nothing_to_queue", "loop_detected", "missing_on_disk"})
DRIVE_UNPRODUCTIVE_COOLDOWN_SEC = 600.0
_FOLDER_COOLDOWN_LOCK = threading.Lock()
_FOLDER_COOLDOWN: Dict[str, tuple[float, float]] = {}  # path_key -> (expiry_ts, percent_at_skip)


def _unproductive_cooldown_sec() -> float:
    """Cooldown window in seconds; 0 disables the feature. Config-tunable."""
    try:
        from modules.config import get_config_value

        if not bool(get_config_value("auto_drive.unproductive_cooldown_enabled", default=True)):
            return 0.0
        return max(
            0.0,
            float(
                get_config_value(
                    "auto_drive.unproductive_cooldown_sec",
                    default=DRIVE_UNPRODUCTIVE_COOLDOWN_SEC,
                )
            ),
        )
    except Exception:
        return DRIVE_UNPRODUCTIVE_COOLDOWN_SEC


def _is_folder_cooled(path_key: str, current_percent: float, now: float) -> bool:
    """True if ``path_key`` is in an active cooldown and has not advanced since."""
    if not path_key:
        return False
    with _FOLDER_COOLDOWN_LOCK:
        entry = _FOLDER_COOLDOWN.get(path_key)
        if not entry:
            return False
        expiry, pct_at_skip = entry
        if now >= expiry or current_percent > pct_at_skip + _PROGRESS_EPS:
            _FOLDER_COOLDOWN.pop(path_key, None)
            return False
        return True


def _record_unproductive_cooldown(path_key: str, percent: float, now: float, cooldown_sec: float) -> None:
    if not path_key or cooldown_sec <= 0:
        return
    with _FOLDER_COOLDOWN_LOCK:
        _FOLDER_COOLDOWN[path_key] = (now + cooldown_sec, percent)


def _clear_folder_cooldown(path_key: str) -> None:
    if not path_key:
        return
    with _FOLDER_COOLDOWN_LOCK:
        _FOLDER_COOLDOWN.pop(path_key, None)


def _clear_all_folder_cooldowns() -> None:
    with _FOLDER_COOLDOWN_LOCK:
        _FOLDER_COOLDOWN.clear()


def _retry_unattempted_on_loop() -> bool:
    """Kill switch: ``auto_drive.retry_unattempted_on_loop`` (default True).

    When True, the loop guard bypasses a ``loop_detected`` trip for folders whose
    blocking attempts were no-op completions and that still hold never-attempted work.
    """
    try:
        from modules.config import get_config_value

        return bool(get_config_value("auto_drive.retry_unattempted_on_loop", default=True))
    except Exception:
        return True


def build_folder_buckets_for_autodrive(
    *,
    root_path: Optional[str] = None,
    target_phases: Optional[Sequence[Any]] = None,
    folder_paths: Optional[Sequence[str]] = None,
    refresh_dirty_limit: int = AUTODRIVE_DIRTY_REFRESH_LIMIT,
) -> dict[str, Any]:
    """Full-library bucket scan for auto-drive with a short-lived in-process cache."""
    explicit_paths = [str(p).strip() for p in (folder_paths or []) if str(p).strip()]
    cache_key = _autodrive_buckets_cache_key(
        root_path=root_path,
        target_phases=target_phases,
        folder_paths=explicit_paths or None,
    )
    now = time.time()
    ttl = _autodrive_buckets_cache_ttl_sec()
    if not explicit_paths:
        with _BUCKETS_CACHE_LOCK:
            if (
                _BUCKETS_CACHE.get("key") == cache_key
                and _BUCKETS_CACHE.get("planned") is not None
                and (now - float(_BUCKETS_CACHE.get("built_at") or 0.0)) < ttl
            ):
                return _copy_planned_buckets(_BUCKETS_CACHE["planned"])

    planned = build_folder_buckets(
        root_path=root_path,
        limit=AUTODRIVE_CANDIDATE_SCAN_CAP,
        offset=0,
        include_complete=False,
        target_phases=target_phases,
        folder_paths=folder_paths,
        refresh_dirty_limit=refresh_dirty_limit,
        planner_preview_limit=0,
    )
    if not explicit_paths:
        with _BUCKETS_CACHE_LOCK:
            _BUCKETS_CACHE["key"] = cache_key
            _BUCKETS_CACHE["built_at"] = now
            _BUCKETS_CACHE["planned"] = planned
        return _copy_planned_buckets(planned)
    return planned


def _select_autodrive_candidates(
    schedulable: Sequence[dict[str, Any]],
    *,
    limit: int,
    bucket_counts: Dict[str, Any],
) -> list[dict[str, Any]]:
    """Pick up to ``limit`` leaf-ready folders with fair share for large bird backlogs."""
    limit = max(1, min(_as_int(limit, 50), AUTODRIVE_CANDIDATE_SCAN_CAP))
    items = list(schedulable)
    if len(items) <= limit:
        return items

    bird_bucket = "awaiting_bird_species"
    bird_backlog = _as_int((bucket_counts or {}).get(bird_bucket))
    threshold = _bird_backlog_quota_threshold()
    if bird_backlog < threshold:
        return items[:limit]

    reserved = _bird_backlog_reserved_slots(batch_limit=limit, bird_backlog=bird_backlog)
    bird_items = [i for i in items if i.get("bucket") == bird_bucket]
    other_items = [i for i in items if i.get("bucket") != bird_bucket]
    selected: list[dict[str, Any]] = []
    seen_paths: set[str] = set()

    def _take(pool: list[dict[str, Any]], n: int) -> None:
        for item in pool:
            if len(selected) >= limit or n <= 0:
                break
            pk = str(item.get("path_key") or _path_key(str(item.get("path") or "")))
            if pk and pk in seen_paths:
                continue
            selected.append(item)
            if pk:
                seen_paths.add(pk)
            n -= 1

    _take(bird_items, min(reserved, len(bird_items)))
    remaining = limit - len(selected)
    if remaining > 0:
        _take(other_items, remaining)
    if len(selected) < limit:
        _take(
            [i for i in items if (str(i.get("path_key") or _path_key(str(i.get("path") or ""))) not in seen_paths)],
            limit - len(selected),
        )
    return selected[:limit]


def _resolve_enqueue_phases_with_refresh(
    raw_path: str,
    resolved: str,
    phase_candidates: Sequence[str],
) -> list[str]:
    """JIT enqueue phases; refresh folder summary once when the repair plan is empty."""
    phase_values = resolve_auto_drive_enqueue_phases(resolved, phase_candidates, dry_run=True)
    if phase_values or not resolved:
        return phase_values
    try:
        db.get_folder_phase_summary(raw_path, force_refresh=True)
    except Exception:
        logger.debug(
            "runs_autodrive: force_refresh before nothing_to_queue failed for %s",
            raw_path,
            exc_info=True,
        )
    return resolve_auto_drive_enqueue_phases(resolved, phase_candidates, dry_run=True)


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


def _phase_prereq_blockers(
    phase_values: Sequence[str],
    complete: set[str],
    *,
    prereq_complete: Optional[set[str]] = None,
) -> dict[str, list[str]]:
    requested = set(phase_values)
    satisfied = prereq_complete if prereq_complete is not None else complete
    out: dict[str, list[str]] = {}
    for code in phase_values:
        missing = [
            pre for pre in PHASE_PREREQUISITES.get(code, ())
            if pre not in satisfied and pre not in requested
        ]
        if missing:
            out[code] = missing
    return out


def _resolve_phase_row(
    code: str,
    by_code: dict[str, dict[str, Any]],
    *,
    image_count: int,
    subtree_total: int,
    folder_path: str,
) -> dict[str, Any]:
    if code in by_code:
        return dict(by_code[code])
    fallback_total = subtree_total if subtree_total > 0 else image_count
    if code == "bird_species" and not db.folder_has_bird_species_work(folder_path):
        return {
            "code": code,
            "name": code.replace("_", " ").title(),
            "status": "skipped",
            "total_count": 0,
            "done_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "running_count": 0,
            "queued_count": 0,
            "paused_count": 0,
            "cancel_requested_count": 0,
            "restarting_count": 0,
            "optional": True,
        }
    return _default_phase_summary(code, fallback_total)


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
    subtree_total = _subtree_total_from_summary(summary)
    fallback_total = subtree_total if subtree_total > 0 else image_count
    phase_rows: list[dict[str, Any]] = []
    for code in target_phases:
        row = _resolve_phase_row(
            code,
            by_code,
            image_count=image_count,
            subtree_total=subtree_total,
            folder_path=path,
        )
        phase_rows.append(_phase_view(row, fallback_total))

    path_key = _path_key(path)
    complete_all = {
        code
        for code, row in by_code.items()
        if _is_complete(_phase_view(row, fallback_total))
    }
    for code in target_phases:
        if code not in by_code:
            synthetic = _resolve_phase_row(
                code,
                by_code,
                image_count=image_count,
                subtree_total=subtree_total,
                folder_path=path,
            )
            if _is_complete(_phase_view(synthetic, fallback_total)):
                complete_all.add(code)
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
    blockers = _phase_prereq_blockers(next_phases, complete, prereq_complete=complete_all) if next_phases else {}
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
    refresh_dirty_limit: int = 0,
    planner_preview_limit: int = 25,
    planner_preview_max_images: int = 500,
) -> dict[str, Any]:
    limit = max(1, min(_as_int(limit, 25), 500))
    offset = max(0, _as_int(offset, 0))
    target = normalize_target_phases(target_phases)
    root_key = _path_key(root_path or "")
    q_norm = str(q or "").strip().lower()
    bucket_filter = str(bucket or "").strip().lower()
    explicit_path_keys = {_path_key(p) for p in (folder_paths or []) if _path_key(p)}

    refresh_dirty_limit = max(0, _as_int(refresh_dirty_limit, 0))
    explicit_mode = bool(explicit_path_keys)
    if explicit_mode:
        direct_counts = db.get_folder_direct_image_counts_for_paths(folder_paths or [])
        summaries = {}
        dirty_paths = set()
        if refresh_dirty_limit <= 0:
            refresh_dirty_limit = len(explicit_path_keys)
    else:
        direct_counts = db.get_folder_direct_image_counts_by_local_path_norm()
        summaries = db.get_all_folder_phase_summaries_bulk(include_dirty_cache=False)
        dirty_paths = db.get_folder_phase_agg_dirty_local_paths()
    active_keys = _active_job_path_keys()
    dirty_refreshed = [0]
    prioritize_new = _autodrive_prioritize_new_folders()
    new_cutoff_ts = _new_folder_cutoff_ts() if prioritize_new else 0.0

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
        norm_path = os.path.normpath(path)
        norm_raw = os.path.normpath(raw_path) if raw_path else norm_path
        summary = _resolve_folder_phase_summary(
            path,
            norm_path=norm_path,
            norm_raw=norm_raw,
            raw_path=raw_path,
            summaries=summaries,
            dirty_paths=dirty_paths,
            refresh_dirty_limit=refresh_dirty_limit,
            dirty_refreshed=dirty_refreshed,
        )
        item = _build_bucket_from_summary(
            path,
            summary,
            image_count=image_count,
            target_phases=target,
            active_path_keys=active_keys,
        )
        raw_created = (meta or {}).get("created_at")
        item["folder_created_at"] = _format_folder_created_at(raw_created)
        item["is_newly_imported"] = (
            _is_newly_imported_folder(raw_created, cutoff_ts=new_cutoff_ts)
            if prioritize_new
            else False
        )
        if not include_complete and item["bucket"] == "complete":
            continue
        if bucket_filter and bucket_filter != "all" and item["bucket"] != bucket_filter:
            continue
        rows.append(item)

    phase_order = {code: i for i, code in enumerate(target)}
    bucket_order = {"blocked": -1, "in_flight": 99, "complete": 100}

    rows.sort(
        key=lambda item: _folder_bucket_sort_key(
            item,
            phase_order=phase_order,
            bucket_order=bucket_order,
            prioritize_new=prioritize_new,
            new_cutoff_ts=new_cutoff_ts,
        )
    )

    bucket_counts: dict[str, int] = {}
    phase_counts: dict[str, int] = {}
    for item in rows:
        bucket_counts[item["bucket"]] = bucket_counts.get(item["bucket"], 0) + 1
        phase = item.get("current_phase")
        if phase:
            phase_counts[phase] = phase_counts.get(phase, 0) + 1

    page = rows[offset: offset + limit]
    if not explicit_mode:
        _attach_planner_preview_to_bucket_items(
            page,
            target_phases=target,
            planner_preview_limit=planner_preview_limit,
            max_images=planner_preview_max_images,
        )
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
    resolved: Optional[str] = None,
    phase_values: Optional[Sequence[str]] = None,
) -> tuple[Optional[int], Optional[int], Optional[dict[str, Any]]]:
    raw_path = str(bucket.get("path") or "")
    # ``resolved`` / ``phase_values`` are passed by the drive loop, which already
    # computed them to derive the loop-guard plan_key; reuse them so we don't build
    # the dry-run repair plan a second time per enqueued folder.
    if not resolved:
        resolved, _candidates = utils.resolve_scope_input_path(raw_path)
    if not resolved or not os.path.isdir(resolved):
        return None, None, {"reason": "missing_on_disk", "folder_path": raw_path}

    phase_candidates = sort_phase_value_strings(
        [str(p) for p in bucket.get("next_phases") or list(DEFAULT_TARGET_PHASES)]
    )
    if phase_values is None:
        phase_values = resolve_auto_drive_enqueue_phases(resolved, phase_candidates, dry_run=True)
    else:
        phase_values = list(phase_values)
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

    repair_plan = db.build_validation_repair_plan(
        [resolved],
        phase_values,
        False,
        include_stale_executor=False,
    )
    payload["repair_plan_summary"] = repair_plan
    payload["resolved_image_ids_by_stage"] = repair_plan.get("stage_queues", {})
    first_ids = (repair_plan.get("stage_queues", {}) or {}).get(phase_values[0])
    if isinstance(first_ids, list):
        payload["resolved_image_ids"] = first_ids
    payload["skip_existing"] = False
    payload["post_run_audit"] = True

    reason_summary, reason_criteria = build_auto_drive_summary(
        scope_paths=[resolved],
        enqueued_phases=phase_values,
        requested_phases=phase_candidates,
        auto_drive_bucket=str(bucket.get("bucket") or ""),
        auto_drive_overall_percent=bucket.get("overall_percent"),
        auto_drive_plan_key=str(payload.get("auto_drive_plan_key") or ""),
        repair_plan=repair_plan,
        run_mode=CANONICAL_RUN_MODE,
        folder_created_at=bucket.get("folder_created_at"),
        is_newly_imported=bucket.get("is_newly_imported"),
    )
    payload = attach_run_reason(
        payload,
        source=REASON_SOURCE_AUTO_DRIVE,
        summary=reason_summary,
        criteria=reason_criteria,
        trigger="api",
        tool_id="runs_auto_drive",
    )

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
    explicit_paths = [str(p).strip() for p in (folder_paths or []) if str(p).strip()]
    scoped_request = bool(explicit_paths)
    if scoped_request:
        logger.info(
            "runs_autodrive: scoped auto-drive for %d explicit folder(s)",
            len(explicit_paths),
        )
    else:
        _reconcile_stale_ips_for_drive()

    if scoped_request:
        all_path_keys: set[str] = set()
        require_leaf = False
    else:
        direct_counts = db.get_folder_direct_image_counts_by_local_path_norm()
        all_path_keys = {
            pk for p in direct_counts.keys() if (pk := _path_key(_local_path(p)))
        }
        require_leaf = True

    planned = build_folder_buckets_for_autodrive(
        root_path=root_path,
        target_phases=target_phases,
        folder_paths=folder_paths,
        refresh_dirty_limit=len(explicit_paths) if scoped_request else AUTODRIVE_DIRTY_REFRESH_LIMIT,
    )
    schedulable = [
        item for item in planned["items"]
        if item.get("next_phases") and item.get("bucket") not in {"blocked", "in_flight", "complete"}
        and (not require_leaf or _is_leaf_folder_for_autodrive(_path_key(str(item.get("path") or "")), all_path_keys))
    ]
    # Productivity-aware cooldown: drop folders that recently planned empty / loop-blocked
    # so the batch fills with plannable work. Scoped requests honor the user's folders as-is.
    cooldown_sec = 0.0 if scoped_request else _unproductive_cooldown_sec()
    cooldown_now = time.time()
    record_cooldowns = cooldown_sec > 0 and not dry_run
    if cooldown_sec > 0:
        eligible = [
            item for item in schedulable
            if not _is_folder_cooled(
                _path_key(str(item.get("path") or "")),
                _as_float(item.get("overall_percent")),
                cooldown_now,
            )
        ]
        # Never starve the drive: if every schedulable folder is cooled, ignore the
        # cooldown this tick rather than reporting a false stall.
        candidate_pool = eligible if eligible else schedulable
        cooled_out = len(schedulable) - len(candidate_pool)
    else:
        candidate_pool = schedulable
        cooled_out = 0
    candidates = _select_autodrive_candidates(
        candidate_pool,
        limit=limit,
        bucket_counts=planned.get("bucket_counts", {}),
    )
    if scoped_request and not candidates and planned.get("items"):
        logger.info(
            "runs_autodrive: explicit folder(s) not queueable (bucket=%s)",
            [item.get("bucket") for item in planned.get("items", [])],
        )
    # Resolve each candidate's enqueue-time identity ONCE, then build the attempt
    # counts from those exact (narrowed) plan keys. ``_enqueue_auto_bucket`` stores
    # ``_plan_key(resolved, phase_values)`` on the job payload; counting against the
    # wider bucket key (``next_phases``) here would never match the stored job keys,
    # so the loop guard (max_repeats) would never fire. See RCA root cause #2.
    prepared: list[dict[str, Any]] = []
    for item in candidates:
        raw_path = str(item.get("path") or "")
        resolved, _candidates = utils.resolve_scope_input_path(raw_path)
        phase_candidates = sort_phase_value_strings(
            [str(p) for p in item.get("next_phases") or list(DEFAULT_TARGET_PHASES)]
        )
        phase_values = (
            _resolve_enqueue_phases_with_refresh(raw_path, resolved, phase_candidates)
            if resolved
            else []
        )
        plan_key = (
            _plan_key(resolved, phase_values)
            if resolved and phase_values
            else str(item.get("plan_key") or "")
        )
        prepared.append(
            {
                "item": item,
                "resolved": resolved,
                "phase_values": phase_values,
                "plan_key": plan_key,
            }
        )

    attempts = _recent_auto_attempt_counts([p["plan_key"] for p in prepared])

    scheduled: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    loop_detected = 0

    for prep in prepared:
        item = prep["item"]
        plan_key = str(prep["plan_key"] or "")
        attempt_meta = attempts.get(plan_key) or {}
        failure_attempts = _as_int(attempt_meta.get("failure_attempts"))
        completed_attempts = _as_int(attempt_meta.get("completed_attempts"))
        # Forgive completed runs only when the folder advanced since the last completed pass;
        # a folder that keeps completing without progress is bounded at max_repeats.
        current_percent = _as_float(item.get("overall_percent"))
        last_completed_percent = _as_float(attempt_meta.get("last_completed_percent"))
        made_progress = current_percent > last_completed_percent + _PROGRESS_EPS
        effective_attempts = failure_attempts
        if completed_attempts > 0 and not made_progress:
            effective_attempts += completed_attempts
        if effective_attempts >= max_repeats:
            # Don't loop-block when the blocking attempts were no-op COMPLETIONS (empty
            # plans, e.g. claims blocked the work at the time) and the folder still has
            # genuinely un-attempted work (attempt_count == 0). A no-op completion is not
            # a real attempt at the pending images, so it must not permanently block work
            # that has never run. Active failures (failure_attempts > 0) still loop-block,
            # so a truly broken runner stalls instead of spinning.
            if (
                _retry_unattempted_on_loop()
                and failure_attempts == 0
                and prep["phase_values"]
                and prep["resolved"]
                and db.scope_has_unattempted_phase_work(prep["resolved"], prep["phase_values"][0])
            ):
                logger.info(
                    "runs_autodrive: loop-guard bypass — un-attempted work in %s (phase=%s, %d no-op completions)",
                    item.get("path"), prep["phase_values"][0], completed_attempts,
                )
            else:
                loop_detected += 1
                skipped.append({
                    "folder_path": item.get("path"),
                    "phases": item.get("next_phases") or [],
                    "reason": "loop_detected",
                    "attempts": effective_attempts,
                    "failure_attempts": failure_attempts,
                    "completed_attempts": completed_attempts,
                    "made_progress": made_progress,
                    "last_run_id": attempt_meta.get("last_run_id"),
                    "last_status": attempt_meta.get("last_status"),
                })
                if record_cooldowns:
                    _record_unproductive_cooldown(
                        _path_key(str(item.get("path") or "")),
                        current_percent,
                        cooldown_now,
                        cooldown_sec,
                    )
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
                resolved=prep["resolved"] or None,
                phase_values=prep["phase_values"],
            )
            if skip:
                entry = {**skip, "phases": item.get("next_phases") or []}
                skipped.append(entry)
                if entry.get("reason") == "nothing_to_queue":
                    logger.info(
                        "runs_autodrive: nothing_to_queue path=%s bucket=%s current_phase=%s",
                        item.get("path"),
                        item.get("bucket"),
                        item.get("current_phase"),
                    )
                if record_cooldowns and str(entry.get("reason") or "") in _UNPRODUCTIVE_SKIP_REASONS:
                    _record_unproductive_cooldown(
                        _path_key(str(item.get("path") or "")),
                        _as_float(item.get("overall_percent")),
                        cooldown_now,
                        cooldown_sec,
                    )
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
            if record_cooldowns:
                _clear_folder_cooldown(_path_key(str(item.get("path") or "")))
        except Exception as exc:
            logger.exception("runs_autodrive: failed to queue %s", item.get("path"))
            skipped.append({
                "folder_path": item.get("path"),
                "phases": item.get("next_phases") or [],
                "reason": "exception",
                "error": str(exc),
            })

    bucket_counts = planned.get("bucket_counts", {})
    skip_reason_counts: dict[str, int] = (
        dict(Counter(str(item.get("reason") or "unknown") for item in skipped))
        if skipped
        else {}
    )
    result = {
        "dry_run": bool(dry_run),
        "run_mode": CANONICAL_RUN_MODE,
        "limit": limit,
        "scheduled": scheduled,
        "skipped": skipped,
        "candidates": len(candidates),
        "total_outstanding": planned["total"],
        "loop_detected": loop_detected,
        "cooldown_skipped": cooled_out,
        "skip_reason_counts": skip_reason_counts,
        "bucket_counts": bucket_counts,
        "phase_counts": planned.get("phase_counts", {}),
        "health": _bucket_health_from_counts(bucket_counts),
    }
    if scheduled and not dry_run:
        invalidate_autodrive_buckets_cache()
    if dry_run:
        logger.info(
            "runs_autodrive: preview — candidates=%d would_queue=%d skipped=%d outstanding=%d",
            len(candidates),
            len(scheduled),
            len(skipped),
            planned["total"],
        )
    else:
        logger.info(
            "runs_autodrive: batch scan — candidates=%d queued=%d skipped=%d outstanding=%d "
            "loop_detected=%d cooldown_skipped=%d",
            len(candidates),
            len(scheduled),
            len(skipped),
            planned["total"],
            loop_detected,
            cooled_out,
        )
        if skipped:
            logger.info("runs_autodrive: skip reasons: %s", _format_skip_summary(skipped))
        _log_scheduled_runs(scheduled)
    return result


# ---------------------------------------------------------------------------
# Durable server-side drive loop
# ---------------------------------------------------------------------------
# A user starts a "Drive to Complete" via the API; the JobDispatcher then calls
# ``drive_tick`` on every idle tick to top up the queue with the next batch of
# folder runs until nothing is outstanding (or the work stalls / hits the loop
# guard). State lives in-process: a backend restart stops an in-flight drive.

DRIVE_TICK_COOLDOWN_SEC = 15.0
DRIVE_MAX_NOPROGRESS_TICKS = 3
# Absolute cap so a loop-blocked drive (work remains but every candidate trips the loop guard)
# eventually stalls instead of spinning forever.
DRIVE_MAX_LOOPBLOCKED_TICKS = 10

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
    "last_batch_error": None,
    "stop_reason": None,
    "idle_no_progress_ticks": 0,
    "loopblocked_ticks": 0,
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
        state = dict(_DRIVE_STATE)
    state["batch_in_progress"] = _DRIVE_BATCH_LOCK.locked()
    return state


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
        "skip_reason_counts": dict(result.get("skip_reason_counts") or {}),
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
    state = arm_drive(
        root_path=root_path,
        limit=limit,
        target_phases=target_phases,
        generate_captions=generate_captions,
        max_repeats=max_repeats,
    )
    result = _run_drive_batch(force=True)
    return {"state": state, "result": result}


def arm_drive(
    *,
    root_path: Optional[str] = None,
    limit: int = 50,
    target_phases: Optional[Sequence[Any]] = None,
    generate_captions: bool = True,
    max_repeats: int = 2,
) -> Dict[str, Any]:
    """Enable the durable drive without running an immediate batch.

    This is safe for API handlers that must return quickly. Use
    ``kick_drive_batch_async(force=True)`` to enqueue work without blocking.
    """
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
                "last_batch_error": None,
                "stop_reason": None,
                "idle_no_progress_ticks": 0,
                "loopblocked_ticks": 0,
            }
        )
        invalidate_autodrive_buckets_cache()
        _clear_all_folder_cooldowns()
    state = get_drive_state()
    logger.info(
        "runs_autodrive: drive armed root=%s limit=%s max_repeats=%s target_phases=%s",
        state.get("root_path") or "library",
        state.get("limit"),
        state.get("max_repeats"),
        state.get("target_phases") or "full pipeline",
    )
    _broadcast_drive("drive_started")
    return state


def kick_drive_batch_async(*, force: bool = False) -> Dict[str, Any]:
    """Run one drive batch in a background thread and return immediately.

    If a batch is already in flight the second call is a no-op (returns
    ``started=False, reason="busy"``) so duplicate clicks don't lie about
    queuing fresh work.
    """
    if _DRIVE_BATCH_LOCK.locked():
        logger.info("runs_autodrive: drive batch already running (start request ignored)")
        return {"started": False, "reason": "busy"}

    def _runner():
        try:
            logger.info("runs_autodrive: drive batch thread started (force=%s)", force)
            _run_drive_batch(force=bool(force))
        except Exception as exc:
            logger.exception("runs_autodrive: async drive batch failed")
            with _DRIVE_LOCK:
                _DRIVE_STATE["last_batch_error"] = {
                    "at": time.time(),
                    "type": type(exc).__name__,
                    "message": str(exc)[:500],
                }

    t = threading.Thread(target=_runner, daemon=True, name="runs-autodrive-batch")
    t.start()
    logger.info("runs_autodrive: drive batch scheduled on background thread")
    return {"started": True}


def stop_drive(reason: str = "manual") -> Dict[str, Any]:
    with _DRIVE_LOCK:
        was_enabled = bool(_DRIVE_STATE["enabled"])
        last_result = _DRIVE_STATE.get("last_result")
        _DRIVE_STATE["enabled"] = False
        _DRIVE_STATE["stop_reason"] = reason
        invalidate_autodrive_buckets_cache()
    if was_enabled:
        logger.info(
            "runs_autodrive: drive stopped reason=%s last_tick=%s",
            reason,
            last_result,
        )
        _broadcast_drive("drive_stopped", {"reason": reason})
    return get_drive_state()


def _run_drive_batch(*, force: bool = False) -> Optional[Dict[str, Any]]:
    """Run one ``auto_drive_runs`` batch if due. Returns a summary or ``None``.

    ``force`` bypasses the cooldown (used by ``start_drive`` for an immediate
    first batch). A non-blocking batch lock ensures only one batch runs at a
    time across the dispatcher thread and API threads.
    """
    if not _DRIVE_BATCH_LOCK.acquire(blocking=False):
        logger.debug("runs_autodrive: drive batch skipped (another batch holds the lock)")
        return None
    summary: Optional[Dict[str, Any]] = None
    stop_reason: Optional[str] = None
    try:
        with _DRIVE_LOCK:
            if not _DRIVE_STATE["enabled"]:
                logger.debug("runs_autodrive: drive batch skipped (drive disabled)")
                return None
            now = time.time()
            last_tick = float(_DRIVE_STATE["last_tick_at"])
            if not force and (now - last_tick) < DRIVE_TICK_COOLDOWN_SEC:
                remaining = DRIVE_TICK_COOLDOWN_SEC - (now - last_tick)
                logger.info(
                    "runs_autodrive: drive tick skipped (cooldown %.0fs remaining)",
                    remaining,
                )
                return None
            _DRIVE_STATE["last_tick_at"] = now
            params = {
                "root_path": _DRIVE_STATE["root_path"],
                "limit": _DRIVE_STATE["limit"],
                "max_repeats": _DRIVE_STATE["max_repeats"],
                "generate_captions": _DRIVE_STATE["generate_captions"],
                "target_phases": _DRIVE_STATE["target_phases"],
            }

        logger.info(
            "runs_autodrive: drive batch starting root=%s limit=%s force=%s",
            params["root_path"] or "library",
            params["limit"],
            force,
        )
        try:
            result = auto_drive_runs(dry_run=False, **params)
        except Exception as exc:
            logger.exception("runs_autodrive: drive batch failed")
            with _DRIVE_LOCK:
                _DRIVE_STATE["last_batch_error"] = {
                    "at": time.time(),
                    "type": type(exc).__name__,
                    "message": str(exc)[:500],
                }
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

        with _DRIVE_LOCK:
            _DRIVE_STATE["last_result"] = summary
            _DRIVE_STATE["last_batch_error"] = None
            if immediate_stop == "complete":
                _DRIVE_STATE["idle_no_progress_ticks"] = 0
                _DRIVE_STATE["loopblocked_ticks"] = 0
                stop_reason = "complete"
            elif immediate_stop == "blocked":
                _DRIVE_STATE["idle_no_progress_ticks"] = 0
                _DRIVE_STATE["loopblocked_ticks"] = 0
                stop_reason = "blocked"
            elif tick_reason in {"waiting_in_flight", "queued"}:
                _DRIVE_STATE["idle_no_progress_ticks"] = 0
                _DRIVE_STATE["loopblocked_ticks"] = 0
            elif tick_reason == "no_enqueue_progress":
                loop_n = _as_int(result.get("loop_detected"))
                skipped_n = len(result.get("skipped", []) or [])
                schedulable = _as_int(health.get("schedulable_folders"))
                mostly_loop_skips = (
                    loop_n > 0
                    and skipped_n > 0
                    and loop_n >= max(1, int(skipped_n * 0.75))
                )
                loop_blocked = mostly_loop_skips and schedulable > 0 and scheduled_n == 0
                if loop_blocked:
                    # Loop guard is masking the normal idle counter; keep driving so multi-pass
                    # work can resume, but bound it with an absolute cap so we still stall if the
                    # backlog is genuinely stuck.
                    _DRIVE_STATE["idle_no_progress_ticks"] = 0
                    _DRIVE_STATE["loopblocked_ticks"] += 1
                    if _DRIVE_STATE["loopblocked_ticks"] >= DRIVE_MAX_LOOPBLOCKED_TICKS:
                        stop_reason = "stalled"
                else:
                    _DRIVE_STATE["idle_no_progress_ticks"] += 1
                    if _DRIVE_STATE["idle_no_progress_ticks"] >= DRIVE_MAX_NOPROGRESS_TICKS:
                        stop_reason = "stalled"
            else:
                _DRIVE_STATE["idle_no_progress_ticks"] += 1
                if _DRIVE_STATE["idle_no_progress_ticks"] >= DRIVE_MAX_NOPROGRESS_TICKS:
                    stop_reason = "stalled"

        _log_drive_tick_result(
            tick_reason=tick_reason,
            summary=summary,
            stop_reason=stop_reason,
        )
    finally:
        _DRIVE_BATCH_LOCK.release()

    if stop_reason:
        stop_drive(stop_reason)
    elif summary is not None:
        _broadcast_drive("drive_progress")
    return summary


def drive_tick() -> Optional[Dict[str, Any]]:
    """Cheap no-op unless a drive is active. Called from the JobDispatcher idle path."""
    with _DRIVE_LOCK:
        if not _DRIVE_STATE["enabled"]:
            return None
    if not _config_server_loop_enabled():
        logger.info("runs_autodrive: drive tick skipped (auto_drive.server_loop_enabled=false)")
        return None
    return _run_drive_batch(force=False)


def get_drive_status_with_outstanding() -> Dict[str, Any]:
    """Drive state plus a light snapshot of outstanding work for the UI."""
    state = get_drive_state()
    last = state.get("last_result")
    if isinstance(last, dict) and last:
        bucket_counts = last.get("bucket_counts", {}) or {}
        outstanding = {
            "total_outstanding": _as_int(last.get("total_outstanding")),
            "bucket_counts": bucket_counts,
            "phase_counts": last.get("phase_counts", {}) or {},
            "health": last.get("health") or _bucket_health_from_counts(bucket_counts),
            "source": "last_result",
        }
    else:
        # Avoid recomputing ``build_folder_buckets`` here: even with limit=1 it must
        # scan all folders to produce totals and counts, which can block API polling
        # on large libraries.
        outstanding = {
            "total_outstanding": None,
            "bucket_counts": {},
            "phase_counts": {},
            "health": _bucket_health_from_counts({}),
            "source": "unknown",
        }
    last_err = state.get("last_batch_error")
    if last_err:
        outstanding["last_batch_error"] = last_err
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
