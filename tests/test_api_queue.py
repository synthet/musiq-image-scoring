from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules import api, db
from modules.ui import security as ui_security


class _RunnerStub:
    is_running = False


class _BatchRunnerStub:
    def __init__(self, result="Started"):
        self.calls = []
        self.result = result

    def start_batch(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.result


def _build_client():
    app = FastAPI()
    app.include_router(api.create_api_router())
    return TestClient(app)


def test_tasks_active_returns_unified_state(monkeypatch):
    """GET /api/tasks/active returns runners, dispatcher, and active_job."""
    monkeypatch.setattr(api, "_scoring_runner", None)
    monkeypatch.setattr(api, "_tagging_runner", None)
    monkeypatch.setattr(api, "_clustering_runner", None)
    monkeypatch.setattr(api._job_dispatcher, "get_state", lambda: {
        "queue": [{"id": 10, "job_type": "scoring", "status": "pending"}],
        "queue_size": 1,
        "active_runner": None,
        "is_dispatcher_running": True,
    })
    monkeypatch.setattr(db, "get_queued_jobs", lambda limit=200: [{"id": 10, "job_type": "scoring", "status": "pending"}])
    monkeypatch.setattr(db, "get_jobs", lambda *a, **k: [])
    monkeypatch.setattr(db, "get_job_by_id", lambda jid: None)

    with _build_client() as client:
        response = client.get("/api/tasks/active", params={"limit": 50})

    assert response.status_code == 200
    payload = response.json()
    assert "runners" in payload
    assert payload["runners"]["scoring"]["available"] is False
    assert "dispatcher" in payload
    assert payload["dispatcher"]["queue_size"] == 1
    assert payload["dispatcher"]["active_runner"] is None
    assert payload["dispatcher"]["is_dispatcher_running"] is True
    assert "active_job" in payload
    assert payload["active_job"] is None


def test_jobs_queue_endpoint_refreshes_from_db_with_limit_zero(monkeypatch):
    monkeypatch.setattr(api._job_dispatcher, "get_state", lambda: {
        "queue": [{"id": 999, "queue_position": 1}],
        "queue_size": 1,
        "active_runner": None,
        "is_dispatcher_running": True,
    })

    calls = []

    def fake_get_queued_jobs(limit=200):
        calls.append(limit)
        return []

    monkeypatch.setattr(db, "get_queued_jobs", fake_get_queued_jobs)

    with _build_client() as client:
        response = client.get("/api/jobs/queue", params={"limit": 0})

    assert response.status_code == 200
    payload = response.json()
    assert calls == [0]
    assert payload["queue"] == []
    assert payload["queue_size"] == 0


def test_pipeline_submit_cluster_enqueues_full_payload(monkeypatch, tmp_path):
    monkeypatch.setattr(ui_security, "_check_rate_limit", lambda endpoint: None)
    monkeypatch.setattr(api, "_clustering_runner", _RunnerStub())
    monkeypatch.setattr(
        api,
        "validate_and_preview",
        lambda request: {"preview_count": 2, "resolved_image_ids": [11, 12], "missing_paths": [], "warnings": []},
    )

    captured = {}

    def fake_enqueue_job(input_path, phase_code, job_type=None, queue_payload=None, description=None):
        captured["input_path"] = input_path
        captured["phase_code"] = phase_code
        captured["job_type"] = job_type
        captured["queue_payload"] = queue_payload
        captured["description"] = description
        return 321, 7

    monkeypatch.setattr(db, "enqueue_job", fake_enqueue_job)

    created_phase_codes = {}

    def fake_create_job_phases(job_id, phase_codes, first_phase_state=None):
        created_phase_codes["job_id"] = job_id
        created_phase_codes["phase_codes"] = list(phase_codes)
        created_phase_codes["first_phase_state"] = first_phase_state
        return [
            {"phase_order": idx, "phase_code": code, "state": "running" if idx == 0 else "pending"}
            for idx, code in enumerate(phase_codes)
        ]

    monkeypatch.setattr(db, "create_job_phases", fake_create_job_phases)

    body = {
        "input_path": str(tmp_path),
        "operations": ["cluster"],
        "clustering_threshold": 0.2,
        "clustering_time_gap": 12,
        "clustering_force_rescan": True,
    }

    with _build_client() as client:
        response = client.post("/api/pipeline/submit", json=body)

    assert response.status_code == 200
    result = response.json()
    assert result["success"] is True
    assert result["data"]["queue_position"] == 7

    assert captured["phase_code"] == "culling"
    assert captured["job_type"] == "clustering"
    payload = captured["queue_payload"]
    assert payload["input_path"] == str(tmp_path)
    assert payload["threshold"] == 0.2
    assert payload["time_gap"] == 12
    assert payload["force_rescan"] is True
    assert created_phase_codes["job_id"] == 321
    assert created_phase_codes["phase_codes"] == ["culling"]


def test_pipeline_submit_metadata_enqueues_scoring_runner_with_target_phases(monkeypatch, tmp_path):
    # indexing/metadata now route to dedicated runners; first_op="indexing" uses _indexing_runner
    monkeypatch.setattr(ui_security, "_check_rate_limit", lambda endpoint: None)
    monkeypatch.setattr(api, "_indexing_runner", _RunnerStub())
    monkeypatch.setattr(
        api,
        "validate_and_preview",
        lambda request: {"preview_count": 2, "resolved_image_ids": [11, 12], "missing_paths": [], "warnings": []},
    )

    captured = {}

    def fake_enqueue_job(input_path, phase_code, job_type=None, queue_payload=None, description=None):
        captured["input_path"] = input_path
        captured["phase_code"] = phase_code
        captured["job_type"] = job_type
        captured["queue_payload"] = queue_payload
        captured["description"] = description
        return 222, 3

    monkeypatch.setattr(db, "enqueue_job", fake_enqueue_job)
    monkeypatch.setattr(
        db,
        "create_job_phases",
        lambda job_id, phase_codes, first_phase_state=None: [
            {"phase_order": idx, "phase_code": code, "state": "running" if idx == 0 else "pending"}
            for idx, code in enumerate(phase_codes)
        ],
    )

    with _build_client() as client:
        response = client.post(
            "/api/pipeline/submit",
            json={
                "input_path": str(tmp_path),
                "operations": ["indexing", "metadata"],
                "skip_existing": False,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert "indexing" in payload["message"] and "queued" in payload["message"].lower()
    assert payload["data"]["active_operation"] == "indexing"
    assert payload["data"]["remaining_operations"] == ["metadata"]
    assert captured["input_path"] == str(tmp_path)
    assert captured["phase_code"] == "indexing"
    assert captured["job_type"] == "indexing"
    qp = captured["queue_payload"]
    assert qp["input_path"] == str(tmp_path)
    assert qp["skip_existing"] is False
    assert qp["stage_codes"] == ["indexing", "metadata"]


def test_pipeline_submit_mixed_operations_only_targets_scoring_side(monkeypatch, tmp_path):
    monkeypatch.setattr(ui_security, "_check_rate_limit", lambda endpoint: None)
    monkeypatch.setattr(api, "_scoring_runner", _RunnerStub())
    monkeypatch.setattr(
        api,
        "validate_and_preview",
        lambda request: {"preview_count": 2, "resolved_image_ids": [11, 12], "missing_paths": [], "warnings": []},
    )

    captured = {}

    def fake_enqueue_job(input_path, phase_code, job_type=None, queue_payload=None, description=None):
        captured["phase_code"] = phase_code
        captured["job_type"] = job_type
        captured["queue_payload"] = queue_payload
        captured["description"] = description
        return 444, 2

    monkeypatch.setattr(db, "enqueue_job", fake_enqueue_job)
    monkeypatch.setattr(db, "create_job_phases", lambda job_id, phase_codes, first_phase_state=None: [])

    with _build_client() as client:
        response = client.post(
            "/api/pipeline/submit",
            json={
                "input_path": str(tmp_path),
                "operations": ["score", "tag", "cluster"],
                "skip_existing": True,
            },
        )

    assert response.status_code == 200
    assert response.json()["data"]["remaining_operations"] == ["tag", "cluster"]
    assert captured["phase_code"] == "scoring"
    assert captured["job_type"] == "scoring"
    qp = captured["queue_payload"]
    assert qp["input_path"] == str(tmp_path)
    assert qp["skip_existing"] is True
    assert qp["target_phases"] == ["scoring"]


def test_pipeline_submit_metadata_requires_scoring_runner(monkeypatch, tmp_path):
    # metadata routes to _metadata_runner; absence → ApiResponse failure (HTTP 200 envelope)
    monkeypatch.setattr(ui_security, "_check_rate_limit", lambda endpoint: None)
    monkeypatch.setattr(api, "_metadata_runner", None)
    monkeypatch.setattr(
        api,
        "validate_and_preview",
        lambda request: {"preview_count": 2, "resolved_image_ids": [11, 12], "missing_paths": [], "warnings": []},
    )

    with _build_client() as client:
        response = client.post(
            "/api/pipeline/submit",
            json={"input_path": str(tmp_path), "operations": ["metadata"]},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert "Metadata runner" in body["message"]


def test_pipeline_phase_skip_calls_db_with_defaults(monkeypatch, tmp_path):
    monkeypatch.setattr(ui_security, "_check_rate_limit", lambda endpoint: None)
    captured = {}

    def fake_set_folder_phase_status(**kwargs):
        captured.update(kwargs)
        return 5

    monkeypatch.setattr(db, "set_folder_phase_status", fake_set_folder_phase_status)

    with _build_client() as client:
        response = client.post(
            "/api/pipeline/phase/skip",
            json={"input_path": str(tmp_path), "phase_code": "keywords"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "Phase 'keywords' marked as skipped",
        "data": {"updated_images": 5, "phase_code": "keywords"},
    }
    assert captured == {
        "folder_path": str(tmp_path),
        "phase_code": "keywords",
        "status": "skipped",
        "reason": "manual_skip",
        "actor": "api_user",
    }


def test_pipeline_phase_skip_returns_400_for_missing_path(monkeypatch):
    monkeypatch.setattr(ui_security, "_check_rate_limit", lambda endpoint: None)

    with _build_client() as client:
        response = client.post(
            "/api/pipeline/phase/skip",
            json={"input_path": "D:/does/not/exist", "phase_code": "scoring"},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Path not found: D:/does/not/exist"


def test_pipeline_phase_retry_scoring_starts_runner(monkeypatch, tmp_path):
    monkeypatch.setattr(ui_security, "_check_rate_limit", lambda endpoint: None)
    runner = _BatchRunnerStub()
    monkeypatch.setattr(api, "_scoring_runner", runner)

    status_updates = []
    monkeypatch.setattr(
        db,
        "set_folder_phase_status",
        lambda **kwargs: status_updates.append(kwargs) or 8,
    )
    monkeypatch.setattr(db, "create_job", lambda input_path, phase_code=None: 901)
    monkeypatch.setattr(db, "create_job_phases", lambda job_id, phase_codes, first_phase_state=None: [])

    with _build_client() as client:
        response = client.post(
            "/api/pipeline/phase/retry",
            json={"input_path": str(tmp_path), "phase_code": "scoring"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "Retry scoring: Started",
        "data": {"updated_images": 8, "phase_code": "scoring", "job_id": 901},
    }
    assert status_updates == [
        {"folder_path": str(tmp_path), "phase_code": "scoring", "status": "running"}
    ]
    assert runner.calls == [((str(tmp_path), 901, True), {})]


def test_pipeline_phase_retry_keywords_starts_runner(monkeypatch, tmp_path):
    monkeypatch.setattr(ui_security, "_check_rate_limit", lambda endpoint: None)
    runner = _BatchRunnerStub()
    monkeypatch.setattr(api, "_tagging_runner", runner)
    monkeypatch.setattr(db, "set_folder_phase_status", lambda **kwargs: 4)
    monkeypatch.setattr(db, "create_job", lambda input_path, phase_code=None: 902)
    monkeypatch.setattr(db, "create_job_phases", lambda job_id, phase_codes, first_phase_state=None: [])

    with _build_client() as client:
        response = client.post(
            "/api/pipeline/phase/retry",
            json={"input_path": str(tmp_path), "phase_code": "keywords"},
        )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert runner.calls == [
        ((str(tmp_path),), {"job_id": 902, "overwrite": False, "generate_captions": False})
    ]


def test_pipeline_phase_retry_culling_starts_runner(monkeypatch, tmp_path):
    monkeypatch.setattr(ui_security, "_check_rate_limit", lambda endpoint: None)
    runner = _BatchRunnerStub()
    monkeypatch.setattr(api, "_clustering_runner", runner)
    monkeypatch.setattr(db, "set_folder_phase_status", lambda **kwargs: 6)
    monkeypatch.setattr(db, "create_job", lambda input_path, phase_code=None: 903)
    monkeypatch.setattr(db, "create_job_phases", lambda job_id, phase_codes, first_phase_state=None: [])

    with _build_client() as client:
        response = client.post(
            "/api/pipeline/phase/retry",
            json={"input_path": str(tmp_path), "phase_code": "culling"},
        )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert runner.calls == [
        ((str(tmp_path),), {"job_id": 903, "force_rescan": True})
    ]


def test_pipeline_phase_retry_returns_503_when_runner_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(ui_security, "_check_rate_limit", lambda endpoint: None)
    monkeypatch.setattr(api, "_tagging_runner", None)
    monkeypatch.setattr(db, "set_folder_phase_status", lambda **kwargs: 1)

    with _build_client() as client:
        response = client.post(
            "/api/pipeline/phase/retry",
            json={"input_path": str(tmp_path), "phase_code": "keywords"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Tagging runner not available"


def test_pipeline_phase_retry_rejects_unsupported_phase(monkeypatch, tmp_path):
    monkeypatch.setattr(ui_security, "_check_rate_limit", lambda endpoint: None)
    monkeypatch.setattr(db, "set_folder_phase_status", lambda **kwargs: 3)

    with _build_client() as client:
        response = client.post(
            "/api/pipeline/phase/retry",
            json={"input_path": str(tmp_path), "phase_code": "metadata"},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported phase_code: metadata"


def test_pipeline_phase_backfill_returns_count(monkeypatch, tmp_path):
    monkeypatch.setattr(ui_security, "_check_rate_limit", lambda endpoint: None)
    monkeypatch.setattr(db, "backfill_index_meta_for_folder", lambda folder_path: 9)

    with _build_client() as client:
        response = client.post(
            "/api/pipeline/phase/backfill-index-meta",
            json={"input_path": str(tmp_path)},
        )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "Backfilled Index/Meta for 9 image(s)",
        "data": {"updated_images": 9},
    }


def test_pipeline_phase_backfill_returns_400_for_missing_path(monkeypatch):
    monkeypatch.setattr(ui_security, "_check_rate_limit", lambda endpoint: None)

    with _build_client() as client:
        response = client.post(
            "/api/pipeline/phase/backfill-index-meta",
            json={"input_path": "D:/missing/folder"},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Path not found: D:/missing/folder"


def test_scoring_start_returns_500_when_enqueue_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(ui_security, "_check_rate_limit", lambda endpoint: None)
    monkeypatch.setattr(api, "_scoring_runner", _RunnerStub())
    monkeypatch.setattr(
        api,
        "resolve_selectors",
        lambda **kwargs: {"resolved_image_ids": [11], "missing_image_paths": [], "missing_folder_paths": []},
    )
    monkeypatch.setattr(db, "enqueue_job", lambda *args, **kwargs: (None, 0))

    with _build_client() as client:
        response = client.post("/api/scoring/start", json={"input_path": str(tmp_path)})

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to enqueue scoring job"


def test_tagging_start_returns_500_when_enqueue_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(ui_security, "_check_rate_limit", lambda endpoint: None)
    monkeypatch.setattr(api, "_tagging_runner", _RunnerStub())
    monkeypatch.setattr(
        api,
        "resolve_selectors",
        lambda **kwargs: {"resolved_image_ids": [11], "missing_image_paths": [], "missing_folder_paths": []},
    )
    monkeypatch.setattr(db, "enqueue_job", lambda *args, **kwargs: (None, 0))

    with _build_client() as client:
        response = client.post("/api/tagging/start", json={"input_path": str(tmp_path)})

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to enqueue tagging job"


def test_clustering_start_returns_500_when_enqueue_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(ui_security, "_check_rate_limit", lambda endpoint: None)
    monkeypatch.setattr(api, "_clustering_runner", _RunnerStub())
    monkeypatch.setattr(
        api,
        "resolve_selectors",
        lambda **kwargs: {"resolved_image_ids": [11], "missing_image_paths": [], "missing_folder_paths": []},
    )
    monkeypatch.setattr(db, "enqueue_job", lambda *args, **kwargs: (None, 0))

    with _build_client() as client:
        response = client.post("/api/clustering/start", json={"input_path": str(tmp_path)})

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to enqueue clustering job"


def test_clustering_start_creates_job_phases_with_queued_first_phase(monkeypatch, tmp_path):
    monkeypatch.setattr(ui_security, "_check_rate_limit", lambda endpoint: None)
    monkeypatch.setattr(api, "_clustering_runner", _RunnerStub())
    monkeypatch.setattr(
        api,
        "resolve_selectors",
        lambda **kwargs: {"resolved_image_ids": None, "missing_image_paths": [], "missing_folder_paths": []},
    )
    monkeypatch.setattr(db, "enqueue_job", lambda *a, **kw: (42, 1))
    captured = {}

    def fake_create_job_phases(job_id, phase_codes, first_phase_state=None):
        captured["job_id"] = job_id
        captured["phase_codes"] = list(phase_codes)
        captured["first_phase_state"] = first_phase_state
        return []

    monkeypatch.setattr(db, "create_job_phases", fake_create_job_phases)

    with _build_client() as client:
        response = client.post("/api/clustering/start", json={"input_path": str(tmp_path)})

    assert response.status_code == 200
    assert captured.get("job_id") == 42
    assert captured.get("phase_codes") == ["indexing", "metadata", "scoring", "culling"]
    assert captured.get("first_phase_state") == "queued"


def test_pipeline_submit_returns_500_when_enqueue_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(ui_security, "_check_rate_limit", lambda endpoint: None)
    monkeypatch.setattr(api, "_clustering_runner", _RunnerStub())
    monkeypatch.setattr(
        api,
        "validate_and_preview",
        lambda request: {"preview_count": 2, "resolved_image_ids": [11, 12], "missing_paths": [], "warnings": []},
    )
    monkeypatch.setattr(db, "enqueue_job", lambda *args, **kwargs: (None, 0))

    body = {
        "input_path": str(tmp_path),
        "operations": ["cluster"],
        "clustering_threshold": 0.2,
    }
    with _build_client() as client:
        response = client.post("/api/pipeline/submit", json=body)

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert "cluster" in detail and "enqueue" in detail.lower()


def test_pipeline_submit_requires_input_path(monkeypatch):
    monkeypatch.setattr(ui_security, "_check_rate_limit", lambda endpoint: None)

    with _build_client() as client:
        response = client.post("/api/pipeline/submit", json={"operations": ["score"]})

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert "workspace_target" in body["message"] and "selector" in body["message"]


def test_outliers_endpoint_returns_detector_payload(monkeypatch):
    expected = {
        "outliers": [{
            "image_id": 5, 
            "file_path": "/photos/2024/img5.jpg",
            "outlier_score": 0.85,
            "z_score": -2.4,
            "nearest_neighbors": [
                {"image_id": 6, "file_path": "/photos/2024/img6.jpg", "similarity": 0.95}
            ]
        }],
        "stats": {
            "total_with_embeddings": 100,
            "folder_mean": 0.9,
            "folder_std": 0.05,
            "z_threshold": 1.8,
            "k_neighbors": 7,
            "outliers_found": 1
        },
        "skipped": [],
    }

    def fake_find_outliers(folder_path, z_threshold=None, k=None, limit=None):
        assert folder_path == "/photos/2024"
        assert z_threshold == 1.8
        assert k == 7
        assert limit == 33
        return expected

    from modules import similar_search
    monkeypatch.setattr(similar_search, "find_outliers", fake_find_outliers)

    with _build_client() as client:
        response = client.get(
            "/api/outliers",
            params={"folder_path": "/photos/2024", "z_threshold": 1.8, "k": 7, "limit": 33},
        )

    assert response.status_code == 200
    assert response.json() == expected


def test_outliers_endpoint_propagates_domain_error(monkeypatch):
    from modules import similar_search
    monkeypatch.setattr(similar_search, "find_outliers", lambda **kwargs: {"error": "folder_path is required"})

    with _build_client() as client:
        response = client.get("/api/outliers", params={"folder_path": "/bad/path"})

    assert response.status_code == 400
    assert response.json()["detail"] == "folder_path is required"


def test_outliers_endpoint_returns_500_on_unexpected_exception(monkeypatch):
    from modules import similar_search

    def _raise_unexpected(**kwargs):
        raise RuntimeError("unexpected failure")

    monkeypatch.setattr(similar_search, "find_outliers", _raise_unexpected)

    with _build_client() as client:
        response = client.get("/api/outliers", params={"folder_path": "/bad/path"})

    assert response.status_code == 500
    assert response.json()["detail"] == "unexpected failure"


def test_similarity_similar_alias_matches_existing_contract(monkeypatch):
    from modules import similar_search

    monkeypatch.setattr(db, "get_db", lambda: _FakeConn(found=True))

    expected_results = [
        {"image_id": 2, "file_path": "/photos/2.jpg", "similarity": 0.93},
        {"image_id": 3, "file_path": "/photos/3.jpg", "similarity": 0.90},
    ]

    def fake_search_similar_images(
        example_image_id, limit, folder_path, min_similarity, embedding_space=None
    ):
        assert example_image_id == 1
        assert limit == 5
        assert folder_path == "/photos"
        assert min_similarity == 0.9
        assert embedding_space is None
        return expected_results

    monkeypatch.setattr(similar_search, "search_similar_images", fake_search_similar_images)

    with _build_client() as client:
        response = client.get(
            "/api/similarity/similar",
            params={"image_id": 1, "limit": 5, "folder_path": "/photos", "min_similarity": 0.9},
        )

    assert response.status_code == 200
    assert response.json() == {
        "query_image_id": 1,
        "results": expected_results,
        "count": 2,
    }


def test_similarity_duplicates_alias_returns_count(monkeypatch):
    from modules import similar_search

    expected_duplicates = [
        {"a_image_id": 1, "b_image_id": 2, "similarity": 0.99},
        {"a_image_id": 3, "b_image_id": 4, "similarity": 0.98},
    ]

    def fake_find_near_duplicates(threshold=None, folder_path=None, limit=1000):
        assert threshold == 0.97
        assert folder_path == "/photos"
        assert limit == 10
        return expected_duplicates

    monkeypatch.setattr(similar_search, "find_near_duplicates", fake_find_near_duplicates)

    with _build_client() as client:
        response = client.get(
            "/api/similarity/duplicates",
            params={"threshold": 0.97, "folder_path": "/photos", "limit": 10},
        )

    assert response.status_code == 200
    assert response.json() == {
        "duplicates": expected_duplicates,
        "count": 2,
    }


def test_similarity_outliers_alias_returns_detector_payload(monkeypatch):
    expected = {
        "outliers": [{
            "image_id": 12,
            "file_path": "/photos/img12.jpg",
            "outlier_score": 0.72,
            "z_score": -2.0,
            "nearest_neighbors": [
                {"image_id": 11, "file_path": "/photos/img11.jpg", "similarity": 0.94}
            ]
        }],
        "stats": {
            "total_with_embeddings": 20,
            "folder_mean": 0.91,
            "folder_std": 0.04,
            "z_threshold": 1.7,
            "k_neighbors": 4,
            "outliers_found": 1,
        },
        "skipped": [],
    }

    from modules import similar_search
    monkeypatch.setattr(similar_search, "find_outliers", lambda **kwargs: expected)

    with _build_client() as client:
        response = client.get(
            "/api/similarity/outliers",
            params={"folder_path": "/photos", "z_threshold": 1.7, "k": 4, "limit": 8},
        )

    assert response.status_code == 200
    assert response.json() == expected


class _FakeCursor:
    def __init__(self, found=True):
        self._found = found

    def execute(self, *_args, **_kwargs):
        return None

    def fetchone(self):
        if self._found:
            return (1,)
        return None


class _FakeConn:
    def __init__(self, found=True):
        self._found = found

    def cursor(self):
        return _FakeCursor(found=self._found)

    def close(self):
        return None


def test_ipc_bridge_routes_pipeline_submit(monkeypatch, tmp_path):
    monkeypatch.setattr(ui_security, "_check_rate_limit", lambda endpoint: None)
    monkeypatch.setattr(api, "_scoring_runner", _RunnerStub())
    monkeypatch.setattr(
        api,
        "validate_and_preview",
        lambda request: {"preview_count": 2, "resolved_image_ids": [11, 12], "missing_paths": [], "warnings": []},
    )

    monkeypatch.setattr(db, "enqueue_job", lambda *a, **kw: (900, 4))
    monkeypatch.setattr(db, "create_job_phases", lambda job_id, phase_codes, first_phase_state=None: [])

    with _build_client() as client:
        response = client.post(
            "/api/ipc/bridge",
            json={
                "channel": "pipeline:submit",
                "payload": {
                    "workspace_target": str(tmp_path),
                    "operations": ["score"],
                    "skip_existing": True,
                },
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["channel"] == "pipeline:submit"
    assert payload["ok"] is True
    assert payload["data"]["success"] is True
    assert payload["data"]["data"]["job_id"] == 900


def test_ipc_bridge_routes_tasks_active(monkeypatch):
    monkeypatch.setattr(api._job_dispatcher, "get_state", lambda: {
        "queue": [],
        "queue_size": 0,
        "active_runner": None,
        "is_dispatcher_running": True,
    })
    monkeypatch.setattr(db, "get_queued_jobs", lambda limit=200: [])
    monkeypatch.setattr(db, "get_jobs", lambda *a, **k: [])
    monkeypatch.setattr(db, "get_job_by_id", lambda job_id: None)

    with _build_client() as client:
        response = client.post(
            "/api/ipc/bridge",
            json={"channel": "tasks:active", "payload": {"limit": 11}},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["channel"] == "tasks:active"
    assert payload["ok"] is True
    assert "dispatcher" in payload["data"]


def test_ipc_bridge_rejects_unknown_channel():
    with _build_client() as client:
        response = client.post(
            "/api/ipc/bridge",
            json={"channel": "unknown:channel", "payload": {}},
        )

    assert response.status_code == 400
    detail = response.json()["detail"]
    text = detail["message"] if isinstance(detail, dict) else str(detail)
    assert "Unsupported IPC channel" in text


def test_ipc_bridge_folders_phase_status_requires_path():
    with _build_client() as client:
        response = client.post(
            "/api/ipc/bridge",
            json={"channel": "folders:phase-status", "payload": {}},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "payload.path is required for folders:phase-status"
