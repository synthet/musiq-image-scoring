"""Tests for PATCH /api/images/{id} — covers the new pick_status field and its
mirror onto rating/label so legacy gallery filters keep working.

Uses FastAPI TestClient with stubbed DB calls; no real database is needed.
"""

from __future__ import annotations

import pytest

FastAPI = None
TestClient = None
api = None
db = None
ui_security = None


def _ensure_api_deps_loaded() -> None:
    global FastAPI, TestClient, api, db, ui_security
    if api is not None:
        return
    FastAPI = pytest.importorskip("fastapi").FastAPI
    TestClient = pytest.importorskip("fastapi.testclient").TestClient
    api = pytest.importorskip("modules.api")
    db = pytest.importorskip("modules.db")
    ui_security = pytest.importorskip("modules.ui.security")


@pytest.fixture(autouse=True)
def _api_test_deps():
    _ensure_api_deps_loaded()


def _build_client():
    app = FastAPI()
    app.include_router(api.create_api_router())
    return TestClient(app)


class _StubCursor:
    """Returns a fixed image row regardless of the SELECT executed."""

    def __init__(self, row):
        self._row = row

    def execute(self, *_args, **_kwargs):
        return None

    def fetchone(self):
        return self._row


class _StubConn:
    def __init__(self, row):
        self._row = row
        self.closed = False

    def cursor(self):
        return _StubCursor(self._row)

    def close(self):
        self.closed = True


@pytest.fixture
def patched_db(monkeypatch):
    """Stub the DB layer so PATCH handlers run without a real database."""
    captured: dict[str, object] = {"meta": None, "pick": None}

    current_row = (
        "/photos/IMG_0001.jpg",  # file_path
        "",                       # keywords
        "",                       # title
        "",                       # description
        0,                        # rating
        "",                       # label
    )

    def fake_get_db():
        return _StubConn(current_row)

    def fake_update_metadata(file_path, keywords, title, description, rating, label):
        captured["meta"] = {
            "file_path": file_path,
            "keywords": keywords,
            "title": title,
            "description": description,
            "rating": rating,
            "label": label,
        }
        return True

    def fake_update_pick(image_id, pick_status):
        captured["pick"] = {"image_id": image_id, "pick_status": pick_status}
        return True

    monkeypatch.setattr(db, "get_db", fake_get_db)
    monkeypatch.setattr(db, "update_image_metadata", fake_update_metadata)
    monkeypatch.setattr(db, "update_image_pick_status", fake_update_pick)
    monkeypatch.setattr(ui_security, "_check_rate_limit", lambda _ep: None)
    monkeypatch.setattr(api, "_tagging_runner", None)

    return captured


def test_patch_pick_marks_rating_4_and_green(patched_db):
    with _build_client() as client:
        response = client.patch(
            "/api/images/123",
            json={"pick_status": 1, "write_sidecar": False},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    assert body["data"]["pick_status"] == 1
    assert body["data"]["rating"] == 4
    assert body["data"]["label"] == "Green"

    assert patched_db["pick"] == {"image_id": 123, "pick_status": 1}
    assert patched_db["meta"]["rating"] == 4
    assert patched_db["meta"]["label"] == "Green"


def test_patch_reject_marks_rating_1_and_red(patched_db):
    with _build_client() as client:
        response = client.patch(
            "/api/images/77",
            json={"pick_status": -1, "write_sidecar": False},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["data"]["rating"] == 1
    assert body["data"]["label"] == "Red"
    assert patched_db["pick"] == {"image_id": 77, "pick_status": -1}
    assert patched_db["meta"]["rating"] == 1
    assert patched_db["meta"]["label"] == "Red"


def test_patch_unflag_clears_rating_and_label(patched_db):
    with _build_client() as client:
        response = client.patch(
            "/api/images/9",
            json={"pick_status": 0, "write_sidecar": False},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["data"]["rating"] == 0
    assert body["data"]["label"] == ""
    assert patched_db["pick"] == {"image_id": 9, "pick_status": 0}


def test_patch_explicit_rating_overrides_pick_mirror(patched_db):
    """If caller sets both pick_status and rating, the explicit rating wins."""
    with _build_client() as client:
        response = client.patch(
            "/api/images/5",
            json={"pick_status": 1, "rating": 5, "write_sidecar": False},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["rating"] == 5  # explicit wins
    assert body["data"]["label"] == "Green"  # label still mirrored
    assert patched_db["pick"] == {"image_id": 5, "pick_status": 1}


def test_patch_without_pick_status_skips_pick_helper(patched_db):
    """Plain metadata edits must NOT touch update_image_pick_status."""
    with _build_client() as client:
        response = client.patch(
            "/api/images/42",
            json={"rating": 3, "write_sidecar": False},
        )

    assert response.status_code == 200
    assert patched_db["pick"] is None
    assert patched_db["meta"]["rating"] == 3


def test_patch_rejects_pick_status_out_of_range(patched_db):
    with _build_client() as client:
        response = client.patch(
            "/api/images/1",
            json={"pick_status": 2, "write_sidecar": False},
        )

    assert response.status_code == 422
