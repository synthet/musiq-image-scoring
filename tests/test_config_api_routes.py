"""Tests for GET /api/config vs GET /api/config/full."""

import json

import pytest

FastAPI = pytest.importorskip("fastapi").FastAPI
TestClient = pytest.importorskip("fastapi.testclient").TestClient

import modules.config as cfg
from modules import api as api_mod


def _build_client():
    app = FastAPI()
    app.include_router(api_mod.create_api_router())
    return TestClient(app)


def test_get_config_returns_public_flags(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(cfg, "ENVIRONMENT_FILE", tmp_path / "environment.json")
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "culling": {"enabled": True},
                "embedding_map": {"enabled": False},
                "database": {"db_explorer_enabled": False},
                "scoring": {"models": {"liqe": {"enabled": True, "shadow": False}}},
            }
        ),
        encoding="utf-8",
    )

    with _build_client() as client:
        response = client.get("/api/config")

    assert response.status_code == 200
    data = response.json()
    assert set(data.keys()) == {
        "enable_culling",
        "embedding_map_enabled",
        "db_explorer_enabled",
        "scoring_models",
    }
    assert data["enable_culling"] is True
    assert data["embedding_map_enabled"] is False
    assert data["db_explorer_enabled"] is False
    assert data["scoring_models"]["liqe"]["enabled"] is True


def test_get_config_full_returns_merged_document(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(cfg, "ENVIRONMENT_FILE", tmp_path / "environment.json")
    (tmp_path / "config.json").write_text(
        json.dumps({"scoring": {"models": {"spaq": {"enabled": True}}}}),
        encoding="utf-8",
    )
    (tmp_path / "environment.json").write_text(
        json.dumps({"ui": {"gallery_page_size": 99}}),
        encoding="utf-8",
    )

    with _build_client() as client:
        response = client.get("/api/config/full")

    assert response.status_code == 200
    data = response.json()
    assert data["scoring"]["models"]["spaq"]["enabled"] is True
    assert data["ui"]["gallery_page_size"] == 99
