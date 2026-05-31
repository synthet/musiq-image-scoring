"""Tests for image_phase_status reconciliation tied to jobs (startup / terminal status)."""

from modules import api
from modules import db


def test_job_should_stop_processing_paused(monkeypatch):
    monkeypatch.setattr(
        "modules.db.get_job",
        lambda jid: {"status": "paused", "cancel_requested": 0},
    )
    assert db.job_should_stop_processing(1) is True


def test_job_should_stop_processing_running(monkeypatch):
    monkeypatch.setattr(
        "modules.db.get_job",
        lambda jid: {"status": "running", "cancel_requested": 0},
    )
    assert db.job_should_stop_processing(1) is False


def test_job_should_stop_processing_cancel_requested(monkeypatch):
    monkeypatch.setattr(
        "modules.db.get_job",
        lambda jid: {"status": "running", "cancel_requested": 1},
    )
    assert db.job_should_stop_processing(1) is True


def test_graceful_shutdown_processing_idempotent(monkeypatch):
    calls = []

    def track_stop():
        calls.append("stop")

    monkeypatch.setattr(api, "_graceful_shutdown_done", False)
    monkeypatch.setattr(api, "stop_dispatcher", track_stop)
    monkeypatch.setattr(api, "_join_runner_threads", lambda *a, **k: None)
    monkeypatch.setattr(api, "_finalize_running_jobs_after_worker_stop", lambda *a, **k: None)

    api.graceful_shutdown_processing("test")
    api.graceful_shutdown_processing("test")
    assert calls == ["stop"]


def test_recover_running_jobs_invokes_phase_reconcile(monkeypatch):
    calls = []

    def fake_reconcile(job_ids, error_message=None, in_flight_to="failed"):
        calls.append((list(job_ids), error_message, in_flight_to))
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
    assert calls[0][2] == "not_started"


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


# --- Issue #161: salvage scoring rows whose outputs already exist -------------


def _make_reconcile_fake(executed_log):
    """Connector double that records execute() calls and returns deterministic rowcounts."""

    class FakeConn:
        def query(self, sql, params=None):
            return []

        def execute(self, sql, params=None):
            executed_log.append((sql, list(params) if params else []))
            sql_upper = sql.upper()
            if "SET STATUS = 'DONE'" in sql_upper:
                return 17
            if "SET STATUS = 'FAILED'" in sql_upper:
                return 3
            if "SET STATUS = 'NOT_STARTED'" in sql_upper:
                return 4
            return 0

    return FakeConn()


def test_reconcile_failed_salvages_scoring_rows_with_outputs(monkeypatch):
    """Issue #161: scoring rows whose outputs are persisted on ``images`` must be
    flipped to ``done`` (with a ``:outputs_present`` marker), not ``failed``.
    """
    executed = []
    monkeypatch.setattr("modules.db.get_connector", lambda: _make_reconcile_fake(executed))
    monkeypatch.setattr("modules.db.invalidate_folder_phase_aggregates", lambda **kw: None)

    rc = db.reconcile_stale_running_phases_for_jobs(
        [2423], error_message="stale_running_reconciled:job_cancelled", in_flight_to="failed",
    )

    update_calls = [(s, p) for s, p in executed if "UPDATE IMAGE_PHASE_STATUS" in s.upper()]
    # Expect 3 UPDATEs: scoring salvage, culling salvage, fail.
    assert len(update_calls) == 3, update_calls

    scoring_salvage_sql, salvage_params = update_calls[0]
    assert "SET status = 'done'" in scoring_salvage_sql
    assert "code = 'scoring'" in scoring_salvage_sql
    assert "image_model_scores" in scoring_salvage_sql
    assert "scores_json IS NOT NULL" not in scoring_salvage_sql
    assert salvage_params[0] == "stale_running_reconciled:job_cancelled:outputs_present"

    culling_salvage_sql, _ = update_calls[1]
    assert "SET status = 'done'" in culling_salvage_sql
    assert "code = 'culling'" in culling_salvage_sql
    assert "stack_id IS NOT NULL" in culling_salvage_sql

    fail_sql, _ = update_calls[2]
    assert "SET status = 'failed'" in fail_sql

    # Total = scoring salvaged (17) + culling salvaged (17) + failed (3).
    assert rc == 37


