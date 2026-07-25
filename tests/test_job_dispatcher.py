import json
import threading

import pytest

from modules.job_dispatcher import JobDispatcher
from modules.selection_runner import SelectionRunner


@pytest.fixture(autouse=True)
def _stub_jit_replan_without_db(monkeypatch):
    """Unit tests must not require Postgres for JIT replan at phase start."""

    def _stub(self, job_id, payload, queue_key, input_path):
        payload = dict(payload)
        existing = payload.get("resolved_image_ids")
        if isinstance(existing, list):
            scoped = [int(x) for x in existing]
        else:
            scoped = [1]
        payload["resolved_image_ids"] = scoped
        skip_phase = len(scoped) == 0
        return payload, scoped if scoped else None, skip_phase

    monkeypatch.setattr(JobDispatcher, "_jit_replan_phase", _stub)
    monkeypatch.setattr("modules.job_dispatcher.db.update_job_payload", lambda *a, **k: None)
    # Unit tests mock dequeue_next_job; do not reload queue_payload from a live DB row.
    monkeypatch.setattr("modules.job_dispatcher.db.get_job_by_id", lambda job_id: None)
    monkeypatch.setattr(
        "modules.job_dispatcher.db.get_running_job_for_phase_continuation",
        lambda: None,
    )
    monkeypatch.setattr(
        "modules.job_dispatcher.db.reconcile_phantom_running_job_phases",
        lambda **kw: [],
    )
    monkeypatch.setattr(
        "modules.job_dispatcher.db.count_running_pipeline_jobs",
        lambda **kw: 0,
    )


