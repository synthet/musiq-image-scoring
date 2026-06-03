"""FastAPI tests for culling analytics routes."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules import api, config


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(api.create_api_router())
    return TestClient(app)


@pytest.mark.db
def test_culling_analytics_endpoint(client):
    if config.get_database_engine() != "postgres":
        pytest.skip("PostgreSQL required")
    resp = client.get("/api/analytics/culling?per_stack_limit=5")
    if resp.status_code == 501:
        pytest.skip("Analytics not on postgres in this environment")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("scope") == "library"
    assert "stack_size" in data
