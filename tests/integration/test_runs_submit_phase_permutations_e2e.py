"""
E2E: POST /api/runs/submit × phase subset × run mode × scratch vs seeded DB state.

Requires PostgreSQL (``pytest.mark.postgres``). Uses fake runners — no ML.

Run::

    RUN_POSTGRES_TESTS=1 pytest tests/integration/test_runs_submit_phase_permutations_e2e.py -m postgres
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from tests.support.pipeline_matrix import build_submit_matrix

pytestmark = [pytest.mark.postgres]

_MATRIX = build_submit_matrix(
    max_cases=int(os.environ.get("PIPELINE_SUBMIT_MATRIX_MAX_CASES", "120")),
)

FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient


@pytest.fixture(autouse=True)
def _postgres_clean(postgres_test_session, clean_postgres):
    yield


@pytest.fixture(autouse=True)
def _disable_preview_phase_heal(monkeypatch):
    """Scope preview calls ``get_folder_phase_summary(..., force_refresh=True)``, which heals stale rows."""
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


def _snapshot_phase_statuses(image_id: int) -> dict[str, str]:
    from modules import db

    rows = db.get_connector().query(
        """
        SELECT pp.code, COALESCE(ips.status, 'not_started') AS status
        FROM pipeline_phases pp
        LEFT JOIN image_phase_status ips
          ON ips.phase_id = pp.id AND ips.image_id = ?
        WHERE pp.enabled = 1
        """,
        (image_id,),
    )
    out: dict[str, str] = {}
    for r in rows or []:
        code = str(r.get("code") or "").strip().lower()
        st = str(r.get("status") or "").strip().lower()
        if code:
            out[code] = st
    return out


def _assert_phases_completed(job_id: int, expected_codes: list[str]):
    from modules import db
    from modules.phases import sort_phase_value_strings

    want = sort_phase_value_strings(list(expected_codes))
    phases = db.get_job_phases(job_id) or []
    got = sort_phase_value_strings([str(p.get("phase_code") or "") for p in phases])
    assert got == want, (got, want)
    assert len(phases) == len(want)
    for p in phases:
        assert (p.get("state") or "").lower() == "completed", p


@pytest.mark.parametrize("scenario", _MATRIX, ids=[c["test_id"] for c in _MATRIX])
def test_runs_submit_phase_matrix(api_client, tmp_path, scenario: dict[str, Any]):
    from modules import db
    from tests.integration.test_runs_submit_modes_e2e import _make_dispatcher
    from tests.support.pipeline_matrix import (
        run_dispatcher_until_quiet,
        seed_partial_phase_state,
        submit_run_via_api,
    )

    scope_dir = tmp_path / scenario["test_id"].replace("|", "_").replace("+", "_")
    scope_dir.mkdir(parents=True, exist_ok=True)
    paths = [str(scope_dir.resolve())]

    seed_image_id: int | None = None
    snap_before: dict[str, str] | None = None
    if scenario["seed_state"] == "partial_prefix":
        cmprefix = scenario["completed_prefix"]
        assert cmprefix
        seed_image_id = seed_partial_phase_state(paths[0], tuple(cmprefix))
        snap_before = _snapshot_phase_statuses(seed_image_id)

    resp = submit_run_via_api(
        api_client,
        paths,
        scenario["phase_plan"],
        run_api_mode=str(scenario["run_api_mode"]),
    )

    if scenario["expect_status"] == 400:
        assert resp.status_code == 400, resp.text
        detail = resp.json().get("detail")
        assert isinstance(detail, dict), detail
        assert detail.get("code") == "missing_prerequisites"
        assert detail.get("missing")
        return

    assert resp.status_code == 200, resp.text
    job_id = int(resp.json()["run_id"])
    dispatcher = _make_dispatcher(delay_s=0.02, scoring_recordings=None)
    run_dispatcher_until_quiet(dispatcher, deadline_s=120.0)

    row = db.get_job(job_id)
    assert row is not None
    assert (row.get("status") or "").lower() == "completed", row

    plan_list = list(scenario["phase_plan"])
    _assert_phases_completed(job_id, plan_list)

    if scenario["seed_state"] == "partial_prefix" and seed_image_id is not None and snap_before:
        snap_after = _snapshot_phase_statuses(seed_image_id)
        outside = set(snap_before.keys()) - {str(c).lower() for c in plan_list}
        for code in outside:
            assert snap_after.get(code) == snap_before.get(code), (code, snap_before, snap_after)
