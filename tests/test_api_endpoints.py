"""
Tests for REST API endpoints in modules/api.py.

Uses FastAPI TestClient with mocked runners and DB functions.
No real DB or ML models are needed.

Skipped automatically when ML/framework dependencies are not installed
(tensorflow, torch) — same pattern as other runner tests.
"""

import pytest

FastAPI = None
TestClient = None
api = None
db = None
ui_security = None


def _ensure_api_deps_loaded():
    """Import API test deps lazily so module import stays lightweight."""
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


# ---------------------------------------------------------------------------
# Helpers / Stubs
# ---------------------------------------------------------------------------

class _RunnerStub:
    """Minimal stand-in for any runner."""
    is_running = False
    job_type = None

    def get_status(self):
        return (False, "", "Idle", 0, 0)

    def stop(self):
        pass

    def start_fix_db(self, job_id):
        return "Started"

    def run_single_image(self, file_path):
        return (True, "OK")

    def fix_image_metadata(self, file_path):
        return (True, "OK")


def _build_client():
    _ensure_api_deps_loaded()
    app = FastAPI()
    app.include_router(api.create_api_router())
    app.include_router(api.create_public_api_router())
    return TestClient(app)


def _noop_rate_limit(endpoint):
    pass


def _noop_resolve_selectors(**kwargs):
    return {"resolved_image_ids": []}


# ---------------------------------------------------------------------------
# Health / Schema
# ---------------------------------------------------------------------------

def test_health_returns_healthy_when_no_runners(monkeypatch):
    with _build_client() as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["scoring_available"] is False
    assert data["tagging_available"] is False
    assert data["clustering_available"] is False


def test_minimal_environment_executes_health_endpoint():
    import sys

    with _build_client() as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert "modules.ui.app" not in sys.modules


def test_health_reflects_available_runners(monkeypatch):
    monkeypatch.setattr(api, "_scoring_runner", _RunnerStub())
    monkeypatch.setattr(api, "_tagging_runner", _RunnerStub())
    with _build_client() as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["scoring_available"] is True
    assert data["tagging_available"] is True
    assert data["clustering_available"] is False


def test_schema_returns_dict_with_api_name(monkeypatch):
    with _build_client() as client:
        response = client.get("/api/schema")
    assert response.status_code == 200
    data = response.json()
    assert "api_name" in data
    assert "endpoints" in data


def test_diagnostics_returns_full_payload(monkeypatch):
    from modules import diagnostics
    monkeypatch.setattr(diagnostics, "get_diagnostics", lambda: {
        "timestamp": "2024-03-24T00:00:00",
        "system": {"os": "TestOS"},
        "database": {"reachable": True},
        "models": {"gpu_available": False},
        "filesystem": {"free_space_gb": 100},
        "config": {"debug": True}
    })
    with _build_client() as client:
        response = client.get("/api/diagnostics")
    assert response.status_code == 200
    data = response.json()
    assert data["system"]["os"] == "TestOS"
    assert "runners" in data
    assert data["runners"]["scoring"] == "unavailable"


# ---------------------------------------------------------------------------
# Scoring endpoints
# ---------------------------------------------------------------------------

def test_scoring_status_returns_503_when_runner_unavailable(monkeypatch):
    monkeypatch.setattr(api, "_scoring_runner", None)
    with _build_client() as client:
        response = client.get("/api/scoring/status")
    assert response.status_code == 503


def test_scoring_status_returns_idle_fields(monkeypatch):
    monkeypatch.setattr(api, "_scoring_runner", _RunnerStub())
    with _build_client() as client:
        response = client.get("/api/scoring/status")
    assert response.status_code == 200
    data = response.json()
    assert data["is_running"] is False
    assert "status_message" in data
    assert "progress" in data
    assert "current" in data["progress"]
    assert "total" in data["progress"]
    assert "log" in data


def test_scoring_start_returns_503_when_runner_unavailable(monkeypatch):
    monkeypatch.setattr(api, "_scoring_runner", None)
    with _build_client() as client:
        response = client.post("/api/scoring/start", json={"input_path": "/tmp"})
    assert response.status_code == 503


