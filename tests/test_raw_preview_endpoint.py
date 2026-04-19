"""Tests for /api/raw-preview binary-response behavior."""

import pytest

try:
    from fastapi import APIRouter, FastAPI
    from fastapi.testclient import TestClient
    from PIL import Image

    from modules import api, api_db
    from modules.ui import app as ui_app
except ImportError as exc:  # pragma: no cover - environment-dependent
    pytest.skip(f"API deps not available: {exc}", allow_module_level=True)


def _build_client(monkeypatch) -> TestClient:
    monkeypatch.setattr(api, "create_api_router", lambda: APIRouter())
    monkeypatch.setattr(api, "create_public_api_router", lambda: APIRouter())
    monkeypatch.setattr(api_db, "router", APIRouter())

    app = FastAPI()
    ui_app.setup_server_endpoints(app)
    return TestClient(app)


def test_raw_preview_404_passthrough(monkeypatch, tmp_path):
    client = _build_client(monkeypatch)
    missing = tmp_path / "missing.nef"
    monkeypatch.setattr(ui_app.utils, "resolve_file_path", lambda p: p)
    monkeypatch.setattr(ui_app.utils, "convert_path_to_local", lambda p: p)
    monkeypatch.setattr(ui_app, "_validate_file_path", lambda p: p)

    response = client.get("/api/raw-preview", params={"path": str(missing)})

    assert response.status_code == 404
    assert response.json()["detail"] == "File not found"


def test_raw_preview_400_passthrough_for_unsupported_format(monkeypatch, tmp_path):
    client = _build_client(monkeypatch)
    unsupported = tmp_path / "image.jpg"
    unsupported.write_bytes(b"not-raw")
    monkeypatch.setattr(ui_app.utils, "resolve_file_path", lambda p: p)
    monkeypatch.setattr(ui_app.utils, "convert_path_to_local", lambda p: p)
    monkeypatch.setattr(ui_app, "_validate_file_path", lambda p: p)

    response = client.get("/api/raw-preview", params={"path": str(unsupported)})

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported format"


def test_raw_preview_success_returns_jpeg_response(monkeypatch, tmp_path):
    client = _build_client(monkeypatch)
    raw_file = tmp_path / "image.nef"
    raw_file.write_bytes(b"raw-data")
    monkeypatch.setattr(ui_app.utils, "resolve_file_path", lambda p: p)
    monkeypatch.setattr(ui_app.utils, "convert_path_to_local", lambda p: p)
    monkeypatch.setattr(ui_app, "_validate_file_path", lambda p: p)
    monkeypatch.setattr(
        ui_app.thumbnails,
        "extract_embedded_jpeg",
        lambda *_args, **_kwargs: Image.new("RGB", (16, 16), color="white"),
    )

    response = client.get("/api/raw-preview", params={"path": str(raw_file)})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/jpeg")
    assert response.headers["cache-control"] == "public, max-age=3600"
    assert response.content.startswith(b"\xff\xd8")
