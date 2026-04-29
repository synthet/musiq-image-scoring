"""modules.redact_sensitive — key-based redaction."""

from modules.redact_sensitive import redact_json_obj


def test_redacts_nested_secret_keys():
    raw = {"client_secret": "x", "nested": {"refresh_token": "y", "ok": 1}}
    out = redact_json_obj(raw)
    assert out["client_secret"] == "<redacted>"
    assert out["nested"]["refresh_token"] == "<redacted>"
    assert out["nested"]["ok"] == 1
