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
        "queue_payload": json.dumps({"input_path": "D:/selection/path", "force_rescan": True}),
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
