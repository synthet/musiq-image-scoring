"""Unit tests for modules.doctor_cli (no DB required)."""

from __future__ import annotations

import json

import pytest

from modules.doctor_cli import aggregate_status, format_report, redact_json_obj


@pytest.mark.parametrize(
    ("has_fail", "has_warn", "expected"),
    [
        (True, False, "FAIL"),
        (True, True, "FAIL"),
        (False, True, "WARN"),
        (False, False, "PASS"),
    ],
)
def test_aggregate_status(has_fail: bool, has_warn: bool, expected: str) -> None:
    assert aggregate_status(has_fail, has_warn) == expected


def test_format_report_contains_overall() -> None:
    r = format_report({"overall": "PASS", "lines": ["a", "b"]})
    assert "PASS" in r
    assert "a" in r


def test_redact_json_obj_masks_password_fields() -> None:
    raw = {
        "database": {"postgres": {"user": "u", "password": "secret123"}},
        "api_token": "abc",
        "ok": 1,
    }
    out = redact_json_obj(raw)
    assert out["database"]["postgres"]["password"] == "<redacted>"
    assert out["database"]["postgres"]["user"] == "u"
    assert out["api_token"] == "<redacted>"
    assert out["ok"] == 1


def test_redact_json_obj_roundtrip_json() -> None:
    s = json.dumps(redact_json_obj({"client_secret": "x", "nested": {"refresh_token": "y"}}))
    assert "x" not in s and "y" not in s
