"""
Tests for reorganized similarity API and streaming import endpoint.
"""

import pytest
import json
import os
from unittest.mock import MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from modules import api, similar_search, db

# Mocking modules that might not be available or need complex setup
try:
    from modules.phases import PhaseCode, PhaseStatus
except ImportError:
    # Stubs for testing if not available
    class PhaseCode:
        INDEXING = "indexing"
    class PhaseStatus:
        DONE = "done"

def _build_client():
    app = FastAPI()
    app.include_router(api.create_api_router())
    return TestClient(app)

def _mock_db_image_exists(monkeypatch):
    """Mock db.get_db so the image existence check passes (image_id=1 exists)."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (1,)
    mock_conn.cursor.return_value = mock_cursor
    monkeypatch.setattr(db, "get_db", lambda: mock_conn)

def test_similarity_search_new_endpoint(monkeypatch):
    def mock_search(example_image_id, limit, folder_path, min_similarity):
        return [{"id": 123, "similarity": 0.95}]
    
    monkeypatch.setattr(similar_search, "search_similar_images", mock_search)
    _mock_db_image_exists(monkeypatch)
    
    with _build_client() as client:
        response = client.get("/api/similarity/search?image_id=1")
    
    assert response.status_code == 200
    data = response.json()
    assert data["query_image_id"] == 1
    assert data["results"] == [{"id": 123, "similarity": 0.95}]
    assert data["count"] == 1

def test_similarity_search_alias(monkeypatch):
    def mock_search(example_image_id, limit, folder_path, min_similarity):
        return [{"id": 123, "similarity": 0.95}]
    
    monkeypatch.setattr(similar_search, "search_similar_images", mock_search)
    _mock_db_image_exists(monkeypatch)
    
    with _build_client() as client:
        response = client.get("/api/similar?image_id=1")
    
    assert response.status_code == 200
    data = response.json()
    assert data["query_image_id"] == 1
    assert data["results"] == [{"id": 123, "similarity": 0.95}]
    assert data["count"] == 1

def test_find_duplicates_new_endpoint(monkeypatch):
    def mock_duplicates(threshold, folder_path, limit):
        return [{"image1": "a.jpg", "image2": "b.jpg", "similarity": 0.99}]
    
    monkeypatch.setattr(similar_search, "find_near_duplicates", mock_duplicates)
    
    with _build_client() as client:
        response = client.post("/api/similarity/duplicates", json={"folder_path": "test", "threshold": 0.9})
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["duplicates"] == [{"image1": "a.jpg", "image2": "b.jpg", "similarity": 0.99}]

def test_find_outliers_new_endpoint(monkeypatch):
    def mock_outliers(folder_path, z_threshold, k, limit):
        return {
            "outliers": [
                {
                    "image_id": 999,
                    "file_path": "/path/to/img.jpg",
                    "outlier_score": 3.5,
                    "z_score": -2.0,
                    "nearest_neighbors": [],
                }
            ],
            "stats": {"total_with_embeddings": 10},
            "skipped": [],
        }
    
    monkeypatch.setattr(similar_search, "find_outliers", mock_outliers)
    
    with _build_client() as client:
        response = client.get("/api/similarity/outliers?folder_path=test")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data["outliers"]) == 1
    assert data["outliers"][0]["image_id"] == 999
    assert data["outliers"][0]["outlier_score"] == 3.5

def test_import_register_stream(monkeypatch):
    # Mocking OS and DB interactions
    monkeypatch.setattr(os.path, "isdir", lambda x: True)
    monkeypatch.setattr(os, "listdir", lambda x: ["img1.jpg", "img2.jpg", "not_an_image.txt"])
    monkeypatch.setattr(os.path, "isfile", lambda x: True)
    
    monkeypatch.setattr(db, "get_or_create_folder", lambda x: 1)
    monkeypatch.setattr(db, "find_image_id_by_path", lambda x: None)
    monkeypatch.setattr(db, "register_image_for_import", lambda *args: (123, True))
    monkeypatch.setattr(db, "set_image_phase_status", lambda *args, **kwargs: None)
    
    # Mock rate limit and version if needed
    monkeypatch.setattr("modules.ui.security._check_rate_limit", lambda x: None)
    
    # Mock extract_exif to avoid external dependencies
    monkeypatch.setattr("modules.exif_extractor.extract_exif", lambda x: {})

    with _build_client() as client:
        # Use a context manager to handle the steam
        with client.stream("POST", "/api/import/register/stream", json={"folder_path": "test/path"}) as response:
            assert response.status_code == 200
            
            lines = []
            for line in response.iter_lines():
                if line:
                    lines.append(json.loads(line))
            
            # Verify stream structure
            assert any(l["type"] == "init" for l in lines)
            assert any(l["type"] == "progress" for l in lines)
            assert any(l["type"] == "done" for l in lines)
            
            init_msg = next(l for l in lines if l["type"] == "init")
            assert init_msg["total_files"] == 3 # img1, img2, not_an_image.txt
            
            done_msg = next(l for l in lines if l["type"] == "done")
            assert done_msg["added"] == 2 # Only jpgs
            assert done_msg["success"] is True

def test_import_register_legacy(monkeypatch):
    monkeypatch.setattr(os.path, "isdir", lambda x: True)
    monkeypatch.setattr(os, "listdir", lambda x: ["img1.jpg"])
    monkeypatch.setattr(os.path, "isfile", lambda x: True)
    monkeypatch.setattr(db, "get_or_create_folder", lambda x: 1)
    monkeypatch.setattr(db, "find_image_id_by_path", lambda x: None)
    monkeypatch.setattr(db, "register_image_for_import", lambda *args: (123, True))
    monkeypatch.setattr(db, "set_image_phase_status", lambda *args, **kwargs: None)
    monkeypatch.setattr("modules.ui.security._check_rate_limit", lambda x: None)
    monkeypatch.setattr("modules.exif_extractor.extract_exif", lambda x: {})

    with _build_client() as client:
        response = client.post("/api/import/register", json={"folder_path": "test/path"})
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "Import complete" in data["message"]
    assert data["data"]["added"] == 1


def test_import_register_backfills_indexing_on_existing_path(monkeypatch):
    """Re-importing the same path should mark indexing (Discovery) done if it was missing."""
    phase_calls = []

    def capture_set(*args, **kwargs):
        phase_calls.append({"args": args, "kwargs": kwargs})

    monkeypatch.setattr(os.path, "isdir", lambda x: True)
    monkeypatch.setattr(os, "listdir", lambda x: ["dup.jpg"])
    monkeypatch.setattr(os.path, "isfile", lambda x: True)
    monkeypatch.setattr(db, "get_or_create_folder", lambda x: 1)
    monkeypatch.setattr(db, "find_image_id_by_path", lambda x: 99)
    monkeypatch.setattr(db, "get_image_phase_status", lambda image_id, phase: None)
    monkeypatch.setattr(db, "set_image_phase_status", capture_set)
    monkeypatch.setattr("modules.ui.security._check_rate_limit", lambda x: None)
    monkeypatch.setattr("modules.exif_extractor.extract_exif", lambda x: {})

    with _build_client() as client:
        response = client.post("/api/import/register", json={"folder_path": "test/path"})

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["added"] == 0
    assert body["data"]["skipped"] == 1
    assert len(phase_calls) == 1
    assert phase_calls[0]["kwargs"].get("executor_version") == "1.0.0"


def test_import_register_no_backfill_when_indexing_already_done(monkeypatch):
    phase_calls = []

    def capture_set(*args, **kwargs):
        phase_calls.append({"args": args, "kwargs": kwargs})

    monkeypatch.setattr(os.path, "isdir", lambda x: True)
    monkeypatch.setattr(os, "listdir", lambda x: ["dup.jpg"])
    monkeypatch.setattr(os.path, "isfile", lambda x: True)
    monkeypatch.setattr(db, "get_or_create_folder", lambda x: 1)
    monkeypatch.setattr(db, "find_image_id_by_path", lambda x: 99)
    monkeypatch.setattr(
        db,
        "get_image_phase_status",
        lambda image_id, phase: {"status": PhaseStatus.DONE},
    )
    monkeypatch.setattr(db, "set_image_phase_status", capture_set)
    monkeypatch.setattr("modules.ui.security._check_rate_limit", lambda x: None)
    monkeypatch.setattr("modules.exif_extractor.extract_exif", lambda x: {})

    with _build_client() as client:
        response = client.post("/api/import/register", json={"folder_path": "test/path"})

    assert response.status_code == 200
    assert len(phase_calls) == 0
