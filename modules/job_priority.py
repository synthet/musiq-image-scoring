"""Queue priority resolution for job enqueue paths."""
from __future__ import annotations

from typing import Any, Mapping, Optional

_AUTO_DRIVE_TOOL_IDS = frozenset({
    "runs_auto_drive",
    "auto_drive_heal_thumbnails",
    "auto_drive_self_heal",
})

_MAINTENANCE_TOOL_PREFIXES = ("auto_drive_heal", "auto_drive_", "maintenance")


def _config_bool(key: str, default: bool) -> bool:
    try:
        from modules.config import get_config_value

        return bool(get_config_value(key, default=default))
    except Exception:
        return default


def _config_int(key: str, default: int) -> int:
    try:
        from modules.config import get_config_value

        return int(get_config_value(key, default=default))
    except (TypeError, ValueError):
        return default


def resolve_job_enqueue_priority(
    payload: Optional[Mapping[str, Any]],
    *,
    job_type: Optional[str] = None,
) -> int:
    """Map queue_payload + job_type to a 1..999 priority (higher dequeues sooner)."""
    data = dict(payload) if payload else {}
    if "priority" in data and data.get("priority") is not None:
        try:
            return max(1, min(int(data["priority"]), 999))
        except (TypeError, ValueError):
            pass

    if not _config_bool("dispatcher.priority_lanes_enabled", default=True):
        return 100

    base = 100
    tool_id = str(data.get("tool_id") or "").strip().lower()
    jt = str(job_type or data.get("job_type") or "").strip().lower()

    if data.get("auto_drive_plan_key") or tool_id in _AUTO_DRIVE_TOOL_IDS:
        return base

    if jt == "maintenance" or any(tool_id.startswith(p) for p in _MAINTENANCE_TOOL_PREFIXES):
        return max(1, base - _config_int("dispatcher.maintenance_priority_delta", default=50))

    # Manual / interactive API submits (Runs UI, pipeline submit, legacy starts).
    interactive_boost = _config_int("dispatcher.interactive_priority_boost", default=200)
    if tool_id and tool_id not in _AUTO_DRIVE_TOOL_IDS:
        base = min(999, base + interactive_boost)

    small_threshold = _config_int("dispatcher.small_batch_image_threshold", default=10)
    small_boost = _config_int("dispatcher.small_batch_priority_boost", default=50)
    resolved = data.get("resolved_image_ids")
    if isinstance(resolved, list) and 0 < len(resolved) <= small_threshold:
        base = min(999, base + small_boost)

    return max(1, min(base, 999))
