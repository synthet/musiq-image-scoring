"""Tests for POST /api/db/query (modules/api_db.py)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("fastapi.testclient")


def _route_paths(router) -> list[str]:
    paths: list[str] = []
    for r in router.routes:
        path = getattr(r, "path", None)
        if path:
            paths.append(path)
    return paths


def test_create_api_router_has_no_db_query_route():
    from modules import api

    router = api.create_api_router()
    paths = _route_paths(router)
    assert "/db/query" not in paths
    assert not any(p.endswith("/db/query") for p in paths)


def _test_client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from modules import api_db

    app = FastAPI()
    app.include_router(api_db.router)
    return TestClient(app)


def test_read_query_returns_rows_and_data():
    client = _test_client()
    rows = [{"id": 1, "name": "a"}]
    with patch("modules.api_db.db.execute_readonly_sql_for_api", return_value=rows) as mock_exec:
        with patch(
            "modules.config.get_config_value",
            side_effect=lambda key, default=None: default,
        ):
            resp = client.post(
                "/api/db/query",
                json={"sql": "SELECT 1", "params": [], "write": False},
            )
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows"] == rows
    assert body["data"] == rows
    assert body["rowcount"] == 1
    mock_exec.assert_called_once()
    assert mock_exec.call_args.kwargs.get("max_rows") == 5000


def test_read_query_disabled_by_config():
    client = _test_client()

    def _cfg(key, default=None):
        if key == "database.enable_api_db_query":
            return False
        return default

    with patch("modules.config.get_config_value", side_effect=_cfg):
        resp = client.post(
            "/api/db/query",
            json={"sql": "SELECT 1", "params": []},
        )
    assert resp.status_code == 403
    assert "enable_api_db_query" in resp.json()["detail"]


def test_write_without_token_returns_403():
    client = _test_client()

    def _cfg(key, default=None):
        if key == "database.enable_api_db_query":
            return True
        return default

    with patch("modules.config.get_config_value", side_effect=_cfg):
        with patch("modules.config.get_config_section", return_value={"query_token": ""}):
            resp = client.post(
                "/api/db/query",
                json={
                    "sql": "UPDATE images SET rating = 1 WHERE id = 1",
                    "params": [],
                    "write": True,
                },
            )
    assert resp.status_code == 403
    assert "query_token" in resp.json()["detail"].lower()
