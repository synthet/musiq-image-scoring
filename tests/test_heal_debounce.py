"""Unit tests for the _heal_stale_phase_flags debounce guard (_should_run_heal).

Pure in-process logic — no DB, no markers required.
"""
import time

import modules.db_legacy as db_legacy


def _reset_state():
    with db_legacy._heal_recent_lock:
        db_legacy._heal_recent.clear()


def test_first_call_runs_then_debounced(monkeypatch):
    _reset_state()
    monkeypatch.setattr(db_legacy, "_HEAL_DEBOUNCE_SECONDS", 5.0)
    path = "/mnt/d/Photos/Z8/180-600mm/2026/2026-05-24"
    # First call for a folder runs.
    assert db_legacy._should_run_heal(path) is True
    # Immediate repeat (concurrent/duplicate force_refresh) is suppressed.
    assert db_legacy._should_run_heal(path) is False
    assert db_legacy._should_run_heal(path) is False


def test_distinct_folders_independent(monkeypatch):
    _reset_state()
    monkeypatch.setattr(db_legacy, "_HEAL_DEBOUNCE_SECONDS", 5.0)
    assert db_legacy._should_run_heal("/a") is True
    assert db_legacy._should_run_heal("/b") is True
    assert db_legacy._should_run_heal("/a") is False


def test_runs_again_after_window(monkeypatch):
    _reset_state()
    monkeypatch.setattr(db_legacy, "_HEAL_DEBOUNCE_SECONDS", 0.05)
    path = "/c"
    assert db_legacy._should_run_heal(path) is True
    assert db_legacy._should_run_heal(path) is False
    time.sleep(0.06)
    assert db_legacy._should_run_heal(path) is True


def test_empty_path_never_runs(monkeypatch):
    _reset_state()
    assert db_legacy._should_run_heal("") is False
    assert db_legacy._should_run_heal(None) is False