def test_scoring_start_returns_400_when_no_selector(monkeypatch):
    monkeypatch.setattr(api, "_scoring_runner", _RunnerStub())
    monkeypatch.setattr(ui_security, "_check_rate_limit", _noop_rate_limit)
    with _build_client() as client:
        response = client.post("/api/scoring/start", json={})
    assert response.status_code == 400


def test_scoring_start_enqueues_job_and_returns_job_id(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "_scoring_runner", _RunnerStub())
    monkeypatch.setattr(ui_security, "_check_rate_limit", _noop_rate_limit)
    monkeypatch.setattr("modules.selector_resolver.resolve_selectors", _noop_resolve_selectors)
    monkeypatch.setattr(db, "create_job_phases", lambda *a, **kw: [])
    monkeypatch.setattr(db, "enqueue_job", lambda *a, **kw: (42, 1))
    with _build_client() as client:
        response = client.post("/api/scoring/start", json={"input_path": str(tmp_path)})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["job_id"] == 42


def test_scoring_stop_returns_503_when_runner_unavailable(monkeypatch):
    monkeypatch.setattr(api, "_scoring_runner", None)
    with _build_client() as client:
        response = client.post("/api/scoring/stop")
    assert response.status_code == 503


def test_scoring_stop_returns_false_when_not_running(monkeypatch):
    stub = _RunnerStub()
    stub.is_running = False
    monkeypatch.setattr(api, "_scoring_runner", stub)
    with _build_client() as client:
        response = client.post("/api/scoring/stop")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False


def test_scoring_stop_sends_signal_when_running(monkeypatch):
    stub = _RunnerStub()
    stub.is_running = True
    stopped = []
    stub.stop = lambda: stopped.append(True)
    monkeypatch.setattr(api, "_scoring_runner", stub)
    with _build_client() as client:
        response = client.post("/api/scoring/stop")
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert stopped == [True]


# ---------------------------------------------------------------------------
# Tagging endpoints
# ---------------------------------------------------------------------------

def test_tagging_status_returns_503_when_runner_unavailable(monkeypatch):
    monkeypatch.setattr(api, "_tagging_runner", None)
    with _build_client() as client:
        response = client.get("/api/tagging/status")
    assert response.status_code == 503


def test_tagging_status_returns_status_fields(monkeypatch):
    monkeypatch.setattr(api, "_tagging_runner", _RunnerStub())
    with _build_client() as client:
        response = client.get("/api/tagging/status")
    assert response.status_code == 200
    data = response.json()
    assert "is_running" in data
    assert data["job_type"] == "tagging"


def test_tagging_start_returns_503_when_runner_unavailable(monkeypatch):
    monkeypatch.setattr(api, "_tagging_runner", None)
    with _build_client() as client:
        response = client.post("/api/tagging/start", json={"input_path": "/tmp"})
    assert response.status_code == 503


def test_tagging_start_returns_400_when_no_selector(monkeypatch):
    monkeypatch.setattr(api, "_tagging_runner", _RunnerStub())
    monkeypatch.setattr(ui_security, "_check_rate_limit", _noop_rate_limit)
    with _build_client() as client:
        response = client.post("/api/tagging/start", json={})
    assert response.status_code == 400


def test_tagging_start_enqueues_job(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "_tagging_runner", _RunnerStub())
    monkeypatch.setattr(ui_security, "_check_rate_limit", _noop_rate_limit)
    monkeypatch.setattr("modules.selector_resolver.resolve_selectors", _noop_resolve_selectors)
    monkeypatch.setattr(db, "create_job_phases", lambda *a, **kw: [])
    monkeypatch.setattr(db, "enqueue_job", lambda *a, **kw: (99, 2))
    with _build_client() as client:
        response = client.post("/api/tagging/start", json={"input_path": str(tmp_path)})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["job_id"] == 99


def test_tagging_stop_not_running_returns_false(monkeypatch):
    stub = _RunnerStub()
    stub.is_running = False
    monkeypatch.setattr(api, "_tagging_runner", stub)
    with _build_client() as client:
        response = client.post("/api/tagging/stop")
    assert response.status_code == 200
    assert response.json()["success"] is False


# ---------------------------------------------------------------------------
# Clustering endpoints
# ---------------------------------------------------------------------------

