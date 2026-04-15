"""Unit tests for modules.ui.log_views (no DB)."""

from __future__ import annotations

import pytest


def test_read_log_tail_missing_file(tmp_path):
    from modules.ui.log_views import read_log_tail

    p = tmp_path / "nope.log"
    r = read_log_tail(p, 10)
    assert r["exists"] is False
    assert r["lines"] == []
    assert r["total_lines"] is None
    assert r["error"] is None


def test_read_log_tail_tail_and_total(tmp_path):
    from modules.ui.log_views import read_log_tail

    p = tmp_path / "t.log"
    p.write_text("a\nb\nc\nd\n", encoding="utf-8")
    r = read_log_tail(p, 2)
    assert r["exists"] is True
    assert r["total_lines"] == 4
    assert r["lines"] == ["c", "d"]
    assert r["error"] is None


def test_read_log_tail_empty_file(tmp_path):
    from modules.ui.log_views import read_log_tail

    p = tmp_path / "empty.log"
    p.write_text("", encoding="utf-8")
    r = read_log_tail(p, 10)
    assert r["exists"] is True
    assert r["total_lines"] == 0
    assert r["lines"] == []


def test_read_log_tail_utf8_replace(tmp_path):
    from modules.ui.log_views import read_log_tail

    p = tmp_path / "b.log"
    p.write_bytes(b"ok\n\xff\xfe\n")
    r = read_log_tail(p, 10)
    assert r["exists"] is True
    assert len(r["lines"]) >= 1


def test_clamp_tail_lines():
    from modules.ui.log_views import MAX_LOG_TAIL_LINES, clamp_tail_lines, DEFAULT_LOG_TAIL_LINES

    assert clamp_tail_lines(0) == 1
    assert clamp_tail_lines(50) == 50
    assert clamp_tail_lines(99999) == MAX_LOG_TAIL_LINES
    assert DEFAULT_LOG_TAIL_LINES == 100


def test_build_log_tails_payload_invalid_sources():
    from modules.ui.log_views import build_log_tails_payload

    with pytest.raises(ValueError, match="sources"):
        build_log_tails_payload("invalid", 10)


def test_build_log_tails_payload_webui_only(tmp_path, monkeypatch):
    from modules.ui.log_views import build_log_tails_payload

    w = tmp_path / "webui.log"
    w.write_text("line1\nline2\n", encoding="utf-8")

    monkeypatch.setattr("modules.ui.log_views.resolve_webui_log_path", lambda: w)
    monkeypatch.setattr("modules.ui.log_views.resolve_debug_log_path", lambda: tmp_path / "missing.log")

    p = build_log_tails_payload("webui", 10)
    assert len(p["sources"]) == 1
    assert p["sources"][0]["id"] == "webui"
    assert p["sources"][0]["exists"] is True
    assert "line2" in p["sources"][0]["lines"]


def test_webui_rotation_from_config_defaults():
    from webui import _DEFAULT_LOG_BACKUP_COUNT, _DEFAULT_LOG_MAX_BYTES, _webui_rotation_from_config

    mx, bc = _webui_rotation_from_config({})
    assert mx == _DEFAULT_LOG_MAX_BYTES
    assert bc == _DEFAULT_LOG_BACKUP_COUNT


def test_webui_rotation_from_config_custom():
    from webui import _webui_rotation_from_config

    mx, bc = _webui_rotation_from_config({"system": {"log_max_bytes": 4096, "log_backup_count": 2}})
    assert mx == 4096
    assert bc == 2
