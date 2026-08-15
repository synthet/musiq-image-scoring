"""``safe_runner_thread`` must not complete a stage the runner never executed.

Regression for #156. A multi-phase job stays ``running`` after one stage finishes,
so the fallback completion in ``safe_runner_thread`` used to fire a second time and
land on the stage ``db.set_job_phase_state`` had just auto-advanced to ``running`` —
marking it ``completed`` with zero images and no runner involved. Observed on runs
6582/6583/6584: ``metadata`` ran, ``scoring`` completed in 0.1s with
``images_in_scope=0``, ``keywords`` ran, ``culling`` completed in 0.1s.
"""

import pytest

from modules.pipeline import safe_runner_thread

TERMINAL = {"completed", "skipped", "canceled", "cancelled", "failed"}


class FakeJobDb:
    """Minimal stand-in for the multi-phase semantics of ``modules.db``.

    Mirrors the two behaviours that interact to produce the bug:
    ``set_job_phase_state`` auto-advancing the next pending phase
    (``db_legacy.set_job_phase_state``), and ``update_job_status(completed)``
    leaving ``jobs.status`` at ``running`` while stages remain
    (``db_legacy.update_job_status``).
    """

    JOB_TERMINAL_STATES = {"completed", "failed", "canceled", "cancelled", "interrupted"}

    def __init__(self, phase_codes):
        self.phases = [
            {"phase_order": i, "phase_code": code, "state": "running" if i == 0 else "pending"}
            for i, code in enumerate(phase_codes)
        ]
        self.job_status = "running"
        self.update_calls = []

    def get_job(self, job_id):
        return {"id": job_id, "status": self.job_status}

    def get_job_phases(self, job_id):
        return [dict(p) for p in self.phases]

    def update_job_status(self, job_id, status, *args, **kwargs):
        self.update_calls.append(status)
        if status != "completed" or len(self.phases) <= 1:
            self.job_status = status
            return
        running = next((p for p in self.phases if p["state"] == "running"), None)
        if running is not None:
            self._complete_phase(running)
        if all(p["state"] in TERMINAL for p in self.phases):
            self.job_status = "completed"
        else:
            self.job_status = "running"

    def _complete_phase(self, phase):
        phase["state"] = "completed"
        nxt = next(
            (p for p in self.phases if p["phase_order"] > phase["phase_order"] and p["state"] == "pending"),
            None,
        )
        if nxt is not None:
            nxt["state"] = "running"

    def states(self):
        return {p["phase_code"]: p["state"] for p in self.phases}


class FakeRunner:
    def __init__(self):
        self.is_running = True
        self.status_message = "Done"


@pytest.fixture
def fake_db(monkeypatch):
    def _install(phase_codes):
        stub = FakeJobDb(phase_codes)
        monkeypatch.setattr("modules.pipeline.db", stub)
        return stub

    return _install


def test_runner_completion_does_not_consume_next_phase(fake_db):
    """A runner that completes its own stage must leave the next stage running."""
    stub = fake_db(["metadata", "scoring", "keywords", "culling"])
    runner = FakeRunner()

    def run_func():
        # What MetadataRunner._run_batch_internal does at modules/metadata_runner.py:624
        stub.update_job_status(6583, "completed")

    safe_runner_thread(runner, 6583, run_func)

    assert stub.states() == {
        "metadata": "completed",
        "scoring": "running",
        "keywords": "pending",
        "culling": "pending",
    }
    assert stub.update_calls == ["completed"], "fallback must not fire a second completion"
    assert runner.is_running is False


def test_fallback_still_completes_when_runner_records_nothing(fake_db):
    """The safety net must survive: a runner that writes no terminal state."""
    stub = fake_db(["metadata", "scoring"])
    runner = FakeRunner()

    safe_runner_thread(runner, 4242, lambda: None)

    assert stub.update_calls == ["completed"]
    assert stub.states() == {"metadata": "completed", "scoring": "running"}


def test_single_phase_job_unchanged(fake_db):
    """Single-phase jobs still reach a terminal status via the fallback."""
    stub = fake_db(["scoring"])
    runner = FakeRunner()

    safe_runner_thread(runner, 77, lambda: None)

    assert stub.job_status == "completed"
    assert stub.update_calls == ["completed"]


def test_runner_that_already_marked_job_terminal_is_not_recompleted(fake_db):
    """Single-phase runner wrote its own terminal status — no second write."""
    stub = fake_db(["scoring"])
    runner = FakeRunner()

    def run_func():
        stub.update_job_status(77, "completed")

    safe_runner_thread(runner, 77, run_func)

    assert stub.update_calls == ["completed"]


def test_failure_path_marks_job_failed(fake_db):
    stub = fake_db(["metadata", "scoring"])
    runner = FakeRunner()

    def boom():
        raise RuntimeError("kaboom")

    with pytest.raises(RuntimeError):
        safe_runner_thread(runner, 99, boom)

    assert stub.update_calls == ["failed"]
    assert runner.is_running is False
