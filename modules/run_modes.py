from __future__ import annotations

from typing import Dict, Optional

RUN_MODE_FLAGS: Dict[str, Dict[str, bool]] = {
    "process_all_overwrite": {
        "skip_done": False,
        "skip_existing": False,
        "force_rerun": True,
        "fix_incomplete_stages": False,
        "overwrite": True,
        "force_rescan": True,
    },
    "process_unprocessed_or_empty": {
        "skip_done": True,
        "skip_existing": True,
        "force_rerun": False,
        "fix_incomplete_stages": False,
        "overwrite": False,
        "force_rescan": False,
    },
    "validate_and_repair": {
        "skip_done": False,
        "skip_existing": False,
        "force_rerun": False,
        "fix_incomplete_stages": True,
        "overwrite": False,
        "force_rescan": True,
    },
}


def infer_run_mode(
    run_mode: Optional[str],
    *,
    run_mode_explicit: bool,
    skip_done: Optional[bool] = None,
    force_rerun: Optional[bool] = None,
    fix_incomplete_stages: Optional[bool] = None,
) -> str:
    """
    Resolve canonical run_mode.

    If run_mode was explicitly provided, it must be valid and wins over legacy booleans.
    If run_mode was omitted, infer from legacy booleans for backward compatibility.
    """
    mode = (run_mode or "").strip()
    if run_mode_explicit:
        if mode not in RUN_MODE_FLAGS:
            raise ValueError(
                f"Invalid run_mode={run_mode!r}. "
                f"Allowed values: {sorted(RUN_MODE_FLAGS)}"
            )
        return mode

    if bool(fix_incomplete_stages):
        return "validate_and_repair"
    if bool(force_rerun) or (skip_done is False):
        return "process_all_overwrite"
    return "process_unprocessed_or_empty"


def resolve_run_mode_flags(run_mode: str) -> Dict[str, bool]:
    mode = (run_mode or "").strip()
    if mode not in RUN_MODE_FLAGS:
        raise ValueError(
            f"Invalid run_mode={run_mode!r}. "
            f"Allowed values: {sorted(RUN_MODE_FLAGS)}"
        )
    return dict(RUN_MODE_FLAGS[mode])