class DummyRunner:
    def __init__(self, is_running=False, result="Started"):
        self.is_running = is_running
        self.result = result
        self.calls = []

    def start_batch(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.result


def test_dispatcher_starts_selection_job(monkeypatch):
    selection_runner = DummyRunner()
    dispatcher = JobDispatcher(selection_runner=selection_runner)

    queued_job = {
        "id": 42,
        "job_type": "selection",
        "input_path": "D:/selection/path",
        "queue_payload": json.dumps({
            "input_path": "D:/selection/path",
            "force_rescan": True,
            "run_mode": "process_all_overwrite",
        }),
    }

    monkeypatch.setattr("modules.job_dispatcher.db.dequeue_next_job", lambda: queued_job)
    failures = []
    monkeypatch.setattr("modules.job_dispatcher.db.update_job_status", lambda *args, **kwargs: failures.append((args, kwargs)))

    dispatcher._tick()

    assert failures == []
    assert len(selection_runner.calls) == 1
    args, kwargs = selection_runner.calls[0]
    assert kwargs["job_id"] == 42
    assert kwargs["force_rescan"] is True


def test_dispatcher_treats_selection_runner_as_busy(monkeypatch):
    selection_runner = DummyRunner(is_running=True)
    dispatcher = JobDispatcher(selection_runner=selection_runner)

    def _should_not_dequeue():
        raise AssertionError("dequeue_next_job should not be called while selection runner is busy")

    monkeypatch.setattr("modules.job_dispatcher.db.dequeue_next_job", _should_not_dequeue)

    assert dispatcher._any_runner_busy() is True
    assert dispatcher._get_active_runner() == "selection"
    dispatcher._tick()


def test_dispatcher_sees_real_selection_runner_busy(monkeypatch):
    """SelectionRunner must expose is_running so JobDispatcher does not double-dispatch culling."""
    hold = threading.Event()

    def fake_run_internal(self, input_path, force_rescan, job_id=None, resolved_image_ids=None):
        hold.wait()

    monkeypatch.setattr(SelectionRunner, "_run_internal", fake_run_internal)

    selection_runner = SelectionRunner()
    dispatcher = JobDispatcher(selection_runner=selection_runner)

    assert dispatcher._any_runner_busy() is False
    assert selection_runner.start_batch("/tmp/fake_scope", job_id=999, force_rescan=False) == "Started"
    assert selection_runner.is_running is True
    assert dispatcher._any_runner_busy() is True
    assert dispatcher._get_active_runner() == "selection"

    hold.set()
    assert selection_runner._thread is not None
    selection_runner._thread.join(timeout=5.0)
    assert selection_runner.is_running is False
    assert dispatcher._any_runner_busy() is False


def test_dispatcher_supports_culling_alias(monkeypatch):
    selection_runner = DummyRunner()
    dispatcher = JobDispatcher(selection_runner=selection_runner)

    queued_job = {
        "id": 55,
        "job_type": "culling",
        "input_path": "D:/culling/path",
        "queue_payload": json.dumps({"force_rescan": False}),
    }

    monkeypatch.setattr("modules.job_dispatcher.db.dequeue_next_job", lambda: queued_job)
    monkeypatch.setattr("modules.job_dispatcher.db.update_job_status", lambda *args, **kwargs: None)

    dispatcher._tick()

    assert len(selection_runner.calls) == 1
    _, kwargs = selection_runner.calls[0]
    assert kwargs["job_id"] == 55
    assert kwargs["force_rescan"] is False


def test_dispatcher_clustering_respects_queue_payload_force_rescan(monkeypatch):
    """POST /api/clustering/start stores force_rescan on queue_payload without run_mode."""
    clustering_runner = DummyRunner()
    dispatcher = JobDispatcher(clustering_runner=clustering_runner)

    queued_job = {
        "id": 1076,
        "job_type": "clustering",
        "input_path": "/mnt/d/Photos/folder",
        "queue_payload": json.dumps({
            "input_path": "/mnt/d/Photos/folder",
            "threshold": 0.15,
            "time_gap": 120,
            "force_rescan": True,
        }),
    }

    monkeypatch.setattr("modules.job_dispatcher.db.dequeue_next_job", lambda: queued_job)
    monkeypatch.setattr("modules.job_dispatcher.db.update_job_status", lambda *args, **kwargs: None)

    dispatcher._tick()

    assert len(clustering_runner.calls) == 1
    args, kwargs = clustering_runner.calls[0]
    assert args[0] == "/mnt/d/Photos/folder"
    assert kwargs["job_id"] == 1076
    assert kwargs["force_rescan"] is True
    assert kwargs["threshold"] == 0.15
    assert kwargs["time_gap"] == 120


def test_dispatcher_bird_species_explicit_selector_ids_bypass_empty_jit(monkeypatch):
    """Selector bird-species jobs must dispatch explicit IDs even when JIT returns empty."""
    bird_runner = DummyRunner()
    dispatcher = JobDispatcher(bird_species_runner=bird_runner)

    def _empty_stub(self, job_id, payload, queue_key, input_path):
        return dict(payload), [], True

    monkeypatch.setattr(JobDispatcher, "_jit_replan_phase", _empty_stub)

    queued_job = {
        "id": 88,
        "job_type": "bird_species",
        "input_path": "SELECTOR_BIRD_SPECIES",
        "queue_payload": json.dumps({
            "input_path": None,
            "resolved_image_ids": [101, 102],
            "resolved_image_ids_by_stage": {"bird_species": [101, 102]},
        }),
    }

    monkeypatch.setattr("modules.job_dispatcher.db.dequeue_next_job", lambda: queued_job)
    monkeypatch.setattr("modules.job_dispatcher.db.update_job_status", lambda *args, **kwargs: None)

    dispatcher._tick()

    assert len(bird_runner.calls) == 1
    _, kwargs = bird_runner.calls[0]
    assert kwargs["job_id"] == 88
    assert kwargs["resolved_image_ids"] == [101, 102]


def test_dispatcher_maintenance_bypasses_empty_jit(monkeypatch):
    """Maintenance jobs must reach MaintenanceRunner even when JIT would return empty."""
    maintenance_runner = DummyRunner()
    dispatcher = JobDispatcher(maintenance_runner=maintenance_runner)

    def _empty_stub(self, job_id, payload, queue_key, input_path):
        return dict(payload), [], True

    monkeypatch.setattr(JobDispatcher, "_jit_replan_phase", _empty_stub)

    queued_job = {
        "id": 4146,
        "job_type": "maintenance",
        "input_path": "Tools: Backfill EXIF Dates (limit=10000)",
        "queue_payload": json.dumps({
            "action": "backfill_exif",
            "limit": 10000,
        }),
    }

    monkeypatch.setattr("modules.job_dispatcher.db.dequeue_next_job", lambda: queued_job)
    monkeypatch.setattr("modules.job_dispatcher.db.update_job_status", lambda *args, **kwargs: None)
    monkeypatch.setattr("modules.job_dispatcher.db.set_job_phase_state", lambda *a, **k: None)

    dispatcher._tick()

    assert len(maintenance_runner.calls) == 1
    _, kwargs = maintenance_runner.calls[0]
    assert kwargs["job_id"] == 4146


def test_dispatcher_scoring_empty_jit_queue_skips_phase(monkeypatch):
    """When JIT replan finds no stale/missing work, scoring is not dispatched."""
    scoring_runner = DummyRunner()
    dispatcher = JobDispatcher(scoring_runner=scoring_runner)

    def _empty_stub(self, job_id, payload, queue_key, input_path):
        return dict(payload), [], True

    monkeypatch.setattr(JobDispatcher, "_jit_replan_phase", _empty_stub)

    queued_job = {
        "id": 77,
        "job_type": "scoring",
        "input_path": "SELECTOR_SCORING",
        "queue_payload": json.dumps({
            "input_path": None,
            "skip_existing": True,
            "resolved_image_ids": [],
        }),
    }

    monkeypatch.setattr("modules.job_dispatcher.db.dequeue_next_job", lambda: queued_job)
    monkeypatch.setattr("modules.job_dispatcher.db.update_job_status", lambda *args, **kwargs: None)
    monkeypatch.setattr("modules.job_dispatcher.db.set_job_phase_state", lambda *a, **k: None)
    monkeypatch.setattr(
        "modules.job_dispatcher.db.get_job_phases",
        lambda job_id: [{"phase_code": "scoring", "state": "completed", "phase_order": 0}],
    )

    dispatcher._tick()

    assert len(scoring_runner.calls) == 0


def test_dispatcher_empty_scoring_advances_to_culling(monkeypatch):
    """Empty scoring must not complete a multi-phase job before culling runs."""
    scoring_runner = DummyRunner()
    selection_runner = DummyRunner()
    dispatcher = JobDispatcher(
        scoring_runner=scoring_runner,
        selection_runner=selection_runner,
    )

    def _empty_stub(self, job_id, payload, queue_key, input_path):
        return dict(payload), [], True

    monkeypatch.setattr(JobDispatcher, "_jit_replan_phase", _empty_stub)

    queued_job = {
        "id": 6518,
        "job_type": "scoring",
        "input_path": "/mnt/d/Photos/Z8/105mm/2026/2026-07-04",
        "queue_payload": json.dumps({
            "input_path": "/mnt/d/Photos/Z8/105mm/2026/2026-07-04",
            "scope_paths": ["/mnt/d/Photos/Z8/105mm/2026/2026-07-04"],
            "run_mode": "process_stale_or_missing",
            "phases": ["scoring", "culling"],
            "target_phases": ["scoring", "culling"],
            "resolved_image_ids_by_stage": {
                "scoring": [],
                "culling": [200772, 200775],
            },
        }),
    }

    status_calls = []
    phase_state = {"scoring": "running", "culling": "pending"}

    def _set_phase(job_id, phase_code, state, **kwargs):
        phase_state[phase_code] = state
        if state == "completed" and phase_code == "scoring":
            phase_state["culling"] = "running"

    def _get_phases(job_id):
        return [
            {"phase_code": "scoring", "state": phase_state["scoring"], "phase_order": 0},
            {"phase_code": "culling", "state": phase_state["culling"], "phase_order": 1},
        ]

    monkeypatch.setattr("modules.job_dispatcher.db.dequeue_next_job", lambda: queued_job)
    monkeypatch.setattr(
        "modules.job_dispatcher.db.update_job_status",
        lambda *args, **kwargs: status_calls.append((args, kwargs)),
    )
    monkeypatch.setattr("modules.job_dispatcher.db.set_job_phase_state", _set_phase)
    monkeypatch.setattr("modules.job_dispatcher.db.get_job_phases", _get_phases)

    dispatcher._tick()

    assert len(scoring_runner.calls) == 0
    assert status_calls, "expected update_job_status after empty scoring skip"
    status_args, status_kwargs = status_calls[-1]
    assert status_args[0] == 6518
    assert status_args[1] == "running"
    assert "no stale/missing work" in (status_args[2] or "")
    assert status_kwargs.get("current_phase") == "culling"
    assert phase_state["scoring"] == "completed"
    assert phase_state["culling"] == "running"

    # Continuation tick should dispatch culling with the pre-resolved image IDs.
    continuation_job = {
        "id": 6518,
        "job_type": "scoring",
        "input_path": "/mnt/d/Photos/Z8/105mm/2026/2026-07-04",
        "queue_payload": queued_job["queue_payload"],
        "_active_phase_code": "culling",
    }
    monkeypatch.setattr("modules.job_dispatcher.db.dequeue_next_job", lambda: None)
    monkeypatch.setattr(
        "modules.job_dispatcher.db.get_running_job_for_phase_continuation",
        lambda: dict(continuation_job),
    )
    monkeypatch.setattr("modules.job_dispatcher.db.get_image_count", lambda **k: 2)

    dispatcher._tick()

    assert len(selection_runner.calls) == 1
    _, kwargs = selection_runner.calls[0]
    assert kwargs.get("job_id") == 6518
    assert kwargs.get("resolved_image_ids") == [200772, 200775]


def test_dispatcher_scoring_fix_incomplete_resolves_image_ids(monkeypatch):
    """fix_incomplete_stages with pre-resolved IDs from upstream repair plan.

    The API layer now runs build_validation_repair_plan and populates
    resolved_image_ids before enqueuing.  The dispatcher just passes them
    through and sets skip_existing=False when fix_incomplete_stages is set.
    """
    scoring_runner = DummyRunner()
    dispatcher = JobDispatcher(scoring_runner=scoring_runner)

    queued_job = {
        "id": 90,
        "job_type": "scoring",
        "input_path": "D:/Photos/batch",
        "queue_payload": json.dumps({
            "input_path": "D:/Photos/batch",
            "skip_existing": True,
            "fix_incomplete_stages": True,
            "resolved_image_ids": [101, 202],
            "scope_paths": ["D:/Photos/batch", "D:/Photos/other"],
        }),
    }

    monkeypatch.setattr("modules.job_dispatcher.db.dequeue_next_job", lambda: queued_job)
    monkeypatch.setattr("modules.job_dispatcher.db.update_job_status", lambda *args, **kwargs: None)

    dispatcher._tick()

    assert len(scoring_runner.calls) == 1
    args, kwargs = scoring_runner.calls[0]
    assert args[0] == "D:/Photos/batch"
    assert args[1] == 90
    assert args[2] is False  # skip_existing overridden to False
    assert kwargs["resolved_image_ids"] == [101, 202]
    assert kwargs["target_phases"] is None


def test_dispatcher_scoring_preserves_target_phases(monkeypatch):
    scoring_runner = DummyRunner()
    dispatcher = JobDispatcher(scoring_runner=scoring_runner)

    queued_job = {
        "id": 88,
        "job_type": "scoring",
        "input_path": "D:/pipeline/path",
        "queue_payload": json.dumps({
            "input_path": "D:/pipeline/path",
            "skip_existing": False,
            "target_phases": ["indexing", "metadata"],
            "run_mode": "process_all_overwrite",
        }),
    }

    monkeypatch.setattr("modules.job_dispatcher.db.dequeue_next_job", lambda: queued_job)
    monkeypatch.setattr("modules.job_dispatcher.db.update_job_status", lambda *args, **kwargs: None)

    dispatcher._tick()

    assert len(scoring_runner.calls) == 1
    args, kwargs = scoring_runner.calls[0]
    assert args[0] == "D:/pipeline/path"
    assert args[1] == 88
    assert args[2] is False
    assert kwargs["target_phases"] == ["indexing", "metadata"]


def test_dispatcher_multi_stage_continuation_preserves_resolved_image_ids(monkeypatch):
    """Issue #156: second-or-later stage must see the same resolved_image_ids
    as the first stage when the workflow payload carries the root ``resolved_image_ids``
    list (no per-stage queue dict). Regression for the silently-zero-scoped stage 1+
    observed in production runs 2365/2393.
    """
    scoring_runner = DummyRunner()
    tagging_runner = DummyRunner()
    dispatcher = JobDispatcher(scoring_runner=scoring_runner, tagging_runner=tagging_runner)

    payload = {
        "input_path": "/mnt/d/Photos/Z8/180-600mm/2026/2026-05-10",
        "workspace_target": "/mnt/d/Photos/Z8/180-600mm/2026/2026-05-10",
        "workflow_template": "custom",
        "stage_codes": ["metadata", "score", "tag", "cluster"],
        "skip_existing": True,
        "resolved_image_ids": [101, 202, 303],
        "selector_preview_count": 3,
    }

    # First stage 0 (metadata) has finished; dispatcher's continuation tick
    # picks up job_phases.state='running' for ``scoring``.
    continuation_job = {
        "id": 2365,
        "job_type": "metadata",  # job_type stays as the originally-queued first op
        "input_path": "/mnt/d/Photos/Z8/180-600mm/2026/2026-05-10",
        "queue_payload": json.dumps(payload),
        "_active_phase_code": "scoring",
    }

    monkeypatch.setattr("modules.job_dispatcher.db.dequeue_next_job", lambda: None)
    monkeypatch.setattr(
        "modules.job_dispatcher.db.get_running_job_for_phase_continuation",
        lambda: dict(continuation_job),
    )
    monkeypatch.setattr("modules.job_dispatcher.db.update_job_status", lambda *a, **k: None)
    # ReportCollector path inside scoring dispatch issues a query; stub it out.
    class _StubConn:
        def query(self, *a, **k):
            return []
    monkeypatch.setattr("modules.job_dispatcher.db.get_connector", lambda: _StubConn())
    monkeypatch.setattr("modules.job_dispatcher.db.get_image_count", lambda **k: 0)

    dispatcher._tick()

    assert len(scoring_runner.calls) == 1
    args, kwargs = scoring_runner.calls[0]
    # ``resolved_image_ids`` is the third positional after input_path/job_id/skip_existing
    # — verify it's the original 3-item list, not None and not empty.
    assert kwargs.get("resolved_image_ids") == [101, 202, 303]


def test_dispatcher_multi_stage_continuation_keywords_preserves_resolved_image_ids(monkeypatch):
    """Same as above but for the ``keywords`` (tag) stage after another phase finished."""
    tagging_runner = DummyRunner()
    dispatcher = JobDispatcher(tagging_runner=tagging_runner)

    payload = {
        "input_path": "/mnt/d/Photos/Z8/180-600mm/2026/2026-05-10",
        "stage_codes": ["cluster", "tag"],
        "resolved_image_ids": [101, 202, 303],
        "skip_existing": False,
    }
    continuation_job = {
        "id": 2393,
        "job_type": "clustering",
        "input_path": "/mnt/d/Photos/Z8/180-600mm/2026/2026-05-10",
        "queue_payload": json.dumps(payload),
        "_active_phase_code": "keywords",
    }

    monkeypatch.setattr("modules.job_dispatcher.db.dequeue_next_job", lambda: None)
    monkeypatch.setattr(
        "modules.job_dispatcher.db.get_running_job_for_phase_continuation",
        lambda: dict(continuation_job),
    )
    monkeypatch.setattr("modules.job_dispatcher.db.update_job_status", lambda *a, **k: None)

    dispatcher._tick()

    assert len(tagging_runner.calls) == 1
    _, kwargs = tagging_runner.calls[0]
    assert kwargs.get("resolved_image_ids") == [101, 202, 303]


def test_dispatcher_logs_resolved_count_at_entry(monkeypatch, caplog):
    """Issue #156: dispatch must emit a structured log line with resolved_count
    so multi-stage handoffs are diagnosable from server logs alone.
    """
    import logging
    caplog.set_level(logging.INFO, logger="modules.job_dispatcher")

    tagging_runner = DummyRunner()
    dispatcher = JobDispatcher(tagging_runner=tagging_runner)

    queued_job = {
        "id": 4242,
        "job_type": "tagging",
        "input_path": "/mnt/d/foo",
        "queue_payload": json.dumps({
            "input_path": "/mnt/d/foo",
            "resolved_image_ids": [1, 2, 3, 4, 5],
        }),
    }
    monkeypatch.setattr("modules.job_dispatcher.db.dequeue_next_job", lambda: queued_job)
    monkeypatch.setattr("modules.job_dispatcher.db.update_job_status", lambda *a, **k: None)

    dispatcher._tick()

    msgs = [r.getMessage() for r in caplog.records if r.name == "modules.job_dispatcher"]
    dispatch_lines = [m for m in msgs if "[DISPATCHER] dispatch" in m and "queue_key=keywords" in m]
    assert dispatch_lines, f"missing structured dispatch log, got: {msgs}"
    line = dispatch_lines[0]
    assert "resolved_count=5" in line
    assert "source=jit_planner" in line
    assert "job_id=4242" in line


# ── Issue #159 Stage A: seed job_phases denominator for tag/cluster/selection ──


def _capture_scope_pushes(monkeypatch):
    """Capture every db.update_job_phase_counters call from any dispatcher seed/finalize."""
    calls = []
    def _capture(job_id, phase_code, *, in_scope, targeted, processed, skipped, failed):
        calls.append({
            "job_id": job_id, "phase_code": phase_code,
            "in_scope": in_scope, "targeted": targeted,
            "processed": processed, "skipped": skipped, "failed": failed,
        })
    monkeypatch.setattr("modules.db.update_job_phase_counters", _capture)
    return calls


def test_dispatcher_seeds_job_phases_scope_for_tagging(monkeypatch):
    """Tagging dispatch must push job_phases.images_in_scope/targeted before runner starts (issue #159)."""
    tagging_runner = DummyRunner()
    dispatcher = JobDispatcher(tagging_runner=tagging_runner)

    queued_job = {
        "id": 7001,
        "job_type": "tagging",
        "input_path": "/mnt/d/foo",
        "queue_payload": json.dumps({
            "input_path": "/mnt/d/foo",
            "resolved_image_ids": [11, 22, 33, 44, 55, 66, 77],
        }),
    }
    monkeypatch.setattr("modules.job_dispatcher.db.dequeue_next_job", lambda: queued_job)
    monkeypatch.setattr("modules.job_dispatcher.db.update_job_status", lambda *a, **k: None)
    monkeypatch.setattr("modules.job_dispatcher.db.get_image_count", lambda **kw: 0)
    pushes = _capture_scope_pushes(monkeypatch)

    dispatcher._tick()

    # Runner was still invoked.
    assert len(tagging_runner.calls) == 1
    # And a denominator push happened before that.
    keywords_pushes = [p for p in pushes if p["phase_code"] == "keywords"]
    assert keywords_pushes, f"expected a job_phases push for keywords, got pushes={pushes}"
    p = keywords_pushes[0]
    assert p["job_id"] == 7001
    # No scope_paths supplied → falls back to resolved set size.
    assert p["in_scope"] == 7
    assert p["targeted"] == 7
    # Stage A: no per-image accounting yet, processed/skipped/failed must be 0.
    assert p["processed"] == 0 and p["skipped"] == 0 and p["failed"] == 0


def test_dispatcher_seeds_job_phases_scope_for_clustering(monkeypatch):
    """Clustering dispatch must push job_phases scope (issue #159)."""
    clustering_runner = DummyRunner()
    dispatcher = JobDispatcher(clustering_runner=clustering_runner)

    queued_job = {
        "id": 7002,
        "job_type": "clustering",
        "input_path": "/mnt/d/foo",
        "queue_payload": json.dumps({
            "input_path": "/mnt/d/foo",
            "resolved_image_ids": [1, 2, 3],
        }),
    }
    monkeypatch.setattr("modules.job_dispatcher.db.dequeue_next_job", lambda: queued_job)
    monkeypatch.setattr("modules.job_dispatcher.db.update_job_status", lambda *a, **k: None)
    monkeypatch.setattr("modules.job_dispatcher.db.get_image_count", lambda **kw: 0)
    pushes = _capture_scope_pushes(monkeypatch)

    dispatcher._tick()

    assert len(clustering_runner.calls) == 1
    culling_pushes = [p for p in pushes if p["phase_code"] == "culling"]
    assert culling_pushes, f"expected a job_phases push for culling, got pushes={pushes}"
    p = culling_pushes[0]
    assert p["job_id"] == 7002
    assert p["in_scope"] == 3
    assert p["targeted"] == 3


def test_dispatcher_seeds_job_phases_scope_for_selection(monkeypatch):
    """Selection dispatch must push job_phases scope (issue #159).

    Selection doesn't filter by resolved_image_ids (folder-only scoping), so when
    scope_paths is supplied it derives in_scope from db.get_image_count; when not,
    it falls back to the resolved set size.
    """
    selection_runner = DummyRunner()
    dispatcher = JobDispatcher(selection_runner=selection_runner)

    queued_job = {
        "id": 7003,
        "job_type": "selection",
        "input_path": "/mnt/d/foo",
        "queue_payload": json.dumps({
            "input_path": "/mnt/d/foo",
            "scope_paths": ["/mnt/d/foo"],
            "resolved_image_ids": [9, 8, 7, 6, 5],
            "run_mode": "process_unprocessed_or_empty",
        }),
    }
    monkeypatch.setattr("modules.job_dispatcher.db.dequeue_next_job", lambda: queued_job)
    monkeypatch.setattr("modules.job_dispatcher.db.update_job_status", lambda *a, **k: None)
    monkeypatch.setattr("modules.job_dispatcher.db.get_image_count", lambda **kw: 42)
    pushes = _capture_scope_pushes(monkeypatch)

    dispatcher._tick()

    assert len(selection_runner.calls) == 1
    culling_pushes = [p for p in pushes if p["phase_code"] == "culling"]
    assert culling_pushes, f"expected a job_phases push for culling (selection), got pushes={pushes}"
    p = culling_pushes[0]
    assert p["job_id"] == 7003
    # scope_paths supplied → in_scope from db.get_image_count.
    assert p["in_scope"] == 42
    # targeted prefers resolved set size when present, even though selection ignores it.
    assert p["targeted"] == 5


def test_dispatcher_seed_phase_scope_swallows_db_failures(monkeypatch):
    """Seeding is best-effort: a DB outage at seed time must not block the runner."""
    tagging_runner = DummyRunner()
    dispatcher = JobDispatcher(tagging_runner=tagging_runner)

    queued_job = {
        "id": 7004,
        "job_type": "tagging",
        "input_path": "/mnt/d/foo",
        "queue_payload": json.dumps({"input_path": "/mnt/d/foo", "resolved_image_ids": [1]}),
    }
    monkeypatch.setattr("modules.job_dispatcher.db.dequeue_next_job", lambda: queued_job)
    monkeypatch.setattr("modules.job_dispatcher.db.update_job_status", lambda *a, **k: None)
    monkeypatch.setattr("modules.job_dispatcher.db.get_image_count", lambda **kw: 0)

    def _boom(*args, **kwargs):
        raise RuntimeError("pool down")
    monkeypatch.setattr("modules.db.update_job_phase_counters", _boom)

    # Should not raise.
    dispatcher._tick()

    # Runner was still invoked despite the seed failing.
    assert len(tagging_runner.calls) == 1


# ── Issue #160: tag dispatch hands a full-lifecycle ReportCollector to the runner ──


def test_dispatcher_tag_passes_collector_to_runner(monkeypatch):
    """Tag dispatch must build a ReportCollector and pass it to TaggingRunner.start_batch
    so per-image record_after/skip/failure increments job_phases counters during the run.
    Stage B for issue #159 (tagging side). See issue #160.
    """
    tagging_runner = DummyRunner()
    dispatcher = JobDispatcher(tagging_runner=tagging_runner)

    queued_job = {
        "id": 8001,
        "job_type": "tagging",
        "input_path": "/mnt/d/foo",
        "queue_payload": json.dumps({
            "input_path": "/mnt/d/foo",
            "resolved_image_ids": [10, 20, 30],
        }),
    }
    pushes = _capture_scope_pushes(monkeypatch)
    monkeypatch.setattr("modules.job_dispatcher.db.dequeue_next_job", lambda: queued_job)
    monkeypatch.setattr("modules.job_dispatcher.db.update_job_status", lambda *a, **k: None)
    monkeypatch.setattr("modules.job_dispatcher.db.get_image_count", lambda **kw: 0)

    dispatcher._tick()

    assert len(tagging_runner.calls) == 1
    _, kwargs = tagging_runner.calls[0]

    # The runner must receive a non-None report_collector.
    rc = kwargs.get("report_collector")
    assert rc is not None, "tag dispatch must pass a ReportCollector to start_batch (#160)"

    # It's the keywords collector (phase_code attribute mirrors phase).
    assert rc.phase_code == "keywords"
    assert rc.job_id == 8001

    # And the dispatcher seeded job_phases.images_in_scope/targeted before dispatch
    # so the Runs UI denominator shows from phase start (#159).
    keywords_pushes = [p for p in pushes if p["phase_code"] == "keywords"]
    assert keywords_pushes, "expected dispatcher to push initial scope for keywords"
    assert keywords_pushes[0]["in_scope"] == 3
    assert keywords_pushes[0]["targeted"] == 3


def test_dispatcher_compute_phase_scope_prefers_scope_paths_over_resolved(monkeypatch):
    """_compute_phase_scope: scope_paths drives in_scope (via db.get_image_count) when supplied."""
    monkeypatch.setattr("modules.job_dispatcher.db.get_image_count", lambda **kw: 42)
    payload = {"scope_paths": ["/mnt/d/foo", "/mnt/d/bar"]}
    # 2 scope paths × 42 each → 84 in_scope; targeted from resolved set size.
    in_scope, targeted = JobDispatcher._compute_phase_scope(payload, resolved=[1, 2, 3])
    assert in_scope == 84
    assert targeted == 3


def test_dispatcher_compute_phase_scope_falls_back_to_resolved_when_no_scope_paths():
    payload = {}
    in_scope, targeted = JobDispatcher._compute_phase_scope(payload, resolved=[1, 2, 3, 4, 5])
    assert in_scope == 5
    assert targeted == 5


def test_dispatcher_compute_phase_scope_handles_empty_resolved():
    """No scope_paths and no resolved → (0, 0). The seed call still happens; UI shows 0/0."""
    payload = {}
    in_scope, targeted = JobDispatcher._compute_phase_scope(payload, resolved=None)
    assert in_scope == 0
    assert targeted == 0


def test_dispatcher_continues_before_dequeue(monkeypatch):
    tagging_runner = DummyRunner()
    dispatcher = JobDispatcher(tagging_runner=tagging_runner)

    def _should_not_dequeue():
        raise AssertionError("dequeue_next_job should not run when continuation is available")

    cont_job = {
        "id": 4162,
        "job_type": "tagging",
        "input_path": "/mnt/d/foo",
        "queue_payload": json.dumps({"resolved_image_ids": [1, 2]}),
        "_active_phase_code": "keywords",
    }

    monkeypatch.setattr("modules.job_dispatcher.db.dequeue_next_job", _should_not_dequeue)
    monkeypatch.setattr(
        "modules.job_dispatcher.db.get_running_job_for_phase_continuation",
        lambda: dict(cont_job),
    )
    monkeypatch.setattr(
        "modules.job_dispatcher.db.reconcile_phantom_running_job_phases",
        lambda **kw: [],
    )
    monkeypatch.setattr("modules.job_dispatcher.db.update_job_status", lambda *a, **k: None)

    dispatcher._tick()

    assert len(tagging_runner.calls) == 1
    _, kwargs = tagging_runner.calls[0]
    assert kwargs["job_id"] == 4162


def test_dispatcher_defers_dequeue_when_in_flight_cap_reached(monkeypatch):
    scoring_runner = DummyRunner()
    dispatcher = JobDispatcher(scoring_runner=scoring_runner)

    dequeue_calls = []

    def _dequeue():
        dequeue_calls.append(True)
        return {
            "id": 99,
            "job_type": "scoring",
            "input_path": "/mnt/d/new",
            "queue_payload": json.dumps({}),
        }

    monkeypatch.setattr("modules.job_dispatcher.db.dequeue_next_job", _dequeue)
    monkeypatch.setattr(
        "modules.job_dispatcher.db.get_running_job_for_phase_continuation",
        lambda: None,
    )
    monkeypatch.setattr(
        "modules.job_dispatcher.db.reconcile_phantom_running_job_phases",
        lambda **kw: [],
    )
    monkeypatch.setattr(
        "modules.job_dispatcher.db.count_running_pipeline_jobs",
        lambda **kw: 2,
    )
    monkeypatch.setattr(
        JobDispatcher,
        "_max_in_flight_jobs",
        staticmethod(lambda: 1),
    )

    dispatcher._tick()

    assert dequeue_calls == []
    assert scoring_runner.calls == []


def test_dispatcher_reconciles_phantom_phases_before_continue(monkeypatch):
    tagging_runner = DummyRunner()
    dispatcher = JobDispatcher(tagging_runner=tagging_runner)
    reconciled = []

    monkeypatch.setattr(
        "modules.job_dispatcher.db.reconcile_phantom_running_job_phases",
        lambda **kw: reconciled.append(kw) or [{"job_id": 1, "phase_code": "keywords"}],
    )
    monkeypatch.setattr(
        "modules.job_dispatcher.db.get_running_job_for_phase_continuation",
        lambda: None,
    )
    monkeypatch.setattr("modules.job_dispatcher.db.dequeue_next_job", lambda: None)
    monkeypatch.setattr(
        "modules.job_dispatcher.db.count_running_pipeline_jobs",
        lambda **kw: 0,
    )

    dispatcher._tick()

    assert reconciled
    assert reconciled[0]["grace_seconds"] == JobDispatcher._stale_phase_grace_sec()


def test_explicit_stage_resolved_ids_empty_list_falls_through_for_folder_scope():
    payload = {
        "scope_paths": ["/mnt/d/foo"],
        "resolved_image_ids_by_stage": {"scoring": []},
    }
    assert JobDispatcher._explicit_stage_resolved_ids(payload, "scoring") is None


def test_explicit_stage_resolved_ids_nonempty_list_for_folder_scope():
    payload = {
        "scope_paths": ["/mnt/d/foo"],
        "resolved_image_ids_by_stage": {"scoring": [10, 11]},
    }
    assert JobDispatcher._explicit_stage_resolved_ids(payload, "scoring") == [10, 11]


def test_dispatcher_jit_replans_when_explicit_scoring_queue_empty(monkeypatch):
    jit_calls = []

    def _jit(self, job_id, payload, queue_key, input_path):
        jit_calls.append(queue_key)
        payload = dict(payload)
        scoped = [1, 2]
        payload["resolved_image_ids"] = scoped
        return payload, scoped, False

    monkeypatch.setattr(JobDispatcher, "_jit_replan_phase", _jit)

    scoring_runner = DummyRunner()
    dispatcher = JobDispatcher(scoring_runner=scoring_runner)
    queued_job = {
        "id": 8001,
        "job_type": "scoring",
        "input_path": "/mnt/d/foo",
        "queue_payload": json.dumps({
            "input_path": "/mnt/d/foo",
            "scope_paths": ["/mnt/d/foo"],
            "run_mode": "process_stale_or_missing",
            "resolved_image_ids_by_stage": {"scoring": []},
        }),
    }
    monkeypatch.setattr("modules.job_dispatcher.db.dequeue_next_job", lambda: queued_job)
    monkeypatch.setattr("modules.job_dispatcher.db.update_job_status", lambda *a, **k: None)
    monkeypatch.setattr("modules.job_dispatcher.db.get_image_count", lambda **kw: 2)

    dispatcher._tick()

    assert jit_calls == ["scoring"]
    assert len(scoring_runner.calls) == 1
    assert scoring_runner.calls[0][1]["resolved_image_ids"] == [1, 2]
