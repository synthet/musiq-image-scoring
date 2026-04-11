"""
Run-scoped log lines for workflow jobs (Web UI /runs detail).

Uses the same level names as Python logging: DEBUG, INFO, WARNING, ERROR.
DEBUG lines are broadcast live but should not be appended to persisted jobs.log
(see should_persist_run_log_line).
"""

from __future__ import annotations

from typing import List, Optional

RUN_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR"})


def normalize_run_log_level(level: str) -> str:
    u = (level or "INFO").strip().upper()
    if u not in RUN_LOG_LEVELS:
        return "INFO"
    return u


def format_run_log_message(
    message: str,
    *,
    phase: Optional[str] = None,
    step: Optional[str] = None,
) -> str:
    parts: List[str] = []
    if phase:
        parts.append(f"[{phase}]")
    if step:
        parts.append(f"[{step}]")
    if not parts:
        return str(message)
    return f"{' '.join(parts)} {message}".strip()


def emit_run_log(
    run_id: Optional[int],
    message: str,
    level: str = "INFO",
    *,
    phase: Optional[str] = None,
    step: Optional[str] = None,
) -> str:
    """
    Push one line to WebSocket clients when run_id is set.
    Returns the normalized level string.
    """
    norm = normalize_run_log_level(level)
    body = format_run_log_message(message, phase=phase, step=step)
    if run_id is not None:
        from modules.events import broadcast_run_log_line

        broadcast_run_log_line(int(run_id), body, level=norm)
    return norm


def should_persist_run_log_line(level: str) -> bool:
    """Persisted jobs.log should omit DEBUG to limit size on large runs."""
    return normalize_run_log_level(level) != "DEBUG"


def append_persisted_job_log(log_history: List[str], message: str, level: str = "INFO") -> None:
    """Append to runner log_history only if the line should be stored on the job row."""
    if should_persist_run_log_line(level):
        log_history.append(message)


def runner_emit(
    log_history: List[str],
    job_id: Optional[int],
    message: str,
    level: str = "INFO",
    *,
    phase: Optional[str] = None,
    step: Optional[str] = None,
) -> str:
    """
    Format one line, optionally persist to log_history (omits DEBUG), and broadcast when job_id is set.
    Returns normalized level.
    """
    norm = normalize_run_log_level(level)
    body = format_run_log_message(message, phase=phase, step=step)
    if should_persist_run_log_line(norm):
        log_history.append(body)
    if job_id is not None:
        from modules.events import broadcast_run_log_line

        broadcast_run_log_line(int(job_id), body, level=norm)
    return norm
