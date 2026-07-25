import json
import logging
import threading
from typing import Any, Dict, List, Optional

import time

from modules import db
from modules.audit import audit_context
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
        tick_continuation: Optional[int] = None
        tick_dequeued: Optional[int] = None
        tick_stale_demotions = 0
        with self._dispatch_lock:
            if self._any_runner_busy():
                return

            busy_runner_keys: List[str] = []
            active_runner = self._get_active_runner()
            if active_runner:
                busy_runner_keys.append(active_runner)

            tick_stale_demotions = len(
                self._reconcile_phantom_job_phases(busy_runner_keys=busy_runner_keys)
            )

            cont = db.get_running_job_for_phase_continuation()
            if cont:
                phase_code = (cont.pop("_active_phase_code", None) or "").strip().lower()
                if not phase_code:
                    logger.warning("Dispatcher: continuation job %s missing active phase code", cont.get("id"))
                else:
                    payload = self._parse_queue_payload(cont)
                    started, err = self._start_job(cont, payload, phase_override=phase_code)
                    tick_continuation = int(cont.get("id"))
                    if not started:
                        reason = err or "Dispatcher failed to continue multi-phase job (unknown reason)"
                        logger.warning("Dispatcher: continuation job %s failed to start: %s", cont.get("id"), reason)
                        db.update_job_status(cont["id"], "failed", reason)
                    self._log_tick_summary(tick_continuation, tick_dequeued, tick_stale_demotions, start_tick)
                    return

            if not self._may_dequeue_new_job():
                idle = True
            else:
                queue_depth = db.get_queued_jobs_count()
                if queue_depth > 0:
                    logger.debug(f"[DISPATCHER] Found {queue_depth} jobs in queue. Attempting dequeue.")

                job = db.dequeue_next_job()
                if job:
                    payload = self._parse_queue_payload(job)
                    started, err = self._start_job(job, payload)
                    tick_dequeued = int(job.get("id"))
                    if not started:
                        reason = err or "Dispatcher failed to start job (unknown reason)"
                        logger.warning("Dispatcher: job %s failed to start: %s", job.get("id"), reason)
                        db.update_job_status(job["id"], "failed", reason)
                    self._log_tick_summary(tick_continuation, tick_dequeued, tick_stale_demotions, start_tick)
                    return

            idle = True

        # When the pipeline is fully idle, top up the queue from the durable
        # auto-drive loop (no-op unless a drive is active). Done outside the
        # dispatch lock because the bucket scan can be heavy on large libraries.
        if idle:
            self._maybe_drive_tick()

        self._log_tick_summary(tick_continuation, tick_dequeued, tick_stale_demotions, start_tick)

    @staticmethod
    def _stale_phase_grace_sec() -> int:
        try:
            from modules.config import get_config_value

            return max(0, int(get_config_value("dispatcher.stale_phase_grace_sec", default=120)))
        except (TypeError, ValueError):
            return 120

    @staticmethod
    def _max_in_flight_jobs() -> int:
        try:
            from modules.config import get_config_value

            return max(1, int(get_config_value("dispatcher.max_in_flight_jobs", default=1)))
        except (TypeError, ValueError):
            return 1

    def _reconcile_phantom_job_phases(self, busy_runner_keys: List[str]) -> list:
        try:
            return db.reconcile_phantom_running_job_phases(
                busy_runner_keys=busy_runner_keys,
                grace_seconds=self._stale_phase_grace_sec(),
            )
        except Exception:
            logger.debug("Dispatcher: phantom phase reconciliation failed", exc_info=True)
            return []

    def _may_dequeue_new_job(self) -> bool:
        try:
            in_flight = db.count_running_pipeline_jobs(exclude_maintenance=True)
        except Exception:
            in_flight = 0
        cap = self._max_in_flight_jobs()
        if in_flight >= cap:
            logger.debug(
                "[DISPATCHER] Deferring dequeue: %s running pipeline job(s) (cap=%s)",
                in_flight,
                cap,
            )
            return False
        return True

    @staticmethod
    def _log_tick_summary(
        continuation: Optional[int],
        dequeued: Optional[int],
        stale_demotions: int,
        start_tick: float,
    ) -> None:
        tick_duration = time.perf_counter() - start_tick
        if continuation is not None or dequeued is not None or stale_demotions:
            logger.info(
                "[DISPATCHER] tick continuation=%s dequeued=%s stale_demotions=%s duration=%.3fs",
                continuation,
                dequeued,
                stale_demotions,
                tick_duration,
            )
        elif tick_duration > 1.0:
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
        """Mark an empty phase completed without completing later stages.

        ``set_job_phase_state(..., completed)`` advances the next pending phase to
        ``running``. Calling ``update_job_status(..., completed)`` afterward would
        incorrectly complete that newly-running next phase (see multi-phase sync in
        ``db.update_job_status``). Keep the job ``running`` when phases remain so
        the dispatcher continuation tick can start the next stage.
        """
        log_msg = f"Phase {phase_code}: no stale/missing work"
        try:
            db.set_job_phase_state(job_id, phase_code, "completed")
            phases = db.get_job_phases(job_id) or []
            terminal = {"completed", "skipped", "canceled", "cancelled"}
            remaining = [
                p for p in phases
                if (p.get("state") or "").strip().lower() not in terminal
            ]
            if remaining:
                active = next(
                    (
                        p for p in remaining
                        if (p.get("state") or "").strip().lower() == "running"
                    ),
                    remaining[0],
                )
                db.update_job_status(
                    job_id,
                    "running",
                    log_msg,
                    current_phase=active.get("phase_code"),
                    next_phase_index=int(active.get("phase_order") or 0),
                    runner_state="running",
                )
            else:
                db.update_job_status(job_id, "completed", log_msg)
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
    def _folder_scoped_payload(payload: Dict[str, Any]) -> bool:
        scope_paths = payload.get("scope_paths")
        if isinstance(scope_paths, list) and any(str(p).strip() for p in scope_paths):
            return True
        ip = (payload.get("input_path") or "").strip()
        return bool(ip) and not ip.startswith("SELECTOR_")

    @staticmethod
    def _explicit_stage_resolved_ids(payload: Dict[str, Any], queue_key: str) -> Optional[List[int]]:
        """Return pre-resolved image IDs when the job has no folder scope (selector API)."""
        stage_queues = payload.get("resolved_image_ids_by_stage")
        if isinstance(stage_queues, dict):
            per_stage = stage_queues.get(queue_key)
            if isinstance(per_stage, list):
                if len(per_stage) == 0 and JobDispatcher._folder_scoped_payload(payload):
                    return None
                return [int(i) for i in per_stage if i is not None]

        root = payload.get("resolved_image_ids")
        if not isinstance(root, list) or not root:
            return None

        ip = (payload.get("input_path") or "").strip()
        if ip and not ip.startswith("SELECTOR_"):
            return None
        scope_paths = payload.get("scope_paths")
        if isinstance(scope_paths, list) and any(str(p).strip() for p in scope_paths):
            return None
        return [int(i) for i in root if i is not None]

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
            # Bind run/phase/source so synchronous DB writes during dispatch land
            # in auditlog with correlation. Note: contextvars do not propagate
            # into runner worker threads — thread-spawning runners still record
            # thread_name and any explicit run_id (e.g. job lifecycle / phases).
            with audit_context(run_id=job_id, phase_code=phase, source=runner_name):
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

        # Maintenance jobs are self-scoping (global SQL limits / action handlers).
        # They must not go through JIT replan, which treats input_path as folder scope.
        if phase_key == "maintenance":
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

        try:
            run_mode = normalize_run_mode(payload.get("run_mode"))
        except ValueError:
            run_mode = CANONICAL_RUN_MODE

        explicit_ids = self._explicit_stage_resolved_ids(payload, queue_key)
        if explicit_ids is not None:
            scoped_resolved = explicit_ids
            payload = self._persist_stage_queue(job_id, payload, queue_key, explicit_ids)
            skip_phase = len(explicit_ids) == 0
            source = "explicit_resolved"
            if skip_phase:
                logger.info(
                    "[DISPATCHER] skip empty phase job_id=%s phase=%s (explicit resolved list empty)",
                    job_id,
                    queue_key,
                )
                return self._skip_empty_phase(job_id, queue_key)
        elif run_mode == CANONICAL_RUN_MODE:
            payload, scoped_resolved, skip_phase = self._jit_replan_phase(
                job_id, payload, queue_key, input_path or "",
            )
            source = "jit_planner"
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
                top_k=int(payload.get("top_k", 1)),
                overwrite=overwrite,
                resolved_image_ids=scoped_resolved,
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
