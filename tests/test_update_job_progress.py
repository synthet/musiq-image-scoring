"""Unit tests for db.update_job_progress (no database)."""

from modules import db


def test_update_job_progress_broadcasts_payload(monkeypatch):
    captured = []

    def fake_broadcast(event_type, payload):
        captured.append((event_type, payload))

    monkeypatch.setattr(db.event_manager, "broadcast_threadsafe", fake_broadcast)
    db.update_job_progress(42, 37)
    assert len(captured) == 1
    et, payload = captured[0]
    assert et == "job_progress"
    assert payload["job_id"] == 42
    assert payload["current"] == 37
    assert payload["total"] == 100
    assert payload["job_type"] == "maintenance"
    assert payload["phase_code"] == "maintenance"


def test_update_job_progress_clamps_percent(monkeypatch):
    captured = []

    def fake_broadcast(event_type, payload):
        captured.append(payload["current"])

    monkeypatch.setattr(db.event_manager, "broadcast_threadsafe", fake_broadcast)
    db.update_job_progress(1, 150)
    assert captured[-1] == 100
    db.update_job_progress(1, -10)
    assert captured[-1] == 0


def test_update_job_progress_invalid_percent_defaults_to_zero(monkeypatch):
    captured = []

    def fake_broadcast(event_type, payload):
        captured.append(payload["current"])

    monkeypatch.setattr(db.event_manager, "broadcast_threadsafe", fake_broadcast)
    db.update_job_progress(1, "not-a-number")
    assert captured[-1] == 0


def test_update_job_progress_swallows_broadcast_errors(monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("ws down")

    monkeypatch.setattr(db.event_manager, "broadcast_threadsafe", boom)
    db.update_job_progress(99, 50)