def test_clustering_status_returns_503_when_runner_unavailable(monkeypatch):
    monkeypatch.setattr(api, "_clustering_runner", None)
    with _build_client() as client:
        response = client.get("/api/clustering/status")
    assert response.status_code == 503


def test_clustering_start_returns_503_when_runner_unavailable(monkeypatch):
    monkeypatch.setattr(api, "_clustering_runner", None)
    with _build_client() as client:
        response = client.post("/api/clustering/start", json={"input_path": "/tmp"})
    assert response.status_code == 503


def test_clustering_start_returns_400_when_no_selector(monkeypatch):
    monkeypatch.setattr(api, "_clustering_runner", _RunnerStub())
    monkeypatch.setattr(ui_security, "_check_rate_limit", _noop_rate_limit)
    with _build_client() as client:
        response = client.post("/api/clustering/start", json={})
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Images endpoints
# ---------------------------------------------------------------------------

class _StubImageRow:
    def __init__(self, payload):
        self._payload = payload

    def to_dict(self, exclude_keys=None):
        return dict(self._payload)


def test_images_returns_paginated_list(monkeypatch):
    stub_images = [_StubImageRow({"id": 1, "file_path": "/photos/a.jpg", "score": 0.8})]
    monkeypatch.setattr(db, "get_images_paginated_with_count", lambda **kw: (stub_images, 1))
    with _build_client() as client:
        response = client.get("/api/images")
    assert response.status_code == 200
    data = response.json()
    assert "images" in data
    assert data["total"] == 1
    assert data["page"] == 1
    assert "total_pages" in data


def test_public_api_images_returns_same_shape(monkeypatch):
    stub_images = [_StubImageRow({"id": 1, "file_path": "/photos/a.jpg", "score": 0.8})]
    monkeypatch.setattr(db, "get_images_paginated_with_count", lambda **kw: (stub_images, 1))
    with _build_client() as client:
        response = client.get("/public/api/images")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["images"][0]["id"] == 1


def test_images_returns_empty_list(monkeypatch):
    monkeypatch.setattr(db, "get_images_paginated_with_count", lambda **kw: ([], 0))
    with _build_client() as client:
        response = client.get("/api/images")
    assert response.status_code == 200
    data = response.json()
    assert data["images"] == []
    assert data["total"] == 0


def test_image_by_id_returns_404_for_missing(monkeypatch):
    class _FakeConn:
        def cursor(self):
            return _FakeCur()
        def close(self):
            pass

    class _FakeCur:
        def execute(self, *a):
            pass
        def fetchone(self):
            return None

    monkeypatch.setattr(db, "get_db", lambda: _FakeConn())
    with _build_client() as client:
        response = client.get("/api/images/9999")
        response_public = client.get("/public/api/images/9999")
    assert response.status_code == 404
    assert response_public.status_code == 404


def test_image_exif_returns_json_safe_dict(monkeypatch):
    monkeypatch.setattr(
        db,
        "get_image_exif",
        lambda _id: {"image_id": 1, "make": "Nikon", "model": "Z6"},
    )
    with _build_client() as client:
        response = client.get("/api/images/1/exif")
    assert response.status_code == 200
    assert response.json() == {"image_id": 1, "make": "Nikon", "model": "Z6"}


def test_image_xmp_returns_empty_when_missing(monkeypatch):
    monkeypatch.setattr(db, "get_image_xmp", lambda _id: None)
    with _build_client() as client:
        response = client.get("/api/images/42/xmp")
    assert response.status_code == 200
    assert response.json() == {}


# ---------------------------------------------------------------------------
# Folders endpoints
# ---------------------------------------------------------------------------

def test_folders_returns_list_and_count(monkeypatch):
    stub_folders = [{"id": 1, "folder_path": "/photos/2024"}]
    monkeypatch.setattr(db, "get_all_folders", lambda: stub_folders)
    with _build_client() as client:
        response = client.get("/api/folders")
    assert response.status_code == 200
    data = response.json()
    assert "folders" in data
    assert data["count"] == 1
    assert data["folders"][0]["folder_path"] == "/photos/2024"


