"""
Tier A: fake phase runners for orchestration / queue tests without ML or pipeline imports.

Contract: start_batch -> "Started" | error str; get_status -> (is_running, log, msg, current, total)
or 6-tuple with pipeline depth for scoring-shaped runners; stop() optional.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, List, Optional

from modules import db


class FakePhaseRunner:
    """
    Mimics IndexingRunner-style API: start_batch(input_path, job_id=None, **kwargs).
    Completes the job in a background thread after a short delay.
    """

    def __init__(
        self,
        *,
        delay_s: float = 0.05,
        complete_status: str = "completed",
        fail_message: Optional[str] = None,
        on_start: Optional[Callable[..., Any]] = None,
    ):
        self.delay_s = delay_s
        self.complete_status = complete_status
        self.fail_message = fail_message
        self.on_start = on_start
        self.is_running = False
        self.log_history: List[str] = []
        self.status_message = "Idle"
        self.current_count = 0
        self.total_count = 0
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def get_status(self):
        with self._lock:
            return (
                self.is_running,
                "\n".join(self.log_history),
                self.status_message,
                self.current_count,
                self.total_count,
            )

    def stop(self):
        with self._lock:
            self.log_history.append("stop called")

    def start_batch(self, input_path: str, job_id: int = None, **kwargs: Any) -> str:
        with self._lock:
            if self.is_running:
                return "Error: Already running."
            if job_id is None:
                return "Error: job_id required for FakePhaseRunner."
            self.is_running = True
            self.log_history = ["started"]
            self.status_message = "Running..."
            self.current_count = 0
            self.total_count = 1
            if self.on_start:
                try:
                    self.on_start(input_path, job_id, **kwargs)
                except Exception:
                    pass

        jid = int(job_id)

        # Fail synchronously: a delayed failure in a background thread races the orchestrator,
        # which can mark the job completed before we transition to failed (invalid completed→failed).
        if self.fail_message:
            try:
                db.update_job_status(jid, "failed", self.fail_message)
            finally:
                with self._lock:
                    self.status_message = "Failed"
                    self.log_history.append(self.fail_message)
                    self.is_running = False
                    self.current_count = 1
            return "Started"

        def _run():
            try:
                time.sleep(self.delay_s)
                db.update_job_status(jid, self.complete_status, "\n".join(self.log_history))
                with self._lock:
                    self.status_message = "Done"
                    self.log_history.append("done")
            finally:
                with self._lock:
                    self.is_running = False
                    self.current_count = 1

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        return "Started"


class FakeScoringRunner(FakePhaseRunner):
    """Scoring-shaped start_batch(input_path, job_id, skip_existing=False, **kwargs)."""

    def start_batch(
        self,
        input_path: str,
        job_id: int,
        skip_existing: bool = False,
        resolved_image_ids=None,
        target_phases=None,
        **kwargs: Any,
    ) -> str:
        return super().start_batch(input_path, job_id, **kwargs)


class FakeTaggingRunner(FakePhaseRunner):
    """Tagging-shaped start_batch with keyword args."""

    def start_batch(
        self,
        input_path: str,
        job_id: int = None,
        custom_keywords=None,
        overwrite: bool = False,
        generate_captions: bool = False,
        resolved_image_ids=None,
        **kwargs: Any,
    ) -> str:
        if job_id is None:
            return "Error: job_id required for FakeTaggingRunner."
        return super().start_batch(input_path, job_id, **kwargs)


class FakeClusteringRunner(FakePhaseRunner):
    def start_batch(
        self,
        input_path: str,
        threshold=None,
        time_gap=None,
        force_rescan: bool = False,
        job_id: int = None,
        resolved_image_ids=None,
        **kwargs: Any,
    ) -> str:
        if job_id is None:
            return "Error: job_id required for FakeClusteringRunner."
        return super().start_batch(input_path, job_id, **kwargs)


class FakeSelectionRunner(FakePhaseRunner):
    """Selection/culling-shaped start_batch(input_path, job_id, force_rescan=False)."""

    def start_batch(
        self,
        input_path: str,
        job_id: int = None,
        force_rescan: bool = False,
        **kwargs: Any,
    ) -> str:
        if job_id is None:
            return "Error: job_id required for FakeSelectionRunner."
        return super().start_batch(input_path, job_id, **kwargs)


class FakeBirdSpeciesRunner(FakePhaseRunner):
    """Bird-species-shaped start_batch."""

    def start_batch(
        self,
        input_path: str,
        job_id: int = None,
        candidate_species=None,
        threshold: float = 0.1,
        top_k: int = 3,
        overwrite: bool = False,
        resolved_image_ids=None,
        **kwargs: Any,
    ) -> str:
        if job_id is None:
            return "Error: job_id required for FakeBirdSpeciesRunner."
        return super().start_batch(input_path, job_id, **kwargs)
