"""Tests for POST /api/bird-species/start selector payload."""

import json

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


def test_bird_species_start_selector_stores_stage_queue(monkeypatch):
    monkeypatch.setattr(api, "_bird_species_runner", _RunnerStub())
    monkeypatch.setattr(
        api,
        "resolve_selectors",
        lambda **kwargs: {"resolved_image_ids": [10, 20, 30]},
    )

    captured = {}

    def fake_enqueue_job(input_path, phase_code, job_type=None, queue_payload=None, description=None):
        captured["input_path"] = input_path
        captured["job_type"] = job_type
        captured["queue_payload"] = queue_payload
        return 501, 2

    monkeypatch.setattr(db, "enqueue_job", fake_enqueue_job)
    monkeypatch.setattr(db, "create_job_phases", lambda *a, **k: [])

    with _build_client() as client:
        response = client.post(
            "/api/bird-species/start",
            json={"image_ids": [10, 20, 30]},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["resolved_count"] == 3

    assert captured["input_path"] == "SELECTOR_BIRD_SPECIES"
    assert captured["job_type"] == "bird_species"
    payload = captured["queue_payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    assert payload["resolved_image_ids"] == [10, 20, 30]
    assert payload["resolved_image_ids_by_stage"]["bird_species"] == [10, 20, 30]
