"""FastAPI prerequisite validation on POST /api/runs/submit (compute stubbed; no PostgreSQL required for 400 paths)."""

from __future__ import annotations

import pathlib

import pytest

FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient


@pytest.fixture
def api_client(monkeypatch):
    monkeypatch.setattr("modules.ui.security._check_rate_limit", lambda *_a, **_kw: None)
    from modules import api as api_mod

    app = FastAPI()
    app.include_router(api_mod.create_api_router())
    app.include_router(api_mod.create_public_api_router())
    with TestClient(app) as client:
        yield client


@pytest.fixture(name="_stub_compute_scope_phases")
def stub_compute_scope_phases(monkeypatch):
    """``compute_satisfied_phases_for_scope`` drives submit-run prerequisites."""
    satisfied: set[str] = set()

    def _fake(_scope_paths):
        return set(satisfied)

    monkeypatch.setattr("modules.phases.compute_satisfied_phases_for_scope", _fake)
    return satisfied


@pytest.fixture
def resolve_scope_stub(monkeypatch):
    def _fake(raw_path: str):
        p = pathlib.Path(raw_path)
        p.mkdir(parents=True, exist_ok=True)
        resolved = str(p.resolve())
        return resolved, [resolved]

    monkeypatch.setattr("modules.utils.resolve_scope_input_path", _fake)


def _submit_body(scope_path: str, stages: list[str]) -> dict:
    return {
        "scope_type": "folder_recursive",
        "scope_paths": [scope_path],
        "stages": stages,
        "generate_captions": False,
    }


def test_scoring_only_returns_missing_metadata(api_client, tmp_path, _stub_compute_scope_phases):
    p = tmp_path / "scope"
    p.mkdir()
    r = api_client.post(
        "/api/runs/submit",
        json=_submit_body(str(p.resolve()), ["scoring"]),
    )
    assert r.status_code == 400
    detail = r.json().get("detail")
    assert isinstance(detail, dict)
    assert detail["code"] == "missing_prerequisites"
    assert detail["missing"]["scoring"] == ["metadata"]


def test_bird_species_only_returns_missing_keywords(api_client, tmp_path, _stub_compute_scope_phases):
    p = tmp_path / "scope"
    p.mkdir()
    r = api_client.post(
        "/api/runs/submit",
        json=_submit_body(str(p.resolve()), ["bird_species"]),
    )
    assert r.status_code == 400
    detail = r.json().get("detail")
    assert detail["missing"]["bird_species"] == ["keywords"]


def test_canonical_mode_does_not_bypass_missing_prereq(api_client, tmp_path, _stub_compute_scope_phases):
    p = tmp_path / "scope"
    p.mkdir()
    r = api_client.post(
        "/api/runs/submit",
        json=_submit_body(str(p.resolve()), ["scoring"]),
    )
    assert r.status_code == 400


def test_metadata_and_scoring_accepted_with_stub_enqueue(
    api_client,
    tmp_path,
    _stub_compute_scope_phases,
    resolve_scope_stub,
    monkeypatch,
):
    monkeypatch.setattr(
        "modules.db.enqueue_job_with_phases",
        lambda *a, **k: (42, 0),
    )
    monkeypatch.setattr(
        "modules.db.build_validation_repair_plan",
        lambda *a, **k: {
            "stage_queues": {"metadata": [1], "scoring": [1]},
            "dry_run": False,
        },
    )
    monkeypatch.setattr(
        "modules.runs_autodrive.phases_with_work_from_repair_plan",
        lambda *_a, **_k: ["metadata", "scoring"],
    )
    _stub_compute_scope_phases.add("indexing")

    p = tmp_path / "scope"
    p.mkdir()
    r = api_client.post(
        "/api/runs/submit",
        json=_submit_body(str(p.resolve()), ["metadata", "scoring"]),
    )
    assert r.status_code == 200
    assert r.json().get("success") is True


def test_submit_returns_nothing_to_queue_when_planner_has_no_work(
    api_client,
    tmp_path,
    _stub_compute_scope_phases,
    resolve_scope_stub,
    monkeypatch,
):
    _stub_compute_scope_phases.update({"indexing", "metadata", "scoring"})
    monkeypatch.setattr(
        "modules.runs_autodrive.phases_with_work_from_repair_plan",
        lambda *_a, **_k: [],
    )
    monkeypatch.setattr(
        "modules.db.enqueue_job_with_phases",
        lambda *a, **k: (42, 0),
    )

    p = tmp_path / "scope"
    p.mkdir()
    r = api_client.post(
        "/api/runs/submit",
        json=_submit_body(str(p.resolve()), ["metadata", "scoring"]),
    )
    assert r.status_code == 400
    detail = r.json().get("detail")
    assert detail["code"] == "nothing_to_queue"
