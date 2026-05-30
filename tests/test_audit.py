"""Unit tests for modules.audit (no DB / hardware required)."""
from __future__ import annotations

import datetime

from modules import audit


# ---------------------------------------------------------------------------
# Patch builders
# ---------------------------------------------------------------------------
def test_build_insert_patch_skips_none_and_adds_ops():
    patch = audit.build_insert_patch(
        {"status": "queued", "input_path": "/x", "description": None}
    )
    assert {"op": "add", "path": "/status", "value": "queued"} in patch
    assert {"op": "add", "path": "/input_path", "value": "/x"} in patch
    # None values are omitted unless include_none=True.
    assert all(op["path"] != "/description" for op in patch)


def test_build_insert_patch_include_none():
    patch = audit.build_insert_patch({"description": None}, include_none=True)
    assert patch == [{"op": "add", "path": "/description", "value": None}]


def test_build_update_patch_replace_carries_old_value():
    patch = audit.build_update_patch({"score": 1.0}, {"score": 2.0})
    assert patch == [
        {"op": "replace", "path": "/score", "value": 2.0, "oldValue": 1.0}
    ]


def test_build_update_patch_skips_unchanged():
    assert audit.build_update_patch({"a": 1, "b": 2}, {"a": 1, "b": 2}) == []


def test_build_update_patch_add_for_new_key():
    patch = audit.build_update_patch({}, {"label": "keep"})
    assert patch == [{"op": "add", "path": "/label", "value": "keep"}]


def test_build_field_update_patch_empty_when_equal():
    assert audit.build_field_update_patch("rating", 3, 3) == []


def test_path_escaping_rfc6901():
    patch = audit.build_insert_patch({"a/b~c": 1})
    assert patch[0]["path"] == "/a~1b~0c"


def test_datetime_value_is_jsonable():
    dt = datetime.datetime(2026, 5, 29, 12, 0, 0)
    patch = audit.build_field_update_patch("created_at", None, dt)
    assert patch[0]["value"] == dt.isoformat()


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------
def test_audit_context_merges_and_restores():
    assert audit.current_audit_context() == {}
    with audit.audit_context(run_id=7, source="runner"):
        ctx = audit.current_audit_context()
        assert ctx["run_id"] == 7
        assert ctx["source"] == "runner"
        with audit.audit_context(phase_code="scoring"):
            inner = audit.current_audit_context()
            assert inner["run_id"] == 7  # inherited
            assert inner["phase_code"] == "scoring"
        # inner phase_code is gone after the block exits
        assert "phase_code" not in audit.current_audit_context()
    assert audit.current_audit_context() == {}


# ---------------------------------------------------------------------------
# Gating + writes
# ---------------------------------------------------------------------------
class _FakeConnector:
    def __init__(self):
        self.executed = []
        self.batched = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        return 1

    def execute_many(self, sql, params_list):
        self.batched.append((sql, list(params_list)))


def _enable(monkeypatch, *, postgres=True, flag=True, tables=None):
    monkeypatch.setattr(audit, "_is_postgres", lambda: postgres)

    def fake_cfg(key, default=None):
        if key == "database.audit_log_enabled":
            return flag
        if key == "database.audit_log_tables":
            return tables
        return default

    import modules.config as cfg

    monkeypatch.setattr(cfg, "get_config_value", fake_cfg)


def test_is_enabled_respects_flag_and_engine(monkeypatch):
    _enable(monkeypatch, postgres=True, flag=True)
    assert audit.is_enabled("images") is True
    _enable(monkeypatch, postgres=False, flag=True)
    assert audit.is_enabled("images") is False
    _enable(monkeypatch, postgres=True, flag=False)
    assert audit.is_enabled("images") is False


def test_is_enabled_table_allowlist(monkeypatch):
    _enable(monkeypatch, postgres=True, flag=True, tables=["jobs"])
    assert audit.is_enabled("jobs") is True
    assert audit.is_enabled("images") is False


def test_record_audit_writes_when_enabled(monkeypatch):
    _enable(monkeypatch)
    fake = _FakeConnector()
    monkeypatch.setattr(audit, "_connector", lambda: fake)

    with audit.audit_context(run_id=42, phase_code="scoring", source="ctx"):
        audit.record_audit(
            "images", 5, "update",
            audit.build_field_update_patch("rating", 2, 4),
        )

    assert len(fake.executed) == 1
    sql, params = fake.executed[0]
    assert "INSERT INTO auditlog" in sql
    assert "?::jsonb" in sql
    # params: table_name, record_id, operation, patch_json, thread_name, run_id, phase_code, source, created_at
    assert params[0] == "images"
    assert params[1] == 5
    assert params[2] == "update"
    assert '"oldValue": 2' in params[3]
    assert params[5] == 42  # run_id from context
    assert params[6] == "scoring"  # phase_code from context
    assert params[7] == "ctx"  # source from context


def test_record_audit_explicit_overrides_context(monkeypatch):
    _enable(monkeypatch)
    fake = _FakeConnector()
    monkeypatch.setattr(audit, "_connector", lambda: fake)
    with audit.audit_context(run_id=1, source="ctx"):
        audit.record_audit(
            "jobs", 9, "insert",
            audit.build_insert_patch({"status": "queued"}),
            run_id=99, source="explicit",
        )
    _, params = fake.executed[0]
    assert params[5] == 99
    assert params[7] == "explicit"


def test_record_audit_noop_when_disabled(monkeypatch):
    _enable(monkeypatch, flag=False)
    fake = _FakeConnector()
    monkeypatch.setattr(audit, "_connector", lambda: fake)
    audit.record_audit("images", 1, "update", [{"op": "replace", "path": "/x", "value": 1}])
    assert fake.executed == []


def test_record_audit_noop_on_empty_patch(monkeypatch):
    _enable(monkeypatch)
    fake = _FakeConnector()
    monkeypatch.setattr(audit, "_connector", lambda: fake)
    audit.record_audit("images", 1, "update", [])
    assert fake.executed == []


def test_record_audit_never_raises(monkeypatch):
    _enable(monkeypatch)

    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(audit, "_connector", boom)
    # Must swallow the connector error.
    audit.record_audit("images", 1, "update", [{"op": "replace", "path": "/x", "value": 1}])


def test_record_audit_batch(monkeypatch):
    _enable(monkeypatch)
    fake = _FakeConnector()
    monkeypatch.setattr(audit, "_connector", lambda: fake)
    rows = [
        (1, audit.build_field_update_patch("cull_decision", "neutral", "pick")),
        (2, audit.build_field_update_patch("cull_decision", "pick", "pick")),  # empty → skipped
        (3, audit.build_field_update_patch("cull_decision", None, "reject")),
    ]
    audit.record_audit_batch("images", "update", rows, run_id=7)
    assert len(fake.batched) == 1
    _, param_rows = fake.batched[0]
    # row 2 produced an empty patch and is skipped.
    assert len(param_rows) == 2
    assert {r[1] for r in param_rows} == {1, 3}
    assert all(r[5] == 7 for r in param_rows)


def test_record_audit_uses_tx_when_provided(monkeypatch):
    _enable(monkeypatch)
    fake_conn = _FakeConnector()
    monkeypatch.setattr(audit, "_connector", lambda: fake_conn)
    tx = _FakeConnector()
    audit.record_audit(
        "jobs", 3, "update",
        audit.build_field_update_patch("status", "running", "completed"),
        tx=tx,
    )
    assert len(tx.executed) == 1
    assert fake_conn.executed == []  # standalone connector not used
