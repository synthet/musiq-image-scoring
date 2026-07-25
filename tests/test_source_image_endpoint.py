"""Tests for GET /source-image endpoint behavior and schema registration."""

import pytest

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from PIL import Image

    from scripts.export_openapi import build_app
    from modules.ui import source_image_api
except ImportError as e:
    pytest.skip(f"source-image deps not available: {e}", allow_module_level=True)


def _build_client():
    app = FastAPI()
    app.include_router(source_image_api.router)
    return TestClient(app)


def test_source_image_serves_non_raw_media_type(monkeypatch, tmp_path):
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
        b"\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc```\x00\x00\x00\x04\x00\x01"
        b"\x0d\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    monkeypatch.setattr(source_image_api.utils, "resolve_file_path", lambda p: p)
    monkeypatch.setattr(source_image_api.utils, "convert_path_to_local", lambda p: p)
    monkeypatch.setattr(source_image_api, "_validate_file_path", lambda p: p)

    with _build_client() as client:
        response = client.get("/source-image", params={"path": str(image_path)})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")


def test_source_image_serves_raw_preview_jpeg(monkeypatch, tmp_path):
    raw_path = tmp_path / "sample.nef"
    raw_path.write_bytes(b"raw")

    monkeypatch.setattr(source_image_api.utils, "resolve_file_path", lambda p: p)
    monkeypatch.setattr(source_image_api.utils, "convert_path_to_local", lambda p: p)
    monkeypatch.setattr(source_image_api, "_validate_file_path", lambda p: p)
    monkeypatch.setattr(
        source_image_api.thumbnails,
        "extract_embedded_jpeg",
        lambda *_a, **_kw: Image.new("RGB", (1201, 1000), color=(1, 2, 3)),
    )

    with _build_client() as client:
        response = client.get("/source-image", params={"path": str(raw_path)})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/jpeg")


def test_source_image_raw_large_embedded_preview_calls_exif_transpose(monkeypatch, tmp_path):
    """Regression: RAW in-memory path must run ImageOps.exif_transpose before JPEG encode."""
    import PIL.ImageOps

    raw_path = tmp_path / "orient.nef"
    raw_path.write_bytes(b"raw")
    monkeypatch.setattr(source_image_api.utils, "resolve_file_path", lambda p: p)
    monkeypatch.setattr(source_image_api.utils, "convert_path_to_local", lambda p: p)
    monkeypatch.setattr(source_image_api, "_validate_file_path", lambda p: p)
    monkeypatch.setattr(
        source_image_api.thumbnails,
        "extract_embedded_jpeg",
        lambda *_a, **_kw: Image.new("RGB", (1201, 1000), color=(5, 5, 5)),
    )
    monkeypatch.setattr(source_image_api.thumbnails, "read_orientation", lambda _p: None)
    called: list[object] = []

    def spy_transpose(im):
        called.append(im)
        return im

    monkeypatch.setattr(PIL.ImageOps, "exif_transpose", spy_transpose)

    with _build_client() as client:
        response = client.get("/source-image", params={"path": str(raw_path)})
    assert response.status_code == 200
    assert len(called) == 1


def test_source_image_raw_bakes_orientation_from_source_when_jpeg_lacks_exif(
    monkeypatch, tmp_path
):
    """Vertical NEF: embedded JPEG often has no Orientation; stamp from RAW then bake."""
    import io

    raw_path = tmp_path / "portrait.nef"
    raw_path.write_bytes(b"raw")
    monkeypatch.setattr(source_image_api.utils, "resolve_file_path", lambda p: p)
    monkeypatch.setattr(source_image_api.utils, "convert_path_to_local", lambda p: p)
    monkeypatch.setattr(source_image_api, "_validate_file_path", lambda p: p)
    # Storage landscape large enough that after Orientation-6 bake, width stays > 1000
    # so the in-memory JPEG path is used (not generate_preview fallback).
    monkeypatch.setattr(
        source_image_api.thumbnails,
        "extract_embedded_jpeg",
        lambda *_a, **_kw: Image.new("RGB", (1600, 1200), color=(10, 20, 30)),
    )
    monkeypatch.setattr(source_image_api.thumbnails, "read_orientation", lambda _p: 6)

    with _build_client() as client:
        response = client.get("/source-image", params={"path": str(raw_path)})
    assert response.status_code == 200
    out = Image.open(io.BytesIO(response.content))
    # Orientation 6 swaps storage landscape → upright portrait
    assert out.size == (1200, 1600)


def test_source_image_raw_orientation_noop_when_source_is_normal(monkeypatch, tmp_path):
    """Orientation 1 / missing: leave storage dimensions unchanged."""
    import io

    raw_path = tmp_path / "landscape.nef"
    raw_path.write_bytes(b"raw")
    monkeypatch.setattr(source_image_api.utils, "resolve_file_path", lambda p: p)
    monkeypatch.setattr(source_image_api.utils, "convert_path_to_local", lambda p: p)
    monkeypatch.setattr(source_image_api, "_validate_file_path", lambda p: p)
    monkeypatch.setattr(
        source_image_api.thumbnails,
        "extract_embedded_jpeg",
        lambda *_a, **_kw: Image.new("RGB", (1201, 1000), color=(1, 1, 1)),
    )
    monkeypatch.setattr(source_image_api.thumbnails, "read_orientation", lambda _p: 1)

    with _build_client() as client:
        response = client.get("/source-image", params={"path": str(raw_path)})
    assert response.status_code == 200
    out = Image.open(io.BytesIO(response.content))
    assert out.size == (1201, 1000)


def test_source_image_returns_404_for_missing_file(monkeypatch, tmp_path):
    missing_path = tmp_path / "missing.jpg"
    monkeypatch.setattr(source_image_api.utils, "resolve_file_path", lambda p: p)
    monkeypatch.setattr(source_image_api.utils, "convert_path_to_local", lambda p: p)
    monkeypatch.setattr(source_image_api, "_validate_file_path", lambda p: p)

    with _build_client() as client:
        response = client.get("/source-image", params={"path": str(missing_path)})
    assert response.status_code == 404
    assert response.json()["detail"] == "File not found"


def test_source_image_returns_422_when_path_missing():
    with _build_client() as client:
        response = client.get("/source-image")
    assert response.status_code == 422


def test_source_image_returns_400_for_path_validation_failure(monkeypatch, tmp_path):
    image_path = tmp_path / "bad.jpg"
    image_path.write_bytes(b"x")
    monkeypatch.setattr(source_image_api.utils, "resolve_file_path", lambda p: p)
    monkeypatch.setattr(source_image_api.utils, "convert_path_to_local", lambda p: p)

    from fastapi import HTTPException

    monkeypatch.setattr(
        source_image_api,
        "_validate_file_path",
        lambda _p: (_ for _ in ()).throw(HTTPException(status_code=400, detail="Invalid path")),
    )

    with _build_client() as client:
        response = client.get("/source-image", params={"path": str(image_path)})
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid path"


def test_export_schema_includes_source_image_path():
    app = build_app()
    schema = app.openapi()
    assert "/source-image" in schema["paths"]