def test_reconcile_not_started_mode_skips_salvage(monkeypatch):
    """Resumable reconcile (``in_flight_to='not_started'``) must not run the
    salvage path: rows are intentionally left for the runner to pick up again.
    """
    executed = []
    monkeypatch.setattr("modules.db.get_connector", lambda: _make_reconcile_fake(executed))
    monkeypatch.setattr("modules.db.invalidate_folder_phase_aggregates", lambda **kw: None)

    rc = db.reconcile_stale_running_phases_for_jobs(
        [99], error_message="stale_running_reconciled:job_interrupted", in_flight_to="not_started",
    )
    update_calls = [(s, p) for s, p in executed if "UPDATE IMAGE_PHASE_STATUS" in s.upper()]
    assert len(update_calls) == 1
    assert "SET status = 'not_started'" in update_calls[0][0]
    assert "SET status = 'done'" not in update_calls[0][0]
    assert rc == 4


def test_reconcile_empty_job_ids_short_circuits(monkeypatch):
    """No job ids → zero work and no UPDATE."""
    executed = []
    monkeypatch.setattr("modules.db.get_connector", lambda: _make_reconcile_fake(executed))
    rc = db.reconcile_stale_running_phases_for_jobs([], error_message=None, in_flight_to="failed")
    assert rc == 0
    assert executed == []


def test_count_reconcilable_terminal_job_phases(monkeypatch):
    class FakeConn:
        def query_one(self, sql, params=None):
            assert "COUNT(*)" in sql
            assert "image_phase_status" in sql
            assert "jobs" in sql
            return {"c": 42}

    monkeypatch.setattr("modules.db.get_connector", lambda: FakeConn())
    assert db.count_reconcilable_terminal_job_phases() == 42


# --- Issue #157: orphan-interrupted sweep ---------------------------------


def test_reconcile_orphan_interrupted_no_candidates(monkeypatch):
    """When no interrupted jobs have stuck running IPS rows, sweep is a no-op."""
    class FakeConn:
        def query(self, sql, params=None):
            return []

    monkeypatch.setattr("modules.db.get_connector", lambda: FakeConn())
    called = []
    monkeypatch.setattr(
        "modules.db.reconcile_stale_running_phases_for_jobs",
        lambda *a, **kw: called.append((a, kw)) or 0,
    )

    result = db.reconcile_orphan_interrupted_job_phases()
    assert result == {"swept_job_ids": [], "reconciled_rows": 0}
    assert called == []  # reconcile not invoked when nothing to do


def test_reconcile_orphan_interrupted_sweeps_jobs(monkeypatch):
    """Interrupted jobs with stuck running IPS rows are reconciled to not_started."""
    class FakeConn:
        def query(self, sql, params=None):
            assert "status = 'interrupted'" in sql
            assert "ips.status = 'running'" in sql
            return [{"job_id": 2371}, {"job_id": 2369}]

    captured = {}
    def fake_reconcile(job_ids, error_message=None, in_flight_to="failed"):
        captured["job_ids"] = list(job_ids)
        captured["error_message"] = error_message
        captured["in_flight_to"] = in_flight_to
        return 733

    monkeypatch.setattr("modules.db.get_connector", lambda: FakeConn())
    monkeypatch.setattr("modules.db.reconcile_stale_running_phases_for_jobs", fake_reconcile)

    result = db.reconcile_orphan_interrupted_job_phases()
    assert result == {"swept_job_ids": [2371, 2369], "reconciled_rows": 733}
    assert captured["job_ids"] == [2371, 2369]
    assert captured["in_flight_to"] == "not_started"
    assert "orphan_interrupted_sweep" in (captured["error_message"] or "")


def test_reconcile_orphan_interrupted_swallows_scan_failure(monkeypatch):
    """Best-effort: a scan failure does not propagate; an empty result is returned."""
    class FakeConn:
        def query(self, sql, params=None):
            raise RuntimeError("simulated outage")

    monkeypatch.setattr("modules.db.get_connector", lambda: FakeConn())
    result = db.reconcile_orphan_interrupted_job_phases()
    assert result == {"swept_job_ids": [], "reconciled_rows": 0}
