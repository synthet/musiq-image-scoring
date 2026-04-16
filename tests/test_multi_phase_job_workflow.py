"""
Multi-phase workflow: one jobs row + job_phases; stage completion must not
terminal-complete the job until all phases finish; dispatcher continues in-process.
"""
import os
import shutil
import time
import uuid

import pytest

pytestmark = pytest.mark.firebird

from modules import db
from modules.job_dispatcher import JobDispatcher
from tests.support.fake_runners import FakePhaseRunner


@pytest.fixture(scope="module")
def mp_db(tmp_path_factory):
    template = os.path.abspath("template.fdb")
    if not os.path.exists(template):
        pytest.skip("template.fdb not found - Firebird tests unavailable")

    tmp = tmp_path_factory.mktemp("multi_phase_workflow")
    db_path = str(tmp / f"mp_{uuid.uuid4().hex}.fdb")
    shutil.copy2(template, db_path)

    original_path = db.DB_PATH
    db.DB_PATH = os.path.abspath(db_path)
    db.reset_init_db_state_for_tests()
    try:
        db.init_db()
    except Exception as exc:
        db.DB_PATH = original_path
        pytest.skip(f"DB init failed: {exc}")

    yield
    db.DB_PATH = original_path


@pytest.fixture(autouse=True)
def clean_jobs(mp_db):
    conn = db.get_db()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM job_phases")
    except Exception:
        pass
    c.execute("DELETE FROM jobs")
    conn.commit()
    conn.close()


def test_update_job_status_completed_advances_phases_without_terminal_job(mp_db):
    jid = db.create_job(
        "/mp/scope",
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


def test_update_job_status_completed_terminal_when_all_phases_done(mp_db):
    jid = db.create_job(
        "/mp/scope2",
        phase_code="metadata",
        job_type="metadata",
        status="running",
        runner_state="running",
    )
    db.create_job_phases(jid, ["indexing", "metadata"])
    phases_before = db.get_job_phases(jid)
    # Simulate indexing already done; only metadata running
    db.set_job_phase_state(jid, phases_before[0]["phase_code"], "completed")
    db.set_job_phase_state(jid, phases_before[1]["phase_code"], "running")

    db.update_job_status(jid, "completed")
    row = db.get_job(jid)
    assert (row["status"] or "").lower() == "completed"
    assert row.get("finished_at") is not None
    phases = db.get_job_phases(jid)
    assert all((p["state"] or "").lower() == "completed" for p in phases)


def _noop_running_sync(path, job_id, **kwargs):
    """Align job_phases with real runners (running -> running is a no-op transition)."""
    db.update_job_status(int(job_id), "running")


def test_dispatcher_starts_second_phase_after_first_completes(mp_db):
    fake_ix = FakePhaseRunner(delay_s=0.04, on_start=_noop_running_sync)
    fake_meta = FakePhaseRunner(delay_s=0.04, on_start=_noop_running_sync)
    d = JobDispatcher(
        indexing_runner=fake_ix,
        metadata_runner=fake_meta,
        poll_interval=5.0,
    )
    jid, _ = db.enqueue_job(
        "D:/mp-chain/1",
        phase_code="indexing",
        job_type="pipeline",
        queue_payload={"input_path": "D:/mp-chain/1"},
    )
    db.create_job_phases(jid, ["indexing", "metadata"], first_phase_state="queued")

    deadline = time.time() + 3.0
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