def test_folders_rebuild_calls_rebuild_and_returns_folders(monkeypatch):
    rebuilt = []
    monkeypatch.setattr(db, "rebuild_folder_cache", lambda: rebuilt.append(True))
    monkeypatch.setattr(db, "get_all_folders", lambda: [])
    with _build_client() as client:
        response = client.post("/api/folders/rebuild")
    assert response.status_code == 200
    assert rebuilt == [True]
    data = response.json()
    assert "folders" in data


def test_delete_folder_cache_success(monkeypatch):
    monkeypatch.setattr(
        db,
        "delete_empty_folder_cache_subtree",
        lambda p: {"success": True, "message": "OK", "deleted_folders": 2, "reason": None},
    )
    with _build_client() as client:
        response = client.request(
            "DELETE",
            "/api/folders/cache",
            json={"path": "/photos/empty"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["deleted_folders"] == 2


def test_delete_folder_cache_not_found(monkeypatch):
    monkeypatch.setattr(
        db,
        "delete_empty_folder_cache_subtree",
        lambda p: {"success": False, "message": "nope", "deleted_folders": 0, "reason": "not_found"},
    )
    with _build_client() as client:
        response = client.request("DELETE", "/api/folders/cache", json={"path": "/nope"})
    assert response.status_code == 404


def test_delete_folder_cache_not_empty(monkeypatch):
    monkeypatch.setattr(
        db,
        "delete_empty_folder_cache_subtree",
        lambda p: {"success": False, "message": "has images", "deleted_folders": 0, "reason": "not_empty"},
    )
    with _build_client() as client:
        response = client.request("DELETE", "/api/folders/cache", json={"path": "/x"})
    assert response.status_code == 409


def test_delete_folder_cache_invalid_body(monkeypatch):
    monkeypatch.setattr(
        db,
        "delete_empty_folder_cache_subtree",
        lambda p: {"success": False, "message": "No folder path", "deleted_folders": 0, "reason": "invalid"},
    )
    with _build_client() as client:
        response = client.request("DELETE", "/api/folders/cache", json={"path": "  "})
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Stats endpoint
# ---------------------------------------------------------------------------

def test_stats_returns_dict(monkeypatch):
    stub_stats = {"total_images": 100, "total_scored": 80}
    from modules import mcp_server
    monkeypatch.setattr(mcp_server, "get_database_stats", lambda: stub_stats)
    with _build_client() as client:
        response = client.get("/api/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_images" in data


# ---------------------------------------------------------------------------
# Jobs endpoints
# ---------------------------------------------------------------------------

def test_jobs_queue_returns_state_and_queue(monkeypatch):
    monkeypatch.setattr(api._job_dispatcher, "get_state", lambda: {
        "active_runner": None,
        "is_dispatcher_running": True,
    })
    monkeypatch.setattr(db, "get_queued_jobs", lambda limit=200: [])
    with _build_client() as client:
        response = client.get("/api/jobs/queue")
    assert response.status_code == 200
    data = response.json()
    assert "queue" in data
    assert data["queue_size"] == 0


def test_job_by_id_returns_404_for_missing(monkeypatch):
    monkeypatch.setattr(db, "get_job_by_id", lambda job_id: None)
    with _build_client() as client:
        response = client.get("/api/jobs/9999")
    assert response.status_code == 404


def test_job_by_id_returns_job_with_phases(monkeypatch):
    monkeypatch.setattr(db, "get_job_by_id", lambda job_id: {"id": job_id, "status": "done"})
    monkeypatch.setattr(db, "get_job_phases", lambda job_id: [])
    with _build_client() as client:
        response = client.get("/api/jobs/1")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 1
    assert "phases" in data


def test_cancel_job_returns_404_for_missing(monkeypatch):
    monkeypatch.setattr(db, "request_cancel_job", lambda job_id: {"success": False, "reason": "not_found"})
    with _build_client() as client:
        response = client.post("/api/jobs/999/cancel")
    assert response.status_code == 404


def test_cancel_job_returns_success(monkeypatch):
    monkeypatch.setattr(db, "request_cancel_job", lambda job_id: {"success": True, "status": "cancelled"})
    with _build_client() as client:
        response = client.post("/api/jobs/1/cancel")
    assert response.status_code == 200
    assert response.json()["success"] is True


# ---------------------------------------------------------------------------
# All runners status
# ---------------------------------------------------------------------------

def test_all_status_returns_all_keys(monkeypatch):
    monkeypatch.setattr(api, "_scoring_runner", _RunnerStub())
    monkeypatch.setattr(api, "_tagging_runner", _RunnerStub())
    monkeypatch.setattr(api, "_clustering_runner", _RunnerStub())
    with _build_client() as client:
        response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert "scoring" in data
    assert "tagging" in data


def test_pause_workflow_run_returns_conflict(monkeypatch):
    monkeypatch.setattr(db, "get_job_by_id", lambda job_id: {"id": job_id, "status": "completed"})
    def _raise(*args, **kwargs):
        raise ValueError("Invalid job status transition: completed -> paused")
    monkeypatch.setattr(db, "update_job_status", _raise)
    with _build_client() as client:
        response = client.post("/api/workflow-runs/1/pause", json={})
    assert response.status_code == 409


def test_resume_stage_run_success(monkeypatch):
    monkeypatch.setattr(db, "get_job_by_id", lambda job_id: {"id": job_id, "status": "paused"})
    monkeypatch.setattr(db, "get_job_phases", lambda job_id: [{"phase_code": "scoring", "state": "paused"}])
    monkeypatch.setattr(db, "set_job_phase_state", lambda *args, **kwargs: [{"phase_code": "scoring", "state": "running"}])
    with _build_client() as client:
        response = client.post("/api/stage-runs/1/scoring/resume", json={})
    assert response.status_code == 200
    assert response.json()["success"] is True


def test_restart_step_run_success(monkeypatch):
    calls = []
    monkeypatch.setattr(db, "set_image_phase_status", lambda image_id, phase_code, status, error=None: calls.append(status))
    monkeypatch.setattr(db, "get_image_phase_statuses", lambda image_id: {"scoring": {"status": "queued"}})
    with _build_client() as client:
        response = client.post("/api/step-runs/99/scoring/restart", json={})
    assert response.status_code == 200
    assert calls == ["restarting", "queued"]


# ---------------------------------------------------------------------------
# Scoring model registry endpoint
# ---------------------------------------------------------------------------

def test_models_endpoint_returns_empty_when_registry_empty(monkeypatch):
    from modules.engines.registry import reset_registry

    reset_registry()
    with _build_client() as client:
        response = client.get("/api/models")
    assert response.status_code == 200
    data = response.json()
    assert data == {"models": [], "count": 0}


def test_models_endpoint_lists_registered_models(monkeypatch):
    from modules.engines.base import IScoringModel
    from modules.engines.registry import get_registry, reset_registry

    class _Stub(IScoringModel):
        def __init__(self, name, version, framework, score_range):
            self.name = name
            self.version = version
            self.framework = framework
            self.score_range = score_range
            self.load_status = "loaded"

        def load(self):
            return True

        def predict(self, image_path):
            return {"score": 0.0, "status": "success", "error": None}

    reset_registry()
    reg = get_registry()
    reg.register(_Stub("spaq", "musiq-1", "tf", (0.0, 100.0)))
    reg.register(_Stub("liqe", "liqe-1", "torch", (1.0, 5.0)))

    monkeypatch.setattr(
        "modules.engines.registry.ModelRegistry._resolve_config",
        staticmethod(lambda cfg=None: {
            "spaq": {"enabled": True, "shadow": False},
            "liqe": {"enabled": False, "shadow": True},
        }),
    )

    with _build_client() as client:
        response = client.get("/api/models")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    by_name = {m["name"]: m for m in data["models"]}

    assert by_name["spaq"]["framework"] == "tf"
    assert by_name["spaq"]["version"] == "musiq-1"
    assert by_name["spaq"]["score_range"] == [0.0, 100.0]
    assert by_name["spaq"]["enabled"] is True
    assert by_name["spaq"]["shadow"] is False
    assert by_name["spaq"]["load_status"] == "loaded"

    assert by_name["liqe"]["framework"] == "torch"
    assert by_name["liqe"]["enabled"] is False
    assert by_name["liqe"]["shadow"] is True

    reset_registry()
