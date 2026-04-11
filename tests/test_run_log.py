"""Tests for modules/run_log — level normalization and persistence rules."""

from modules import run_log


def test_normalize_run_log_level_defaults_unknown():
    assert run_log.normalize_run_log_level("") == "INFO"
    assert run_log.normalize_run_log_level("verbose") == "INFO"


def test_normalize_run_log_level_accepts_upper_and_lower():
    assert run_log.normalize_run_log_level("debug") == "DEBUG"
    assert run_log.normalize_run_log_level("ERROR") == "ERROR"


def test_should_persist_skips_debug():
    assert run_log.should_persist_run_log_line("DEBUG") is False
    assert run_log.should_persist_run_log_line("INFO") is True


def test_format_run_log_message_prefixes():
    assert run_log.format_run_log_message("hello", phase="indexing") == "[indexing] hello"
    assert (
        run_log.format_run_log_message("x", phase="scoring", step="prep") == "[scoring] [prep] x"
    )


def test_runner_emit_skips_history_for_debug(monkeypatch):
    calls = []

    def fake_broadcast(rid, msg, level="INFO"):
        calls.append((rid, msg, level))

    monkeypatch.setattr(
        "modules.events.broadcast_run_log_line",
        fake_broadcast,
    )
    hist = []
    run_log.runner_emit(hist, 42, "dbg line", "DEBUG", phase="test")
    assert hist == []
    assert len(calls) == 1 and calls[0][2] == "DEBUG"

    run_log.runner_emit(hist, 42, "info line", "INFO", phase="test")
    assert len(hist) == 1
    assert "[test]" in hist[0]


def test_duration_ms_from_phase_timestamps_datetime_pair():
    import datetime

    from modules.db import _duration_ms_from_phase_timestamps

    a = datetime.datetime(2026, 1, 1, 12, 0, 0)
    b = datetime.datetime(2026, 1, 1, 12, 0, 2)
    assert _duration_ms_from_phase_timestamps(a, b) == 2000


def test_duration_ms_from_phase_timestamps_iso_strings():
    from modules.db import _duration_ms_from_phase_timestamps

    assert (
        _duration_ms_from_phase_timestamps(
            "2026-01-01T12:00:00",
            "2026-01-01T12:00:01",
        )
        == 1000
    )
