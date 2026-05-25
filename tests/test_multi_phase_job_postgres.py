"""Multi-phase job workflow against PostgreSQL (default test engine)."""

import time

import pytest

from modules import db
from modules.db import job_type_for_phase_dispatch
from modules.job_dispatcher import JobDispatcher
from tests.support.fake_runners import FakePhaseRunner

pytestmark = [pytest.mark.postgres]


@pytest.fixture(autouse=True)
def _postgres_clean_each_test(postgres_test_session, clean_postgres):
    yield


def test_job_type_for_phase_dispatch():
    assert job_type_for_phase_dispatch("keywords") == "tagging"
    assert job_type_for_phase_dispatch("culling") == "selection"
    assert job_type_for_phase_dispatch("indexing") == "indexing"
    assert job_type_for_phase_dispatch("scoring") == "scoring"


def test_update_job_status_completed_advances_phases_without_terminal_job():
    jid = db.create_job(
        "/mp/pg-scope",
        phase_code="indexing",
        job_type="pipeline",
        status="running",
        runner_state="running",
    )
    db.create_job_phases(jid, ["indexing", "metadata"])
    db.update_job_status(jid, "completed")

    row = db.get_job(jid)
    assert (row["status"] or "").lower() == "running"
    assert (row["job_type"] or "").lower() == "pipeline"
    assert row.get("finished_at") is None
    assert row.get("completed_at") is None
    assert (row.get("current_phase") or "").lower() == "metadata"

    phases = db.get_job_phases(jid)
    assert len(phases) == 2
    assert (phases[0]["state"] or "").lower() == "completed"
    assert (phases[1]["state"] or "").lower() == "running"


def test_update_job_status_completed_terminal_when_all_phases_done():
    jid = db.create_job(
        "/mp/pg-scope2",
        phase_code="metadata",
        job_type="metadata",
        status="running",
        runner_state="running",
    )
    db.create_job_phases(jid, ["indexing", "metadata"])
    phases_before = db.get_job_phases(jid)
    db.set_job_phase_state(jid, phases_before[0]["phase_code"], "completed")
    db.set_job_phase_state(jid, phases_before[1]["phase_code"], "running")

    db.update_job_status(jid, "completed")
    row = db.get_job(jid)
    assert (row["status"] or "").lower() == "completed"
    assert row.get("finished_at") is not None
    phases = db.get_job_phases(jid)
    assert all((p["state"] or "").lower() == "completed" for p in phases)


def _noop_running_sync(path, job_id, **kwargs):
    db.update_job_status(int(job_id), "running")


def test_dispatcher_starts_second_phase_after_first_completes(monkeypatch):
    fake_ix = FakePhaseRunner(delay_s=0.04, on_start=_noop_running_sync)
    fake_meta = FakePhaseRunner(delay_s=0.04, on_start=_noop_running_sync)
    monkeypatch.setattr(
        JobDispatcher,
        "_jit_replan_phase",
        lambda self, job_id, payload, queue_key, input_path: (payload, [1], False),
    )
    d = JobDispatcher(
        indexing_runner=fake_ix,
        metadata_runner=fake_meta,
        poll_interval=5.0,
    )
    jid, _ = db.enqueue_job(
        "D:/mp-pg-chain/1",
        phase_code="indexing",
        job_type="pipeline",
        queue_payload={"input_path": "D:/mp-pg-chain/1"},
    )
    db.create_job_phases(jid, ["indexing", "metadata"], first_phase_state="queued")

    deadline = time.time() + 5.0
    while time.time() < deadline:
        d.tick_for_tests()
        j = db.get_job(jid)
        if (j.get("current_phase") or "").lower() == "metadata" and fake_meta.is_running:
            break
        time.sleep(0.02)

    row = db.get_job(jid)
    assert (row.get("job_type") or "").lower() == "pipeline"
    assert (row.get("current_phase") or "").lower() == "metadata"
    assert fake_meta.is_running

    while time.time() < deadline:
        d.tick_for_tests()
        if not fake_meta.is_running and (db.get_job(jid)["status"] or "").lower() == "completed":
            break
        time.sleep(0.02)

    assert (db.get_job(jid)["status"] or "").lower() == "completed"
