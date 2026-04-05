"""Tests for image_phase_status reconciliation tied to jobs (startup / terminal status)."""

from modules import db


def test_recover_running_jobs_invokes_phase_reconcile(monkeypatch):
    calls = []

    def fake_reconcile(job_ids, error_message=None):
        calls.append((list(job_ids), error_message))
        return 0

    class Tx:
        def execute(self, *a, **kw):
            return 1

    class FakeConn:
        def query(self, sql, params=None):
            if "FROM jobs WHERE status" in sql and "running" in sql:
                return [{"id": 99}]
            return []

        def run_transaction(self, fn):
            fn(Tx())
            return None

    monkeypatch.setattr("modules.db.get_connector", lambda: FakeConn())
    monkeypatch.setattr("modules.db.reconcile_stale_running_phases_for_jobs", fake_reconcile)

    recovered = db.recover_running_jobs(mark_as="interrupted")
    assert recovered == [99]
    assert len(calls) == 1
    assert calls[0][0] == [99]
    assert "interrupted" in (calls[0][1] or "")


def test_strict_verify_skips_when_disabled(monkeypatch):
    monkeypatch.setattr("modules.config.get_config_value", lambda k, d=None: False)
    assert db._strict_verify_resolved_ids_terminal_for_phase(12345) is None


def test_strict_verify_skips_without_resolved_ids(monkeypatch):
    monkeypatch.setattr("modules.config.get_config_value", lambda k, d=None: True)

    class FakeConn:
        def query_one(self, sql, params=None):
            if "FROM job_phases WHERE job_id" in sql:
                return {"c": 1}
            if "FROM jobs WHERE id" in sql:
                return {"queue_payload": "{}", "phase_id": None, "job_type": "scoring"}
            return None

    monkeypatch.setattr("modules.db.get_connector", lambda: FakeConn())
    assert db._strict_verify_resolved_ids_terminal_for_phase(1) is None


def test_strict_verify_fails_when_image_not_terminal(monkeypatch):
    monkeypatch.setattr("modules.config.get_config_value", lambda k, d=None: True)

    payload = '{"resolved_image_ids": [10, 11]}'

    class FakeConn:
        def query_one(self, sql, params=None):
            if "FROM job_phases WHERE job_id" in sql:
                return {"c": 1}
            if "FROM jobs WHERE id" in sql:
                return {"queue_payload": payload, "phase_id": None, "job_type": "scoring"}
            if "FROM image_phase_status WHERE image_id" in sql:
                iid = params[0]
                if iid == 10:
                    return {"status": "done"}
                return {"status": "running"}
            return None

    monkeypatch.setattr("modules.db.get_connector", lambda: FakeConn())
    monkeypatch.setattr("modules.db.get_phase_id", lambda code: 7)

    msg = db._strict_verify_resolved_ids_terminal_for_phase(5)
    assert msg is not None
    assert "non-terminal" in msg
    assert "10" in msg or "1/" in msg
