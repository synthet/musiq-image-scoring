"""POST /api/tagging/start and /clustering/start enqueue the full dependency prefix.

Guards against the "index + tags, no score" regression: these legacy single-phase
endpoints must expand to their contiguous pipeline prefix so keywords/culling can
never be marked done while metadata/scoring stay not_started.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules import api, db


class _RunnerStub:
    is_running = False

    def stop(self):
        return None


def _build_client():
    app = FastAPI()
    app.include_router(api.create_api_router())
    return TestClient(app)


def _capture_phases(monkeypatch):
    captured = {}

    def fake_enqueue_job(input_path, phase_code, job_type=None, queue_payload=None, description=None):
        captured["phase_code"] = phase_code
        return 777, 1

    def fake_create_job_phases(job_id, phases_list, first_phase_state="queued", *a, **k):
        captured["phases"] = list(phases_list)
        return []

    monkeypatch.setattr(db, "enqueue_job", fake_enqueue_job)
    monkeypatch.setattr(db, "create_job_phases", fake_create_job_phases)
    monkeypatch.setattr(
        api, "resolve_selectors", lambda **kwargs: {"resolved_image_ids": [1, 2, 3]}
    )
    return captured


def test_tagging_start_enqueues_full_prefix(monkeypatch):
    monkeypatch.setattr(api, "_tagging_runner", _RunnerStub())
    captured = _capture_phases(monkeypatch)

    with _build_client() as client:
        response = client.post("/api/tagging/start", json={"image_ids": [1, 2, 3]})

    assert response.status_code == 200, response.text
    assert captured["phase_code"] == "keywords"
    assert captured["phases"] == ["indexing", "metadata", "scoring", "keywords"]


def test_clustering_start_enqueues_full_prefix(monkeypatch):
    monkeypatch.setattr(api, "_clustering_runner", _RunnerStub())
    monkeypatch.setattr("modules.ui.security._check_rate_limit", lambda *a, **k: None)
    captured = _capture_phases(monkeypatch)

    with _build_client() as client:
        response = client.post("/api/clustering/start", json={"image_ids": [1, 2, 3]})

    assert response.status_code == 200, response.text
    assert captured["phase_code"] == "culling"
    # culling prefix excludes keywords (sibling under scoring).
    assert captured["phases"] == ["indexing", "metadata", "scoring", "culling"]
