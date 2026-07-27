"""Runner globals, dispatcher, and graceful shutdown for the REST API."""

import logging
import threading
from typing import Any

from modules import db
from modules.job_dispatcher import JobDispatcher

logger = logging.getLogger(__name__)

# Global references to runners (set by webui.py)
_scoring_runner = None
_tagging_runner = None
_clustering_runner = None
_selection_runner = None
_bird_species_runner = None
_indexing_runner = None
_metadata_runner = None
_maintenance_runner = None
_orchestrator = None
_job_dispatcher = JobDispatcher()


def _stop_runner_for_phase(phase: str) -> bool:
    phase_norm = (phase or "").strip().lower()
    if phase_norm == "scoring" and _scoring_runner is not None:
        _scoring_runner.stop()
        return True
    if phase_norm in ("keywords", "tagging") and _tagging_runner is not None:
        _tagging_runner.stop()
        return True
    if phase_norm in ("culling", "selection") and _selection_runner is not None:
        _selection_runner.stop()
        return True
    if phase_norm == "clustering" and _clustering_runner is not None:
        _clustering_runner.stop()
        return True
    if phase_norm == "indexing" and _indexing_runner is not None:
        _indexing_runner.stop()
        return True
    if phase_norm == "metadata" and _metadata_runner is not None:
        _metadata_runner.stop()
        return True
    if phase_norm in ("bird_species", "bird-species") and _bird_species_runner is not None:
        _bird_species_runner.stop()
        return True
    return False


def set_runners(scoring_runner, tagging_runner, clustering_runner=None, selection_runner=None, orchestrator=None, bird_species_runner=None, indexing_runner=None, metadata_runner=None, maintenance_runner=None):
    """Set the runner instances for API access."""
    global _scoring_runner, _tagging_runner, _clustering_runner, _selection_runner, _orchestrator, _job_dispatcher, _bird_species_runner, _indexing_runner, _metadata_runner, _maintenance_runner
    _scoring_runner = scoring_runner
    _tagging_runner = tagging_runner
    _clustering_runner = clustering_runner
    _selection_runner = selection_runner
    _orchestrator = orchestrator
    _bird_species_runner = bird_species_runner
    _indexing_runner = indexing_runner
    _metadata_runner = metadata_runner
    _maintenance_runner = maintenance_runner
    _job_dispatcher.set_runners(
        scoring_runner, 
        tagging_runner, 
        clustering_runner, 
        selection_runner, 
        bird_species_runner=bird_species_runner,
        indexing_runner=indexing_runner,
        metadata_runner=metadata_runner,
        maintenance_runner=maintenance_runner,
    )
    _job_dispatcher.start()


def stop_dispatcher():
    """Stop background dispatcher thread, used during server shutdown."""
    try:
        _job_dispatcher.stop()
    except Exception as exc:
        logger.warning("Failed to stop JobDispatcher cleanly: %s", exc)


_graceful_shutdown_lock = threading.Lock()
_graceful_shutdown_done = False


def _map_job_row_to_dispatch_phase(job: dict[str, Any]) -> str:
    """Map a jobs row to the phase key used by ``_stop_runner_for_phase``."""
    jt = (job.get("job_type") or "").strip().lower()
    cur = (job.get("current_phase") or "").strip().lower()
    if jt in ("pipeline", "ui_pipeline") and cur:
        return cur
    if jt in ("tag", "tagging", "keywords"):
        return "keywords"
    if jt in ("selection", "culling"):
        return "culling"
    if jt in ("cluster", "clustering"):
        return "clustering"
    if jt in ("bird_species", "bird-species"):
        return "bird_species"
    return jt or ""


def _stop_runner_for_job_row(job: dict[str, Any]) -> bool:
    phase = _map_job_row_to_dispatch_phase(job)
    if not phase:
        return False
    if _stop_runner_for_phase(phase):
        return True
    for ph in (
        "indexing",
        "metadata",
        "scoring",
        "keywords",
        "tagging",
        "clustering",
        "selection",
        "culling",
        "bird_species",
    ):
        if _stop_runner_for_phase(ph):
            return True
    return False


def _join_runner_threads(per_thread_timeout: float = 2.0) -> None:
    """Wait for background runner threads to finish after ``stop()``."""
    runners = [
        _indexing_runner,
        _metadata_runner,
        _scoring_runner,
        _tagging_runner,
        _clustering_runner,
        _selection_runner,
        _bird_species_runner,
    ]
    for r in runners:
        if r is None:
            continue
        th = getattr(r, "_thread", None)
        if th is not None and th.is_alive():
            th.join(timeout=per_thread_timeout)


def _finalize_running_jobs_after_worker_stop(reason_log: str = "server_shutdown") -> None:
    """Move jobs still marked running to paused and reset in-flight image_phase_status rows."""
    try:
        rows = db.get_connector().query("SELECT id FROM jobs WHERE status = 'running'")
    except Exception:
        logger.exception("_finalize_running_jobs_after_worker_stop: query failed")
        return
    for r in rows or []:
        jid = r.get("id")
        if jid is None:
            continue
        try:
            db.update_job_status(int(jid), "paused", reason_log)
        except Exception as exc:
            logger.debug("finalize job %s to paused: %s", jid, exc)
        try:
            db.reconcile_stale_running_phases_for_jobs(
                [int(jid)],
                error_message=db.GRACEFUL_PAUSE_MSG,
                in_flight_to="not_started",
            )
        except Exception:
            logger.exception("reconcile in-flight rows for job %s", jid)


def _graceful_shutdown_done_value() -> bool:
    import sys

    api_mod = sys.modules.get("modules.api")
    if api_mod is not None and "_graceful_shutdown_done" in api_mod.__dict__:
        return bool(api_mod.__dict__["_graceful_shutdown_done"])
    return _graceful_shutdown_done


def _set_graceful_shutdown_done_value(value: bool) -> None:
    global _graceful_shutdown_done
    _graceful_shutdown_done = value
    import sys

    api_mod = sys.modules.get("modules.api")
    if api_mod is not None:
        api_mod.__dict__["_graceful_shutdown_done"] = value


def _shutdown_hook(name: str):
    """Resolve shutdown helpers from ``modules.api`` when tests monkeypatch there."""
    import sys

    api_mod = sys.modules.get("modules.api")
    if api_mod is not None and hasattr(api_mod, name):
        return getattr(api_mod, name)
    return globals()[name]


def graceful_shutdown_processing(reason: str = "server_shutdown") -> None:
    """Cooperatively stop runners, persist pausable job state, then stop the dispatcher."""
    with _graceful_shutdown_lock:
        if _graceful_shutdown_done_value():
            return
        _set_graceful_shutdown_done_value(True)
    logger.info("Graceful shutdown: %s", reason)
    try:
        if _orchestrator is not None:
            _orchestrator.stop(mode="graceful")
    except Exception:
        logger.exception("orchestrator.stop(graceful) failed")
    for phase in (
        "indexing",
        "metadata",
        "scoring",
        "keywords",
        "clustering",
        "selection",
        "culling",
        "bird_species",
        "bird-species",
    ):
        try:
            _stop_runner_for_phase(phase)
        except Exception:
            logger.exception("stop runner phase %s", phase)
    _shutdown_hook("_join_runner_threads")(per_thread_timeout=3.0)
    try:
        _shutdown_hook("_finalize_running_jobs_after_worker_stop")(reason_log=reason)
    except Exception:
        logger.exception("_finalize_running_jobs_after_worker_stop failed")
    _shutdown_hook("stop_dispatcher")()

