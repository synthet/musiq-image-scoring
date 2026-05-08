"""
E2E: sequential POST ``/api/runs/submit`` with one stage per request under ``process_new``.

Prerequisite validation uses ``compute_satisfied_phases_for_scope`` (aligned with scope preview).
Fake runners do not populate folder summaries quickly enough for sequential single-stage submits.
Tests stub that helper and grow a mutable satisfied set after each dispatcher drain.

``pytest.mark.postgres``.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.postgres]

FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient

CANONICAL_STEPS = (
    "indexing",
    "metadata",
    "scoring",
    "culling",
    "keywords",
    "bird_species",
)


@pytest.fixture(autouse=True)
def _postgres_clean(postgres_test_session, clean_postgres):
    yield


@pytest.fixture(autouse=True)
def _disable_preview_phase_heal(monkeypatch):
    monkeypatch.setattr(
        "modules.db_legacy._heal_stale_phase_flags",
        lambda *_a, **_kw: 0,
    )


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


@pytest.fixture
def incremental_scope_satisfied(monkeypatch):
    """Controlled satisfied-phase set for ``compute_satisfied_phases_for_scope`` (submit prereqs)."""
    satisfied: set[str] = set()

    def _fake_compute(_scope_paths):
        return set(satisfied)

    monkeypatch.setattr("modules.phases.compute_satisfied_phases_for_scope", _fake_compute)
    return satisfied


@pytest.fixture
def incremental_api_client(monkeypatch, incremental_scope_satisfied):
    """API client with prerequisite aggregation stubbed (fixture order ensures patch before app use)."""
    monkeypatch.setattr("modules.ui.security._check_rate_limit", _noop_rate_limit)
    from modules import api as api_mod

    app = FastAPI()
    app.include_router(api_mod.create_api_router())
    app.include_router(api_mod.create_public_api_router())
    with TestClient(app) as client:
        yield client


@pytest.fixture
def scope_folder(tmp_path):
    d = tmp_path / "incremental_scope"
    d.mkdir(parents=True, exist_ok=True)
    (d / "_seed.jpg").touch()
    return str(d.resolve())


def test_incremental_chain_process_new(incremental_api_client, scope_folder, incremental_scope_satisfied):
    from modules import db
    from modules.phases import sort_phase_value_strings
    from tests.integration.test_runs_submit_modes_e2e import _make_dispatcher
    from tests.support.pipeline_matrix import run_dispatcher_until_quiet, submit_run_via_api

    dispatcher = _make_dispatcher(delay_s=0.02, scoring_recordings=None)
    prior_done: set[str] = set()

    for phase in CANONICAL_STEPS:
        sub = submit_run_via_api(incremental_api_client, [scope_folder], [phase], "process_new")
        assert sub.status_code == 200, sub.text
        jid = int(sub.json()["run_id"])
        run_dispatcher_until_quiet(dispatcher, deadline_s=60.0)
        row = db.get_job(jid)
        assert row is not None
        assert (row.get("status") or "").lower() == "completed", row

        phases = db.get_job_phases(jid) or []
        got = sort_phase_value_strings([str(p.get("phase_code") or "") for p in phases])
        want = sort_phase_value_strings([phase])
        assert got == want, (got, want)
        for p in phases:
            assert (p.get("state") or "").lower() == "completed", p

        incremental_scope_satisfied.add(phase)
        done_now = set(incremental_scope_satisfied)
        assert phase in done_now
        assert prior_done <= done_now
        prior_done = set(done_now)


def test_incremental_process_all_reruns(incremental_api_client, scope_folder, incremental_scope_satisfied):
    from modules import db
    from tests.integration.test_runs_submit_modes_e2e import _make_dispatcher
    from tests.support.pipeline_matrix import run_dispatcher_until_quiet, submit_run_via_api

    dispatcher = _make_dispatcher(delay_s=0.02, scoring_recordings=None)
    for phase in CANONICAL_STEPS[:3]:
        sub = submit_run_via_api(incremental_api_client, [scope_folder], [phase], "process_new")
        assert sub.status_code == 200, sub.text
        run_dispatcher_until_quiet(dispatcher, deadline_s=60.0)
        incremental_scope_satisfied.add(phase)

    sub2 = submit_run_via_api(incremental_api_client, [scope_folder], ["indexing"], "process_all")
    assert sub2.status_code == 200, sub2.text
    jid = int(sub2.json()["run_id"])
    run_dispatcher_until_quiet(dispatcher, deadline_s=60.0)
    assert (db.get_job(jid).get("status") or "").lower() == "completed"


def test_gap_jump_keywords_without_scoring_returns_400(api_client, scope_folder):
    from tests.support.pipeline_matrix import submit_run_via_api

    sub = submit_run_via_api(
        api_client,
        [scope_folder],
        ["indexing", "metadata", "keywords"],
        "process_new",
    )
    assert sub.status_code == 400, sub.text
    detail = sub.json().get("detail")
    assert isinstance(detail, dict)
    assert detail.get("code") == "missing_prerequisites"
    assert detail["missing"]["keywords"] == ["scoring"]
