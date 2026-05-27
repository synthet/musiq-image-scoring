"""
Tests for ScoringRunner in modules/scoring.py.

Tests state machine logic, guard conditions, and delegation to DB —
without loading any ML models or touching the real filesystem at scale.

Skipped automatically when ML dependencies (tensorflow, torch) are not
installed — same pattern as test_selector_runner_behavior.py.
"""

import threading
import pytest

try:
    from modules import scoring, db
    from modules.scoring import ScoringRunner
except ImportError as e:
    pytest.skip(f"ML/runner deps not available: {e}", allow_module_level=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _CapturedThread:
    """Replaces threading.Thread — records kwargs but does NOT start."""
    def __init__(self):
        self.target = None
        self.started = False

    def start(self):
        self.started = True


_captured_thread = None


def _fake_thread_factory(target):
    global _captured_thread
    t = _CapturedThread()
    t.target = target
    _captured_thread = t
    return t


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

def test_get_status_initial_returns_idle():
    runner = ScoringRunner()
    result = runner.get_status()
    is_running, log_text, status_message, current, total = result[:5]
    assert is_running is False
    assert status_message == "Idle"
    assert current == 0
    assert total == 0
    assert log_text == ""


# ---------------------------------------------------------------------------
# start_batch guard: already running
# ---------------------------------------------------------------------------

def test_start_batch_returns_error_when_already_running(monkeypatch):
    runner = ScoringRunner()
    runner.is_running = True
    result = runner.start_batch("/some/path", job_id=1)
    assert result == "Error: Already running."


# ---------------------------------------------------------------------------
# start_batch: path not found and no resolved_image_ids
# ---------------------------------------------------------------------------

def test_start_batch_returns_path_not_found_when_path_missing(monkeypatch):
    runner = ScoringRunner()
    monkeypatch.setattr(db, "backup_database", lambda *a, **kw: None)
    result = runner.start_batch("/nonexistent/path", job_id=1)
    assert result == "Path not found"
    assert runner.is_running is False
    assert runner.status_message == "Failed (Path not found)"


# ---------------------------------------------------------------------------
# start_batch: starts thread with resolved_image_ids
# ---------------------------------------------------------------------------

def test_start_batch_starts_thread_when_resolved_ids_provided(monkeypatch, tmp_path):
    runner = ScoringRunner()
    threads = []

    def fake_thread_class(target):
        class _T:
            def start(self_):
                threads.append(True)
        return _T()

    monkeypatch.setattr(threading, "Thread", fake_thread_class)
    monkeypatch.setattr(db, "backup_database", lambda *a, **kw: None)

    result = runner.start_batch(None, job_id=5, resolved_image_ids=[1, 2, 3])
    assert result == "Started"
    assert runner.is_running is True
    assert threads == [True]


# ---------------------------------------------------------------------------
# run_single_image: file not found
# ---------------------------------------------------------------------------

def test_run_single_image_returns_false_for_missing_file():
    runner = ScoringRunner()
    success, message = runner.run_single_image("/nonexistent/image.jpg")
    assert success is False
    assert "File not found" in message


# ---------------------------------------------------------------------------
# fix_image_metadata: file not found
# ---------------------------------------------------------------------------

def test_fix_image_metadata_returns_false_for_missing_file(monkeypatch):
    runner = ScoringRunner()
    monkeypatch.setattr(db, "resolve_canonical_file_path_for_lookup", lambda _p: None)
    success, message = runner.fix_image_metadata("/nonexistent/image.jpg")
    assert success is False
    assert "File not found" in message


# ---------------------------------------------------------------------------
# start_fix_db guard: already running
# ---------------------------------------------------------------------------

def test_start_fix_db_returns_error_when_already_running():
    runner = ScoringRunner()
    runner.is_running = True
    result = runner.start_fix_db(job_id=10)
    assert result == "Error: Already running."


# ---------------------------------------------------------------------------
# stop: does not raise when current_processor is None
# ---------------------------------------------------------------------------

def test_stop_does_not_raise_when_no_processor():
    runner = ScoringRunner()
    runner.current_processor = None
    runner.stop()  # Should not raise


# ---------------------------------------------------------------------------
# stop: sets stop_event on current_processor
# ---------------------------------------------------------------------------

def test_stop_sets_stop_event_on_processor():
    runner = ScoringRunner()

    class _FakeEvent:
        def __init__(self):
            self.set_called = False
        def set(self):
            self.set_called = True

    class _FakeProcessor:
        def __init__(self):
            self.stop_event = _FakeEvent()

    proc = _FakeProcessor()
    runner.current_processor = proc
    runner.stop()
    assert proc.stop_event.set_called is True
