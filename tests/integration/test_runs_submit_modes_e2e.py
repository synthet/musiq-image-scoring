"""
E2E integration: POST /api/runs/submit (SPA-shaped payloads) × run modes × multi-folder scope.

Database: ``image_scoring_test`` only (``pytest.mark.postgres``).
Uses fake runners — no PyTorch/TensorFlow scoring loads.

Also covers multiple queued runs (rapid sequential POST — pool-safe on Windows),
parallel dispatcher ticks, and submit-while-pumping overlap.

Run::
    RUN_POSTGRES_TESTS=1 pytest tests/integration/test_runs_submit_modes_e2e.py -m postgres
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

import pytest

pytestmark = [pytest.mark.postgres]

FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient


# Same codes as frontend FULL_PIPELINE_STAGE_CODES (insertion order before API canonical sort).
FULL_PIPELINE_STAGE_CODES = [
    "indexing",
    "metadata",
    "scoring",
    "culling",
    "keywords",
    "bird_species",
]

CANONICAL_SIX_PHASES = [
    "indexing",
    "metadata",
    "scoring",
    "culling",
    "keywords",
    "bird_species",
]


@pytest.fixture(autouse=True)
def _postgres_clean(postgres_test_session, clean_postgres):
    yield


def _noop_rate_limit(*_a, **_kw):
    pass


@pytest.fixture
def api_client(monkeypatch):
    monkeypatch.setattr("modules.ui.security._check_rate_limit", _noop_rate_limit)
    from modules import api as api_mod

    app = FastAPI()
    app.include_router(api_mod.create_api_router())
    app.include_router(api_mod.create_public_api_router())
    with TestClient(app) as client:
        yield client


def _mkdir_scope(tmp_path, n_folders: int) -> list[str]:
    paths = []
    for i in range(n_folders):
        p = tmp_path / f"scope_folder_{i}"
        p.mkdir(parents=True, exist_ok=True)
        paths.append(str(p.resolve()))
    return paths


def _noop_running_sync(path, job_id, **kwargs):
    from modules import db

    db.update_job_status(int(job_id), "running")


class RecordingScoringRunner:
    """Delegates to FakeScoringRunner but records (job_id, skip_existing) per scoring dispatch."""

    def __init__(self, inner, recordings: list[tuple[int, bool]]):
        self._inner = inner
        self.recordings = recordings

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def start_batch(self, input_path, job_id, skip_existing=False, **kwargs):
        self.recordings.append((int(job_id), bool(skip_existing)))
        return self._inner.start_batch(input_path, job_id, skip_existing, **kwargs)


def _make_dispatcher(delay_s: float, scoring_recordings: list[tuple[int, bool]] | None):
    from modules.job_dispatcher import JobDispatcher
    from tests.support.fake_runners import (
        FakeBirdSpeciesRunner,
        FakeClusteringRunner,
        FakePhaseRunner,
        FakeScoringRunner,
        FakeSelectionRunner,
        FakeTaggingRunner,
    )

    recordings = scoring_recordings if scoring_recordings is not None else []

    base_scoring = FakeScoringRunner(delay_s=delay_s, on_start=_noop_running_sync)
    scoring = (
        RecordingScoringRunner(base_scoring, recordings)
        if scoring_recordings is not None
        else base_scoring
    )

    def _tagging():
        return FakeTaggingRunner(delay_s=delay_s, on_start=_noop_running_sync)

    def _clustering():
        return FakeClusteringRunner(delay_s=delay_s, on_start=_noop_running_sync)

    def _selection():
        return FakeSelectionRunner(delay_s=delay_s, on_start=_noop_running_sync)

    def _generic():
        return FakePhaseRunner(delay_s=delay_s, on_start=_noop_running_sync)

    return JobDispatcher(
        indexing_runner=_generic(),
        metadata_runner=_generic(),
        scoring_runner=scoring,
        tagging_runner=_tagging(),
        clustering_runner=_clustering(),
        selection_runner=_selection(),
        bird_species_runner=FakeBirdSpeciesRunner(delay_s=delay_s, on_start=_noop_running_sync),
        poll_interval=5.0,
    )


def _submit_like_spa(
    client,
    scope_paths: list[str],
    *,
    skip_done: bool,
    force_rerun: bool,
    fix_incomplete_stages: bool,
    validation_repair_mode: bool,
    description: str = "",
) -> dict[str, Any]:
    body = {
        "scope_type": "folder_recursive",
        "scope_paths": scope_paths,
        "stages": list(FULL_PIPELINE_STAGE_CODES),
        "skip_done": skip_done,
        "force_rerun": force_rerun,
        "fix_incomplete_stages": fix_incomplete_stages,
        "validation_repair_mode": validation_repair_mode,
        "validation_repair_dry_run": False,
        "generate_captions": False,
        "description": description,
    }
    r = client.post("/api/runs/submit", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("success") is True
    return data


def _payload_flags(job_row: dict[str, Any]) -> dict[str, Any]:
    raw = job_row.get("queue_payload")
    if not raw:
        return {}
    pl = json.loads(raw) if isinstance(raw, str) else {}
    if isinstance(pl, str):
        pl = json.loads(pl)
    return pl if isinstance(pl, dict) else {}


def _assert_six_phases_completed(job_id: int):
    from modules import db

    phases = db.get_job_phases(job_id) or []
    codes = [str(p.get("phase_code") or "").lower() for p in phases]
    assert sorted(codes, key=str) == sorted(CANONICAL_SIX_PHASES, key=str), codes
    assert len(phases) == 6
    for p in phases:
        assert (p.get("state") or "").lower() == "completed", p


@pytest.mark.parametrize(
    "mode,skip_done,force_rerun,fix_incomplete,validation_repair,"
    "expect_run_mode,expect_skip_existing,expect_force_rerun,"
    "expect_overwrite,expect_force_rescan,expect_fix_flag,"
    "expect_repair_summary",
    [
        (
            "process_new",
            True,
            False,
            False,
            False,
            "process_unprocessed_or_empty",
            True,
            False,
            False,
            False,
            False,
            False,
        ),
        (
            "process_all",
            False,
            True,
            False,
            False,
            "process_all_overwrite",
            False,
            True,
            True,
            True,
            False,
            False,
        ),
        (
            "fix_incomplete",
            True,
            False,
            True,
            False,
            "validate_and_repair",
            False,
            False,
            False,
            True,
            True,
            True,
        ),
        (
            "validation_repair",
            True,
            False,
            False,
            True,
            "process_unprocessed_or_empty",
            None,
            None,
            None,
            None,
            False,
            True,
        ),
    ],
)
def test_runs_submit_modes_payload_and_pipeline(
    api_client,
    tmp_path,
    mode,
    skip_done,
    force_rerun,
    fix_incomplete,
    validation_repair,
    expect_run_mode,
    expect_skip_existing,
    expect_force_rerun,
    expect_overwrite,
    expect_force_rescan,
    expect_fix_flag,
    expect_repair_summary,
):
    """SPA-shaped POST /api/runs/submit: queue_payload flags + full fake pipeline completes."""
    from modules import db
    from tests.support.pipeline_matrix import run_dispatcher_until_quiet

    scope_paths = _mkdir_scope(tmp_path, n_folders=3)
    scoring_calls: list[tuple[int, bool]] = []
    dispatcher = _make_dispatcher(delay_s=0.02, scoring_recordings=scoring_calls)

    data = _submit_like_spa(
        api_client,
        scope_paths,
        skip_done=skip_done,
        force_rerun=force_rerun,
        fix_incomplete_stages=fix_incomplete,
        validation_repair_mode=validation_repair,
        description=f"e2e-{mode}",
    )
    job_id = int(data["run_id"])
    job = db.get_job(job_id)
    assert job is not None
    pl = _payload_flags(job)

    assert pl.get("scope_paths") == scope_paths
    assert pl.get("run_mode") == expect_run_mode
    if expect_skip_existing is not None:
        assert pl.get("skip_existing") is expect_skip_existing
    if expect_force_rerun is not None:
        assert pl.get("force_rerun") is expect_force_rerun
    if expect_overwrite is not None:
        assert pl.get("overwrite") is expect_overwrite
    if expect_force_rescan is not None:
        assert pl.get("force_rescan") is expect_force_rescan
    assert pl.get("fix_incomplete_stages") is expect_fix_flag

    if expect_repair_summary:
        assert "validation_repair_summary" in pl
        summary = pl["validation_repair_summary"]
        assert isinstance(summary, dict)
        assert "stage_queues" in summary
    else:
        assert "validation_repair_summary" not in pl

    run_dispatcher_until_quiet(dispatcher, deadline_s=45.0)

    row = db.get_job(job_id)
    assert row is not None
    assert (row.get("status") or "").lower() == "completed", row
    _assert_six_phases_completed(job_id)

    # Deep check: scoring skip_existing for NEW vs ALL (payload-driven modes).
    if mode == "process_new":
        assert any(sk is True for _, sk in scoring_calls), scoring_calls
    elif mode == "process_all":
        assert any(sk is False for _, sk in scoring_calls), scoring_calls
    elif mode == "fix_incomplete":
        assert scoring_calls, "expected at least one scoring dispatch"
        assert all(sk is False for _, sk in scoring_calls), scoring_calls
    elif mode == "validation_repair":
        assert scoring_calls, "expected at least one scoring dispatch"
        assert pl.get("skip_existing") is False


def test_validation_repair_preview_smoke(api_client, tmp_path):
    scope_paths = _mkdir_scope(tmp_path, n_folders=2)
    r = api_client.post(
        "/api/runs/validation-repair/preview",
        json={"scope_paths": scope_paths, "stages": list(FULL_PIPELINE_STAGE_CODES)},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "stage_queues" in body
    assert isinstance(body["stage_queues"], dict)


def test_burst_concurrent_submits_complete_all(api_client, tmp_path):
    """Queue M runs via rapid sequential POST (pool-safe), then drain — all complete.

    True parallel HTTP threads against the same Postgres pool can raise
    ``PoolError: trying to put unkeyed connection`` on Windows; sequential
    submits still validates multiple independent jobs and dispatcher ordering.
    """
    from modules import db
    from tests.support.pipeline_matrix import _drain_runner_threads, run_dispatcher_until_quiet

    m_jobs = 4
    dispatcher = _make_dispatcher(delay_s=0.015, scoring_recordings=None)

    job_ids = []
    for i in range(m_jobs):
        paths = _mkdir_scope(tmp_path / f"burst_{i}", n_folders=2)
        jid = int(
            _submit_like_spa(
                api_client,
                paths,
                skip_done=True,
                force_rerun=False,
                fix_incomplete_stages=False,
                validation_repair_mode=False,
                description=f"burst-{i}",
            )["run_id"]
        )
        job_ids.append(jid)

    assert len(set(job_ids)) == m_jobs

    run_dispatcher_until_quiet(dispatcher, deadline_s=120.0)

    _drain_runner_threads(dispatcher)

    assert db.get_queued_jobs(limit=5) == []
    for jid in job_ids:
        row = db.get_job(jid)
        assert row is not None
        assert (row.get("status") or "").lower() == "completed", row
        _assert_six_phases_completed(jid)


def test_parallel_dispatcher_ticks_single_job(api_client, tmp_path):
    """Many threads calling tick_for_tests; job still completes exactly once."""
    from modules import db

    scope_paths = _mkdir_scope(tmp_path, n_folders=1)
    dispatcher = _make_dispatcher(delay_s=0.06, scoring_recordings=None)
    data = _submit_like_spa(
        api_client,
        scope_paths,
        skip_done=True,
        force_rerun=False,
        fix_incomplete_stages=False,
        validation_repair_mode=False,
    )
    job_id = int(data["run_id"])

    stop = threading.Event()

    def pump():
        while not stop.is_set():
            dispatcher.tick_for_tests()
            time.sleep(0.002)

    threads = [threading.Thread(target=pump, daemon=True) for _ in range(6)]
    for t in threads:
        t.start()

    try:
        deadline = time.time() + 60.0
        while time.time() < deadline:
            row = db.get_job(job_id)
            if row and (row.get("status") or "").lower() == "completed":
                break
            time.sleep(0.02)
        row = db.get_job(job_id)
        assert row is not None
        assert (row.get("status") or "").lower() == "completed", row
        _assert_six_phases_completed(job_id)
    finally:
        stop.set()
        for t in threads:
            t.join(timeout=2.0)
        from tests.support.pipeline_matrix import _drain_runner_threads

        _drain_runner_threads(dispatcher)


def test_submit_while_dispatcher_pumping(api_client, tmp_path):
    """Second run submitted while background pump is active; both finish completed."""
    from modules import db
    from tests.support.pipeline_matrix import _drain_runner_threads

    dispatcher = _make_dispatcher(delay_s=0.04, scoring_recordings=None)
    paths1 = _mkdir_scope(tmp_path / "overlap_a", n_folders=1)
    paths2 = _mkdir_scope(tmp_path / "overlap_b", n_folders=1)

    id1 = int(
        _submit_like_spa(
            api_client,
            paths1,
            skip_done=True,
            force_rerun=False,
            fix_incomplete_stages=False,
            validation_repair_mode=False,
            description="overlap-1",
        )["run_id"]
    )

    stop = threading.Event()

    def pump():
        while not stop.is_set():
            dispatcher.tick_for_tests()
            time.sleep(0.01)

    th = threading.Thread(target=pump, daemon=True)
    th.start()
    try:
        time.sleep(0.05)
        id2 = int(
            _submit_like_spa(
                api_client,
                paths2,
                skip_done=True,
                force_rerun=False,
                fix_incomplete_stages=False,
                validation_repair_mode=False,
                description="overlap-2",
            )["run_id"]
        )
        assert id1 != id2

        deadline = time.time() + 90.0
        while time.time() < deadline:
            r1 = db.get_job(id1)
            r2 = db.get_job(id2)
            if (
                r1
                and r2
                and (r1.get("status") or "").lower() == "completed"
                and (r2.get("status") or "").lower() == "completed"
            ):
                break
            dispatcher.tick_for_tests()
            time.sleep(0.02)

        assert (db.get_job(id1).get("status") or "").lower() == "completed"
        assert (db.get_job(id2).get("status") or "").lower() == "completed"
        assert db.get_queued_jobs(limit=3) == []
    finally:
        stop.set()
        th.join(timeout=2.0)
        _drain_runner_threads(dispatcher)
