import json
import logging
import threading
from typing import Any, Dict, List, Optional

import time

from modules import db
from modules.run_modes import CANONICAL_RUN_MODE, normalize_run_mode, resolve_run_mode_flags

logger = logging.getLogger(__name__)


class JobDispatcher:
    """Dispatches queued jobs and ensures only one active job starts at a time."""

    def __init__(
        self,
        scoring_runner=None,
        tagging_runner=None,
        clustering_runner=None,
        selection_runner=None,
        bird_species_runner=None,
        indexing_runner=None,
        metadata_runner=None,
        maintenance_runner=None,
        poll_interval: float = 1.0,
    ):
        self.scoring_runner = scoring_runner
        self.tagging_runner = tagging_runner
        self.clustering_runner = clustering_runner
        self.selection_runner = selection_runner
        self.bird_species_runner = bird_species_runner
        self.indexing_runner = indexing_runner
        self.metadata_runner = metadata_runner
        self.maintenance_runner = maintenance_runner
        self.poll_interval = max(0.2, float(poll_interval or 1.0))
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._dispatch_lock = threading.Lock()
        self._last_busy_logged: float = 0

    def set_runners(self, scoring_runner=None, tagging_runner=None, clustering_runner=None, selection_runner=None, bird_species_runner=None, indexing_runner=None, metadata_runner=None, maintenance_runner=None):
        self.scoring_runner = scoring_runner
        self.tagging_runner = tagging_runner
        self.clustering_runner = clustering_runner
        self.selection_runner = selection_runner
        self.bird_species_runner = bird_species_runner
        self.indexing_runner = indexing_runner
        self.metadata_runner = metadata_runner
        self.maintenance_runner = maintenance_runner

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="job-dispatcher", daemon=True)
        self._thread.start()
        logger.info("JobDispatcher started")

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        logger.info("JobDispatcher stopped")

    def get_state(self) -> Dict[str, Any]:
        queue = db.get_queued_jobs(limit=200)
        active = self._get_active_runner()
        return {
            "queue": queue,
            "queue_size": len(queue),
            "active_runner": active,
            "is_dispatcher_running": bool(self._thread and self._thread.is_alive()),
        }

    def _run_loop(self):
        while not self._stop_event.is_set():
            try:
                self._tick()
            except Exception as exc:
                logger.exception("JobDispatcher tick failed: %s", exc)
            self._stop_event.wait(self.poll_interval)

    def tick_for_tests(self) -> None:
        """Single dispatch iteration for unit tests (does not require start())."""
        self._tick()

    def _tick(self):
        start_tick = time.perf_counter()
        if self._any_runner_busy():
            # Only log busy state every 30 seconds to avoid spam
            now = time.time()
            if now - getattr(self, '_last_busy_logged', 0) > 30:
                logger.debug(f"[DISPATCHER] Skipping tick: runner '{self._get_active_runner()}' is currently busy.")
                self._last_busy_logged = now
            return

        idle = False
        with self._dispatch_lock:
            if self._any_runner_busy():
                return
            
            queue_depth = db.get_queued_jobs_count()
            if queue_depth > 0:
                logger.debug(f"[DISPATCHER] Found {queue_depth} jobs in queue. Attempting dequeue.")
                
            job = db.dequeue_next_job()
            if job:
                payload = self._parse_queue_payload(job)
                started, err = self._start_job(job, payload)
                if not started:
                    reason = err or "Dispatcher failed to start job (unknown reason)"
                    logger.warning("Dispatcher: job %s failed to start: %s", job.get("id"), reason)
                    db.update_job_status(job["id"], "failed", reason)
                return

            cont = db.get_running_job_for_phase_continuation()
            if not cont:
                idle = True
            else:
                phase_code = (cont.pop("_active_phase_code", None) or "").strip().lower()
                if not phase_code:
                    logger.warning("Dispatcher: continuation job %s missing active phase code", cont.get("id"))
                else:
                    payload = self._parse_queue_payload(cont)
                    started, err = self._start_job(cont, payload, phase_override=phase_code)
                    if not started:
                        reason = err or "Dispatcher failed to continue multi-phase job (unknown reason)"
                        logger.warning("Dispatcher: continuation job %s failed to start: %s", cont.get("id"), reason)
                        db.update_job_status(cont["id"], "failed", reason)

        # When the pipeline is fully idle, top up the queue from the durable
        # auto-drive loop (no-op unless a drive is active). Done outside the
        # dispatch lock because the bucket scan can be heavy on large libraries.
        if idle:
            self._maybe_drive_tick()

        tick_duration = time.perf_counter() - start_tick
        if tick_duration > 1.0:
            logger.warning(f"[DISPATCHER] Slow tick detected: {tick_duration:.3f}s")

    def _maybe_drive_tick(self) -> None:
        """Advance the durable auto-drive loop. Never raises (background thread)."""
        try:
            from modules import runs_autodrive

            runs_autodrive.drive_tick()
        except Exception:
            logger.debug("Dispatcher: drive_tick failed", exc_info=True)

    @staticmethod
    def _parse_queue_payload(job: Dict[str, Any]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        raw_payload = job.get("queue_payload")
        if raw_payload:
            try:
                parsed = json.loads(raw_payload)
                if isinstance(parsed, str):
                    parsed = json.loads(parsed)
                payload = parsed if isinstance(parsed, dict) else {}
            except Exception:
                logger.warning("Invalid queue payload for job %s", job.get("id"))
        return payload

    @staticmethod
    def _run_mode_flags(payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            run_mode = normalize_run_mode(payload.get("run_mode"))
        except ValueError:
            run_mode = CANONICAL_RUN_MODE
        return resolve_run_mode_flags(run_mode)

    @staticmethod
    def _fresh_payload(job_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            row = db.get_job_by_id(job_id)
            if row:
                return JobDispatcher._parse_queue_payload(row)
        except Exception:
            logger.debug("Failed to reload queue_payload for job %s", job_id, exc_info=True)
        return payload

    @staticmethod
    def _persist_stage_queue(
        job_id: int,
        payload: Dict[str, Any],
        queue_key: str,
        image_ids: List[int],
    ) -> Dict[str, Any]:
        stage_queues = dict(payload.get("resolved_image_ids_by_stage") or {})
        stage_queues[queue_key] = list(image_ids)
        if queue_key == "culling":
            stage_queues["clustering"] = list(image_ids)
        payload = dict(payload)
        payload["resolved_image_ids_by_stage"] = stage_queues
        payload["resolved_image_ids"] = list(image_ids)
        try:
            db.update_job_payload(job_id, json.dumps(payload))
        except Exception:
            logger.debug("Failed to persist stage queue for job %s phase %s", job_id, queue_key, exc_info=True)
        return payload

    def _jit_replan_phase(
        self,
        job_id: int,
        payload: Dict[str, Any],
        queue_key: str,
        input_path: str,
    ) -> tuple[Dict[str, Any], Optional[List[int]], bool]:
        """Recompute phase queue from DB truth. Returns (payload, ids, skip_phase)."""
        from modules.phase_work_claims import claim_image_phases, mark_claims_running
        from modules.run_phase_planner import plan_phase

        payload = self._fresh_payload(job_id, payload)
        scope_paths = payload.get("scope_paths")
        if not isinstance(scope_paths, list) or not scope_paths:
            scope_paths = [payload.get("input_path") or input_path]
        scope_paths = [str(p) for p in scope_paths if p]

        planned = plan_phase(scope_paths, queue_key, job_id=job_id, dry_run=False)
        claim_result = claim_image_phases(job_id, queue_key, planned)
        scoped = list(claim_result.get("claimed") or [])
        if scoped:
            mark_claims_running(job_id, queue_key, scoped)
        payload = self._persist_stage_queue(job_id, payload, queue_key, scoped)
        skip_phase = len(scoped) == 0
        return payload, scoped, skip_phase

    @staticmethod
    def _skip_empty_phase(job_id: int, phase_code: str) -> str:
        try:
            db.set_job_phase_state(job_id, phase_code, "completed")
            db.update_job_status(job_id, "completed", f"Phase {phase_code}: no stale/missing work")
        except Exception:
            logger.exception("Failed to skip empty phase job_id=%s phase=%s", job_id, phase_code)
        return "PhaseSkipped"

    @staticmethod
    def _make_collector(job_id: int, phase_code: str, payload: Dict[str, Any]):
        """Create a ReportCollector for a phase dispatch. Returns None on failure."""
        try:
            from modules.report_collector import ReportCollector
            run_mode = (payload.get("run_mode") or "").strip()
            return ReportCollector(job_id, phase_code, run_mode)
        except Exception:
            logger.debug("Failed to create ReportCollector for job %s phase %s", job_id, phase_code, exc_info=True)
            return None

    @staticmethod
    def _compute_phase_scope(payload: Dict[str, Any], resolved: Optional[List[int]]) -> tuple:
        """Return ``(in_scope, targeted)`` derived from ``payload['scope_paths']``
        with a fallback to ``len(resolved)``. Mirrors the scoring dispatch's
        scope computation so all phases use the same accounting (see issue #159).
        """
        total_in_scope = 0
        scope_paths = payload.get("scope_paths")
        if isinstance(scope_paths, list) and scope_paths:
            for p in scope_paths:
                try:
                    total_in_scope += db.get_image_count(folder_path=str(p))
                except Exception:
                    pass
        if total_in_scope == 0:
            total_in_scope = len(resolved) if resolved else 0
        targeted = len(resolved) if resolved else total_in_scope
        return total_in_scope, targeted

    @staticmethod
    def _seed_phase_scope(
        job_id: int,
        phase_code: str,
        payload: Dict[str, Any],
        resolved: Optional[List[int]],
    ) -> None:
        """Push `job_phases.images_in_scope/targeted` for `job_id`/`phase_code` immediately.

        This is the issue #159 lightweight fix: dispatch branches whose runners do
        not yet accept a ``report_collector`` (tag, cluster, selection) can call this
        before invoking ``start_batch`` so the Runs UI denominator is visible from
        phase start. Best-effort — failures are logged and swallowed.

        The collector is short-lived and discarded after seeding; per-image
        progress (record_after / record_skip / record_failure) is NOT recorded
        here. Wiring those callbacks into the runners is left for Stage B.
        """
        try:
            collector = JobDispatcher._make_collector(job_id, phase_code, payload)
            if collector is None:
                return
            in_scope, targeted = JobDispatcher._compute_phase_scope(payload, resolved)
            collector.set_scope_counts(in_scope=in_scope, targeted=targeted)
        except Exception:
            logger.debug(
                "Failed to seed job_phases scope for job %s phase %s",
                job_id, phase_code, exc_info=True,
            )

    def _start_job(self, job: Dict[str, Any], payload: Dict[str, Any], phase_override: Optional[str] = None) -> tuple:
        """Try to start the job. Returns (success: bool, error_msg: str|None)."""
        phase = (phase_override or job.get("job_type") or "").lower()
        job_id = int(job["id"])
        input_path = job.get("input_path")

        # Multi-phase pipeline jobs keep ``job_type`` stable (e.g. "pipeline"); the
        # actual phase to dispatch lives in ``job_phases``. Resolve it from the
        # first queued/running job_phases row when no override is supplied.
        if phase_override is None and phase in ("pipeline", "ui_pipeline"):
            try:
                rows = db.get_job_phases(job_id) or []
            except Exception:
                rows = []
            resolved = next(
                (
                    (r.get("phase_code") or "").strip().lower()
                    for r in rows
                    if (r.get("state") or "").strip().lower() in ("queued", "running", "pending")
                ),
                "",
            )
            if resolved:
                phase = resolved

        if phase_override:
            try:
                from modules.run_log import emit_run_log

                emit_run_log(
                    job_id,
                    f"Continuing multi-phase run with phase: {phase}",
                    "INFO",
                    phase=phase,
                    step="dispatcher",
                )
            except Exception:
                pass

        runner_map = {
            "indexing": ("indexing_runner", self.indexing_runner),
            "metadata": ("metadata_runner", self.metadata_runner),
            "score": ("scoring_runner", self.scoring_runner),
            "scoring": ("scoring_runner", self.scoring_runner),
            "tag": ("tagging_runner", self.tagging_runner),
            "tagging": ("tagging_runner", self.tagging_runner),
            "keywords": ("tagging_runner", self.tagging_runner),
            "cluster": ("clustering_runner", self.clustering_runner),
            "clustering": ("clustering_runner", self.clustering_runner),
            "selection": ("selection_runner", self.selection_runner),
            "culling": ("selection_runner", self.selection_runner),
            "bird_species": ("bird_species_runner", self.bird_species_runner),
            "bird-species": ("bird_species_runner", self.bird_species_runner),
            "maintenance": ("maintenance_runner", self.maintenance_runner),
        }

        entry = runner_map.get(phase)
        if entry is None:
            logger.warning("Unknown queued job_type=%s for job_id=%s", phase, job_id)
            return False, f"Unknown job type: {phase}"

        runner_name, runner = entry
        if not runner:
            return False, f"No runner available for '{phase}' (runner '{runner_name}' is not initialized)"

        logger.info(f"[DISPATCHER] Starting job {job_id} on {runner_name} (phase: {phase}, path: {input_path})")
        
        try:
            result = self._dispatch_to_runner(phase, runner, job_id, input_path, payload)
        except Exception as exc:
            logger.exception("Runner %s raised during start for job %s", runner_name, job_id)
            return False, f"Runner '{runner_name}' raised: {exc}"

        if result in ("Started", "PhaseSkipped"):
            return True, None
        return False, f"Runner '{runner_name}' returned: {result}"

    def _dispatch_to_runner(self, phase: str, runner, job_id: int, input_path: str, payload: Dict[str, Any]) -> str:
        """Call the appropriate start_batch method on the runner. Returns the result string."""
        phase_key = str(phase).strip().lower()
        phase_alias = {
            "score": "scoring",
            "tagging": "keywords",
            "tag": "keywords",
            "selection": "culling",
            "cluster": "clustering",
        }
        queue_key = phase_alias.get(phase_key, phase_key)
        payload = self._fresh_payload(job_id, payload)
        try:
            run_mode = normalize_run_mode(payload.get("run_mode"))
        except ValueError:
            run_mode = CANONICAL_RUN_MODE

        if run_mode == CANONICAL_RUN_MODE:
            payload, scoped_resolved, skip_phase = self._jit_replan_phase(
                job_id, payload, queue_key, input_path or "",
            )
            if skip_phase:
                logger.info(
                    "[DISPATCHER] skip empty phase job_id=%s phase=%s (no stale/missing work)",
                    job_id,
                    queue_key,
                )
                return self._skip_empty_phase(job_id, queue_key)
        else:
            stage_queues = payload.get("resolved_image_ids_by_stage")
            scoped_resolved = payload.get("resolved_image_ids")
            source = "root"
            if isinstance(stage_queues, dict):
                per_stage = stage_queues.get(queue_key)
                if isinstance(per_stage, list):
                    scoped_resolved = per_stage
                    source = "by_stage"
                else:
                    source = "by_stage_missing"

        source = "jit_planner" if run_mode == CANONICAL_RUN_MODE else source
        # Structured log so multi-stage WorkflowRun handoffs are visible without
        # relying on runner-side log_history (see issue #156).
        logger.info(
            "[DISPATCHER] dispatch job_id=%s phase=%s queue_key=%s resolved_count=%d source=%s "
            "input_path=%r has_stage_queues=%s",
            job_id,
            phase_key,
            queue_key,
            len(scoped_resolved or []) if isinstance(scoped_resolved, list) else -1,
            source,
            payload.get("input_path", input_path),
            isinstance(payload.get("resolved_image_ids_by_stage"), dict),
        )

        mode_flags = self._run_mode_flags(payload)

        if phase_key == "indexing":
            report_collector = self._make_collector(job_id, "indexing", payload)
            return runner.start_batch(
                payload.get("input_path", input_path),
                job_id=job_id,
                skip_existing=bool(mode_flags["skip_existing"]),
                resolved_image_ids=scoped_resolved,
                report_collector=report_collector,
            )

        if phase_key == "metadata":
            report_collector = self._make_collector(job_id, "metadata", payload)
            return runner.start_batch(
                payload.get("input_path", input_path),
                job_id=job_id,
                skip_existing=bool(mode_flags["skip_existing"]),
                resolved_image_ids=scoped_resolved,
                report_collector=report_collector,
            )

        if phase_key in ("score", "scoring"):
            skip_existing_val = bool(mode_flags["skip_existing"])
            resolved = scoped_resolved
            run_mode_val = (payload.get("run_mode") or CANONICAL_RUN_MODE).strip()
            report_collector = None
            if resolved and bool(mode_flags.get("fix_incomplete_stages")):
                skip_existing_val = False

            # Build ReportCollector with before-snapshots for resolved IDs.
            try:
                from modules.report_collector import (
                    ReportCollector,
                    extract_score_snapshot,
                    describe_incomplete_fields,
                )
                report_collector = ReportCollector(job_id, "scoring", run_mode_val)
                if resolved:
                    # Batch-query current scores for before-snapshot capture.
                    # Per-model values live in ``image_model_scores`` (migration
                    # 0016) and are overlaid into the row dict below.
                    placeholders = ",".join("?" * len(resolved))
                    rows = db.get_connector().query(
                        f"""
                        SELECT id, score, score_general, score_technical, score_aesthetic,
                               rating, label
                        FROM images WHERE id IN ({placeholders})
                        """,
                        tuple(resolved),
                    )
                    try:
                        ims_map = db.get_batch_image_model_scores(resolved, include_shadow=False)
                    except Exception:
                        ims_map = {}
                    for r in rows or []:
                        img_id = int(r["id"])
                        entries = ims_map.get(img_id) or {}
                        for name in ("spaq", "ava", "koniq", "paq2piq", "liqe"):
                            entry = entries.get(name)
                            if entry and entry.get("status") == "success":
                                val = entry.get("normalized")
                                if val is None:
                                    val = entry.get("raw_score")
                                if val is not None:
                                    r[f"score_{name}"] = val
                        snapshot = extract_score_snapshot(r)
                        reason = describe_incomplete_fields(r)
                        report_collector.record_before(img_id, snapshot, reason)
                # Scope: total images under paths; targeted = resolved set size.
                total_in_scope = 0
                scope_paths = payload.get("scope_paths")
                if isinstance(scope_paths, list) and scope_paths:
                    for p in scope_paths:
                        try:
                            total_in_scope += db.get_image_count(folder_path=str(p))
                        except Exception:
                            pass
                if total_in_scope == 0:
                    total_in_scope = len(resolved) if resolved else 0
                report_collector.set_scope_counts(
                    in_scope=total_in_scope,
                    targeted=len(resolved) if resolved else total_in_scope,
                )
            except Exception:
                logger.debug("Failed to create scoring ReportCollector for job %s", job_id, exc_info=True)

            return runner.start_batch(
                payload.get("input_path", input_path),
                job_id,
                skip_existing_val,
                resolved_image_ids=resolved,
                target_phases=payload.get("target_phases"),
                report_collector=report_collector,
            )

        if phase_key in ("tag", "tagging", "keywords"):
            report_collector = self._make_collector(job_id, "keywords", payload)
            # seed job_phases scope so the Runs UI denominator shows immediately, and
            if report_collector is not None:
                try:
                    in_scope, targeted = self._compute_phase_scope(payload, scoped_resolved)
                    report_collector.set_scope_counts(in_scope=in_scope, targeted=targeted)
                except Exception:
                    logger.debug(
                        "Failed to seed job_phases scope for tagging job %s",
                        job_id, exc_info=True,
                    )
            return runner.start_batch(
                payload.get("input_path", input_path),
                job_id=job_id,
                custom_keywords=payload.get("custom_keywords"),
                overwrite=bool(mode_flags["overwrite"]),
                generate_captions=bool(payload.get("generate_captions", False)),
                generate_accessibility=bool(payload.get("generate_accessibility", False)),
                resolved_image_ids=scoped_resolved,
                report_collector=report_collector,
            )

        if phase_key in ("cluster", "clustering"):
            force_rescan = bool(mode_flags["force_rescan"]) or bool(payload.get("force_rescan"))
            # Issue #159 Stage A: seed denominator. Same caveat as tagging above.
            self._seed_phase_scope(job_id, "culling", payload, scoped_resolved)
            return runner.start_batch(
                payload.get("input_path", input_path),
                threshold=payload.get("threshold"),
                time_gap=payload.get("time_gap"),
                force_rescan=force_rescan,
                job_id=job_id,
                resolved_image_ids=scoped_resolved,
            )

        if phase_key in ("selection", "culling"):
            force_rescan = bool(mode_flags["force_rescan"]) or bool(payload.get("force_rescan"))
            logger.debug(
                "[culling] dispatch job_id=%s phase=%s input_path=%r force_rescan=%s resolved=%d",
                job_id,
                phase_key,
                payload.get("input_path", input_path),
                force_rescan,
                len(scoped_resolved or []),
            )
            self._seed_phase_scope(job_id, "culling", payload, scoped_resolved)
            return runner.start_batch(
                payload.get("input_path", input_path),
                job_id=job_id,
                force_rescan=force_rescan,
                resolved_image_ids=scoped_resolved,
            )

        if phase_key in ("bird_species", "bird-species"):
            overwrite = bool(mode_flags["overwrite"]) or bool(payload.get("overwrite"))
            return runner.start_batch(
                payload.get("input_path", input_path),
                job_id=job_id,
                candidate_species=payload.get("candidate_species"),
                threshold=float(payload.get("threshold", 0.1)),
                top_k=int(payload.get("top_k", 3)),
                overwrite=overwrite,
                resolved_image_ids=scoped_resolved,
            )

        if phase == "maintenance":
            act = (payload or {}).get("action", "")
            logger.info(
                "Dispatching maintenance job id=%s action=%r input_path=%r",
                job_id,
                act,
                input_path,
            )
            return runner.start_batch(
                payload.get("input_path", input_path),
                job_id=job_id,
            )

        return f"No dispatch handler for phase '{phase}'"

    def _runner_busy(self, runner) -> bool:
        return bool(runner and getattr(runner, "is_running", False))

    def _any_runner_busy(self) -> bool:
        return any([
            self._runner_busy(self.indexing_runner),
            self._runner_busy(self.metadata_runner),
            self._runner_busy(self.scoring_runner),
            self._runner_busy(self.tagging_runner),
            self._runner_busy(self.clustering_runner),
            self._runner_busy(self.selection_runner),
            self._runner_busy(self.bird_species_runner),
            self._runner_busy(self.maintenance_runner),
        ])

    def _get_active_runner(self) -> Optional[str]:
        if self._runner_busy(self.indexing_runner):
            return "indexing"
        if self._runner_busy(self.metadata_runner):
            return "metadata"
        if self._runner_busy(self.scoring_runner):
            return "scoring"
        if self._runner_busy(self.tagging_runner):
            return "tagging"
        if self._runner_busy(self.clustering_runner):
            return "clustering"
        if self._runner_busy(self.selection_runner):
            return "selection"
        if self._runner_busy(self.bird_species_runner):
            return "bird_species"
        if self._runner_busy(self.maintenance_runner):
            return "maintenance"
        return None
