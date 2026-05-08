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


def test_scoring_only_returns_missing_metadata(api_client, tmp_path, _stub_compute_scope_phases):
    p = tmp_path / "scope"
    p.mkdir()
    r = api_client.post(
        "/api/runs/submit",
        json={
            "scope_type": "folder_recursive",
            "scope_paths": [str(p.resolve())],
            "stages": ["scoring"],
            "skip_done": True,
            "force_rerun": False,
            "fix_incomplete_stages": False,
            "validation_repair_mode": False,
            "validation_repair_dry_run": False,
            "generate_captions": False,
        },
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
        json={
            "scope_type": "folder_recursive",
            "scope_paths": [str(p.resolve())],
            "stages": ["bird_species"],
            "skip_done": True,
            "force_rerun": False,
            "fix_incomplete_stages": False,
            "validation_repair_mode": False,
            "validation_repair_dry_run": False,
            "generate_captions": False,
        },
    )
    assert r.status_code == 400
    detail = r.json().get("detail")
    assert detail["missing"]["bird_species"] == ["keywords"]


def test_process_all_does_not_bypass_missing_prereq(api_client, tmp_path, _stub_compute_scope_phases):
    p = tmp_path / "scope"
    p.mkdir()
    r = api_client.post(
        "/api/runs/submit",
        json={
            "scope_type": "folder_recursive",
            "scope_paths": [str(p.resolve())],
            "stages": ["scoring"],
            "skip_done": False,
            "force_rerun": True,
            "fix_incomplete_stages": False,
            "validation_repair_mode": False,
            "validation_repair_dry_run": False,
            "generate_captions": False,
        },
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
    _stub_compute_scope_phases.add("indexing")

    p = tmp_path / "scope"
    p.mkdir()
    r = api_client.post(
        "/api/runs/submit",
        json={
            "scope_type": "folder_recursive",
            "scope_paths": [str(p.resolve())],
            "stages": ["metadata", "scoring"],
            "skip_done": True,
            "force_rerun": False,
            "fix_incomplete_stages": False,
            "validation_repair_mode": False,
            "validation_repair_dry_run": False,
            "generate_captions": False,
        },
    )
    assert r.status_code == 200
    assert r.json().get("success") is True
