from __future__ import annotations

CANONICAL_RUN_MODE = "process_stale_or_missing"

# Legacy run_mode strings on in-flight jobs map to the canonical mode.
_LEGACY_RUN_MODE_ALIASES = {
    "process_all_overwrite",
    "process_unprocessed_or_empty",
    "validate_and_repair",
}

RUN_MODE_FLAGS: dict[str, dict[str, bool]] = {
    CANONICAL_RUN_MODE: {
        "skip_done": False,
        "skip_existing": False,
        "force_rerun": False,
        "fix_incomplete_stages": True,
        "overwrite": False,
        "force_rescan": False,
    },
}


def normalize_run_mode(run_mode: str | None) -> str:
    """Return canonical run_mode; map legacy persisted values to the single mode."""
    mode = (run_mode or "").strip()
    if not mode or mode in _LEGACY_RUN_MODE_ALIASES:
        return CANONICAL_RUN_MODE
    if mode not in RUN_MODE_FLAGS:
        raise ValueError(
            f"Invalid run_mode={run_mode!r}. "
            f"Allowed values: {sorted(RUN_MODE_FLAGS)}"
        )
    return mode


def infer_run_mode(
    run_mode: str | None,
    *,
    run_mode_explicit: bool = True,
    skip_done: bool | None = None,
    force_rerun: bool | None = None,
    fix_incomplete_stages: bool | None = None,
) -> str:
    """Resolve canonical run_mode (legacy boolean args are ignored)."""
    _ = (skip_done, force_rerun, fix_incomplete_stages, run_mode_explicit)
    if run_mode_explicit and run_mode:
        return normalize_run_mode(run_mode)
    return CANONICAL_RUN_MODE


def resolve_run_mode_flags(run_mode: str | None) -> dict[str, bool]:
    mode = normalize_run_mode(run_mode)
    return dict(RUN_MODE_FLAGS[mode])
