import json
import threading

from modules.job_dispatcher import JobDispatcher
from modules.selection_runner import SelectionRunner


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

    def fake_run_internal(self, input_path, force_rescan, job_id=None):
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


def test_dispatcher_scoring_selector_payload_preserves_none_input_path(monkeypatch):
    scoring_runner = DummyRunner()
    dispatcher = JobDispatcher(scoring_runner=scoring_runner)

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

    dispatcher._tick()

    assert len(scoring_runner.calls) == 1
    args, kwargs = scoring_runner.calls[0]
    assert args[0] is None
    assert args[1] == 77
    assert args[2] is True
    assert kwargs["resolved_image_ids"] == []


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
    assert "source=root" in line
    assert "job_id=4242" in line
