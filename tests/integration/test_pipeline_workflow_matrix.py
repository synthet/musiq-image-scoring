"""
Tier A: Parametrized pipeline workflow integration matrix.

Database target: ``image_scoring_test`` (PostgreSQL). NEVER production.

Exercises the Cartesian product of:
    phase_plan  x  submit_mode  x  skip_existing  x  intervention

using fake runners (no ML/GPU) + real JobDispatcher + real Postgres job/phase tables.

Env vars:
    PIPELINE_MATRIX_MAX_PLANS   - cap the number of phase plans (default: all valid)
    SKIP_POSTGRES_TESTS=1       - skip entirely if no Postgres
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Tuple

import pytest

from modules import db
from modules.job_dispatcher import JobDispatcher
from tests.support.fake_runners import (
    FakeClusteringRunner,
    FakePhaseRunner,
    FakeScoringRunner,
    FakeSelectionRunner,
    FakeTaggingRunner,
)
from tests.support.pipeline_matrix import (
    INTERVENTIONS,
    _drain_runner_threads,
    build_matrix,
    enqueue_monolithic,
    enqueue_sequential,
    run_dispatcher_until_quiet,
    wait_for_job_status,
)

pytestmark = [pytest.mark.postgres]

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _postgres_clean(postgres_test_session, clean_postgres):
    """Ensure every test starts with empty app tables."""
    yield


def _noop_running_sync(path, job_id, **kwargs):
    """Mirror real runner behavior: mark job as running on start."""
    db.update_job_status(int(job_id), "running")


def _make_dispatcher(
    delay_s: float = 0.03,
    fail_phase: str | None = None,
) -> JobDispatcher:
    """Build a dispatcher wired to fake runners for all 7 phases.

    If ``fail_phase`` is set, the runner for that phase will simulate failure.
    Each runner class matches the start_batch signature the dispatcher expects.
    """
    def _scoring(fail: bool) -> FakeScoringRunner:
        kw = dict(delay_s=delay_s, on_start=_noop_running_sync)
        if fail:
            kw["fail_message"] = "Simulated failure in scoring"
        return FakeScoringRunner(**kw)

    def _tagging(fail: bool) -> FakeTaggingRunner:
        kw = dict(delay_s=delay_s, on_start=_noop_running_sync)
        if fail:
            kw["fail_message"] = "Simulated failure in keywords"
        return FakeTaggingRunner(**kw)

    def _clustering(fail: bool) -> FakeClusteringRunner:
        kw = dict(delay_s=delay_s, on_start=_noop_running_sync)
        if fail:
            kw["fail_message"] = "Simulated failure in clustering"
        return FakeClusteringRunner(**kw)

    def _selection(fail: bool) -> FakeSelectionRunner:
        kw = dict(delay_s=delay_s, on_start=_noop_running_sync)
        if fail:
            kw["fail_message"] = "Simulated failure in culling"
        return FakeSelectionRunner(**kw)

    def _generic(name: str, fail: bool) -> FakePhaseRunner:
        kw = dict(delay_s=delay_s, on_start=_noop_running_sync)
        if fail:
            kw["fail_message"] = f"Simulated failure in {name}"
        return FakePhaseRunner(**kw)

    return JobDispatcher(
        indexing_runner=_generic("indexing", fail_phase == "indexing"),
        metadata_runner=_generic("metadata", fail_phase == "metadata"),
        scoring_runner=_scoring(fail_phase == "scoring"),
        tagging_runner=_tagging(fail_phase == "keywords"),
        clustering_runner=_clustering(fail_phase in ("clustering", "culling")),
        selection_runner=_selection(fail_phase == "culling"),
        poll_interval=5.0,
    )


# ---------------------------------------------------------------------------
# Matrix parametrization
# ---------------------------------------------------------------------------

_RAW_MATRIX = build_matrix(max_plans=0)

# For CI speed, default to a reasonable subset; set env PIPELINE_MATRIX_FULL=1 for all
_MAX_CASES = int(os.environ.get("PIPELINE_MATRIX_MAX_CASES", "80"))
_MATRIX = _RAW_MATRIX[:_MAX_CASES] if _MAX_CASES > 0 else _RAW_MATRIX


@pytest.mark.parametrize(
    "scenario",
    _MATRIX,
    ids=[c["test_id"] for c in _MATRIX],
)
class TestPipelineWorkflowMatrix:
    """Parametrized matrix: each scenario runs the full lifecycle."""

    def test_lifecycle(self, scenario: Dict[str, Any]):
        plan: Tuple[str, ...] = scenario["phase_plan"]
        mode: str = scenario["submit_mode"]
        skip: bool = scenario["skip_existing"]
        intervention: str = scenario["intervention"]
        input_path = f"D:/matrix-test/{'+'.join(plan)}/{mode}"

        if intervention == "none":
            self._run_happy_path(plan, mode, skip, input_path)
        elif intervention == "cancel_queued":
            self._run_cancel_queued(plan, mode, skip, input_path)
        elif intervention == "fail_then_restart":
            self._run_fail_then_restart(plan, mode, skip, input_path)
        elif intervention == "resume_after_interrupt":
            self._run_resume_after_interrupt(plan, mode, skip, input_path)

    # -----------------------------------------------------------------------
    # Intervention: none (happy path)
    # -----------------------------------------------------------------------

    def _run_happy_path(
        self, plan: Tuple[str, ...], mode: str, skip: bool, input_path: str,
    ):
        dispatcher = _make_dispatcher()

        if mode == "monolithic":
            job_id = enqueue_monolithic(input_path, plan, skip_existing=skip)
            run_dispatcher_until_quiet(dispatcher, deadline_s=10.0)

            row = db.get_job(job_id)
            assert row is not None, f"Job {job_id} not found"
            assert (row["status"] or "").lower() == "completed", (
                f"Job {job_id} status={row['status']}, expected completed"
            )

            if len(plan) > 1:
                phases = db.get_job_phases(job_id)
                assert len(phases) == len(plan)
                for p in phases:
                    assert (p["state"] or "").lower() == "completed", (
                        f"Phase {p['phase_code']} state={p['state']}"
                    )
        else:
            job_ids = enqueue_sequential(input_path, plan, skip_existing=skip)
            run_dispatcher_until_quiet(dispatcher, deadline_s=10.0)

            for jid in job_ids:
                row = db.get_job(jid)
                assert row is not None
                assert (row["status"] or "").lower() == "completed", (
                    f"Sequential job {jid} status={row['status']}"
                )

        # Invariant: no jobs left in queue
        assert db.get_queued_jobs(limit=1) == []

    # -----------------------------------------------------------------------
    # Intervention: cancel a queued job before it starts
    # -----------------------------------------------------------------------

    def _run_cancel_queued(
        self, plan: Tuple[str, ...], mode: str, skip: bool, input_path: str,
    ):
        dispatcher = _make_dispatcher(delay_s=0.08)

        if mode == "sequential":
            job_ids = enqueue_sequential(input_path, plan, skip_existing=skip)
            # Cancel the second job while it's still queued
            target = job_ids[1] if len(job_ids) > 1 else job_ids[0]
            result = db.request_cancel_job(target)
            assert result["success"] is True, f"Cancel failed: {result}"

            run_dispatcher_until_quiet(dispatcher, deadline_s=10.0)

            cancelled_row = db.get_job(target)
            assert (cancelled_row["status"] or "").lower() == "cancelled"

            # First job should complete normally
            first_row = db.get_job(job_ids[0])
            assert (first_row["status"] or "").lower() == "completed"

        else:
            # Monolithic: can't cancel a queued phase mid-job through request_cancel_job
            # once the job is dequeued. Instead, enqueue two monolithic jobs and cancel
            # the second one.
            jid1 = enqueue_monolithic(input_path + "/a", plan, skip_existing=skip)
            jid2 = enqueue_monolithic(input_path + "/b", plan, skip_existing=skip)

            result = db.request_cancel_job(jid2)
            assert result["success"] is True

            run_dispatcher_until_quiet(dispatcher, deadline_s=10.0)

            assert (db.get_job(jid1)["status"] or "").lower() == "completed"
            assert (db.get_job(jid2)["status"] or "").lower() == "cancelled"

    # -----------------------------------------------------------------------
    # Intervention: first phase fails, then restart_failed_job
    # -----------------------------------------------------------------------

    def _run_fail_then_restart(
        self, plan: Tuple[str, ...], mode: str, skip: bool, input_path: str,
    ):
        first_phase = plan[0]

        # Phase 1: run with a failing runner for the first phase
        fail_dispatcher = _make_dispatcher(fail_phase=first_phase)

        if mode == "monolithic":
            job_id = enqueue_monolithic(input_path, plan, skip_existing=skip)
            run_dispatcher_until_quiet(fail_dispatcher, deadline_s=8.0)
            row = wait_for_job_status(job_id, "failed", deadline_s=5.0)
            assert (row.get("status") or "").lower() == "failed", (
                f"Expected failed, got {row.get('status')}"
            )

            # Phase 2: restart with a healthy dispatcher
            result = db.restart_failed_job(job_id)
            assert result["success"] is True

            healthy_dispatcher = _make_dispatcher()
            run_dispatcher_until_quiet(healthy_dispatcher, deadline_s=10.0)

            row = db.get_job(job_id)
            assert (row["status"] or "").lower() == "completed"

        else:
            job_ids = enqueue_sequential(input_path, plan, skip_existing=skip)
            run_dispatcher_until_quiet(fail_dispatcher, deadline_s=8.0)

            first_row = wait_for_job_status(job_ids[0], "failed", deadline_s=5.0)
            assert (first_row.get("status") or "").lower() == "failed"

            result = db.restart_failed_job(job_ids[0])
            assert result["success"] is True

            healthy_dispatcher = _make_dispatcher()
            run_dispatcher_until_quiet(healthy_dispatcher, deadline_s=10.0)

            for jid in job_ids:
                row = db.get_job(jid)
                assert (row["status"] or "").lower() == "completed"

    # -----------------------------------------------------------------------
    # Intervention: simulate interrupt mid-pipeline, then resume
    # -----------------------------------------------------------------------

    def _run_resume_after_interrupt(
        self, plan: Tuple[str, ...], mode: str, skip: bool, input_path: str,
    ):
        if len(plan) < 2:
            pytest.skip("resume_after_interrupt needs >= 2 phases")

        if mode == "monolithic":
            # Complete first phase, then simulate interrupt on second
            second_phase = plan[1]
            interrupt_dispatcher = _make_dispatcher(fail_phase=second_phase)

            job_id = enqueue_monolithic(input_path, plan, skip_existing=skip)
            run_dispatcher_until_quiet(interrupt_dispatcher, deadline_s=8.0)

            row = db.get_job(job_id)
            status = (row.get("status") or "").lower()
            # Job should be failed (second phase failed)
            assert status == "failed", f"Expected failed, got {status}"

            # Resume: reset incomplete phases and requeue
            db.resume_job_phases(job_id)
            result = db.restart_failed_job(job_id)
            assert result["success"] is True

            healthy_dispatcher = _make_dispatcher()
            run_dispatcher_until_quiet(healthy_dispatcher, deadline_s=10.0)

            row = db.get_job(job_id)
            assert (row["status"] or "").lower() == "completed"

            phases = db.get_job_phases(job_id)
            for p in phases:
                assert (p["state"] or "").lower() == "completed", (
                    f"Phase {p['phase_code']} state={p['state']}"
                )
        else:
            # Sequential: fail second job, restart it
            job_ids = enqueue_sequential(input_path, plan, skip_existing=skip)

            # Use fail_phase matching the second plan entry
            second_phase = plan[1]
            interrupt_dispatcher = _make_dispatcher(fail_phase=second_phase)
            run_dispatcher_until_quiet(interrupt_dispatcher, deadline_s=8.0)

            # First should complete, second should fail
            assert (db.get_job(job_ids[0])["status"] or "").lower() == "completed"
            second_row = db.get_job(job_ids[1])
            assert (second_row["status"] or "").lower() == "failed"

            result = db.restart_failed_job(job_ids[1])
            assert result["success"] is True

            healthy_dispatcher = _make_dispatcher()
            run_dispatcher_until_quiet(healthy_dispatcher, deadline_s=10.0)

            for jid in job_ids:
                assert (db.get_job(jid)["status"] or "").lower() == "completed"


# ===========================================================================
# Focused non-matrix tests for edge cases
# ===========================================================================

class TestDispatcherEdgeCases:
    """Non-parametrized tests for specific dispatcher / job state edge cases."""

    def test_cancel_running_job_returns_not_supported(self):
        """Running jobs cannot be cancelled via request_cancel_job."""
        dispatcher = _make_dispatcher(delay_s=1.0)

        job_id = enqueue_monolithic("D:/edge/cancel-running", ("indexing",))
        dispatcher.tick_for_tests()
        time.sleep(0.05)

        result = db.request_cancel_job(job_id)
        assert result["success"] is False
        assert result["reason"] == "running_not_supported"

    def test_double_enqueue_monolithic_serializes(self):
        """Two monolithic jobs run sequentially, not in parallel."""
        dispatcher = _make_dispatcher(delay_s=0.04)

        plan = ("indexing", "metadata", "scoring")
        j1 = enqueue_monolithic("D:/edge/serial/a", plan)
        j2 = enqueue_monolithic("D:/edge/serial/b", plan)

        dispatcher.tick_for_tests()
        time.sleep(0.02)

        r1 = db.get_job(j1)
        r2 = db.get_job(j2)
        assert (r1["status"] or "").lower() == "running"
        assert (r2["status"] or "").lower() == "queued"

        run_dispatcher_until_quiet(dispatcher, deadline_s=12.0)

        assert (db.get_job(j1)["status"] or "").lower() == "completed"
        assert (db.get_job(j2)["status"] or "").lower() == "completed"

    def test_restart_failed_increments_retry_count(self):
        dispatcher = _make_dispatcher(fail_phase="scoring")
        job_id = enqueue_monolithic("D:/edge/retry", ("scoring",))
        run_dispatcher_until_quiet(dispatcher, deadline_s=5.0)

        row = db.get_job(job_id)
        assert (row["status"] or "").lower() == "failed"
        assert int(row.get("retry_count") or 0) == 0

        db.restart_failed_job(job_id)

        row = db.get_job(job_id)
        assert (row["status"] or "").lower() == "queued"
        assert int(row.get("retry_count") or 0) == 1

    def test_full_five_phase_monolithic_happy_path(self):
        """Full pipeline: indexing -> metadata -> scoring -> keywords -> culling."""
        dispatcher = _make_dispatcher()
        plan = ("indexing", "metadata", "scoring", "keywords", "culling")
        job_id = enqueue_monolithic("D:/edge/full-pipeline", plan)

        run_dispatcher_until_quiet(dispatcher, deadline_s=15.0)

        row = db.get_job(job_id)
        assert (row["status"] or "").lower() == "completed"

        phases = db.get_job_phases(job_id)
        assert len(phases) == 5
        for p in phases:
            assert (p["state"] or "").lower() == "completed"

    def test_five_phase_sequential_happy_path(self):
        """Full pipeline as 5 sequential single-phase jobs."""
        dispatcher = _make_dispatcher()
        plan = ("indexing", "metadata", "scoring", "keywords", "culling")
        job_ids = enqueue_sequential("D:/edge/full-seq", plan)

        run_dispatcher_until_quiet(dispatcher, deadline_s=15.0)

        for jid in job_ids:
            assert (db.get_job(jid)["status"] or "").lower() == "completed"

    def test_cancel_already_completed_returns_already_finished(self):
        dispatcher = _make_dispatcher()
        job_id = enqueue_monolithic("D:/edge/cancel-done", ("indexing",))
        run_dispatcher_until_quiet(dispatcher, deadline_s=5.0)

        assert (db.get_job(job_id)["status"] or "").lower() == "completed"

        result = db.request_cancel_job(job_id)
        assert result["success"] is False
        assert result["reason"] == "already_finished"

    def test_monolithic_mid_pipeline_fail_preserves_completed_phases(self):
        """When phase 3 fails in a 5-phase job, phases 1-2 stay completed."""
        dispatcher = _make_dispatcher(fail_phase="scoring")
        plan = ("indexing", "metadata", "scoring", "keywords", "culling")
        job_id = enqueue_monolithic("D:/edge/mid-fail", plan)

        run_dispatcher_until_quiet(dispatcher, deadline_s=10.0)

        row = db.get_job(job_id)
        assert (row["status"] or "").lower() == "failed"

        phases = db.get_job_phases(job_id)
        states = {p["phase_code"]: (p["state"] or "").lower() for p in phases}

        # First two phases completed before the failing one
        assert states["indexing"] == "completed"
        assert states["metadata"] == "completed"
        assert states["scoring"] == "failed"
        # Remaining phases: may be pending, running (auto-advanced), or failed
        # depending on how the dispatcher handled the failure cascade
        non_terminal = {"pending", "running", "failed", "queued"}
        assert states["keywords"] in non_terminal, f"keywords: {states['keywords']}"
        assert states["culling"] in non_terminal, f"culling: {states['culling']}"

    def test_empty_queue_tick_is_noop(self):
        """Ticking an empty queue does not crash or create phantom jobs."""
        dispatcher = _make_dispatcher()
        dispatcher.tick_for_tests()
        dispatcher.tick_for_tests()
        assert db.get_queued_jobs(limit=1) == []

    def test_skip_existing_payload_plumbed_through(self):
        """Verify skip_existing lands in queue_payload JSON."""
        import json

        for skip_val in (True, False):
            job_id = enqueue_monolithic(
                f"D:/edge/skip-{skip_val}", ("scoring",), skip_existing=skip_val,
            )
            row = db.get_job(job_id)
            payload = json.loads(row["queue_payload"])
            assert payload["skip_existing"] is skip_val
