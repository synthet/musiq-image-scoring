"""
Tests for GET /api/embedding_map endpoint.

All tests are pure-unit: they mock db.get_embeddings_with_metadata and the
projection functions so no GPU, Firebird, or umap-learn dependency is required.
"""

import numpy as np
import pytest

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from modules import api
except ImportError as e:
    pytest.skip(f"API deps not available: {e}", allow_module_level=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_client():
    app = FastAPI()
    app.include_router(api.create_api_router())
    return TestClient(app)


def _fake_rows(n, dim=8):
    """Return n fake embedding rows with random float32 vectors of dimension `dim`."""
    rows = []
    rng = np.random.default_rng(0)
    for i in range(n):
        vec = rng.random(dim).astype(np.float32)
        rows.append({
            "image_id": i + 1,
            "file_path": f"/photos/img{i+1:04d}.jpg",
            "embedding": vec.tobytes(),
            "thumbnail_path": f"/thumbs/img{i+1:04d}.jpg",
            "label": None,
            "rating": None,
            "score_general": round(float(rng.random()), 3),
            "score_technical": round(float(rng.random()), 3),
            "score_aesthetic": round(float(rng.random()), 3),
            "score_spaq": round(float(rng.random()), 3),
            "score_ava": round(float(rng.random()), 3),
            "score_koniq": round(float(rng.random()), 3),
            "score_paq2piq": round(float(rng.random()), 3),
            "score_liqe": round(float(rng.random()), 3),
        })
    return rows


def _fake_coords(n):
    """Return deterministic 2D coords for n points."""
    rng = np.random.default_rng(1)
    return rng.random((n, 2)).astype(np.float64)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_embedding_map_too_few_points(monkeypatch):
    """Fewer than 3 images → success=True but points=[] and error key present."""
    import modules.db as db_mod
    import modules.projections as proj_mod

    monkeypatch.setattr(proj_mod, "_load_cache", lambda key: None)
    monkeypatch.setattr(proj_mod, "_save_cache", lambda key, data: None)
    monkeypatch.setattr(db_mod, "get_embeddings_with_metadata", lambda **kw: _fake_rows(1))

    with _build_client() as client:
        resp = client.get("/api/embedding_map")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["points"] == []
    assert data["meta"]["error"] == "too_few_points"


def test_embedding_map_returns_points(monkeypatch):
    """With enough rows the endpoint returns a point per image."""
    import modules.db as db_mod
    import modules.projections as proj_mod

    n = 5
    rows = _fake_rows(n)
    monkeypatch.setattr(db_mod, "get_embeddings_with_metadata", lambda **kw: rows)

    fixed_coords = _fake_coords(n)

    def _fake_project_umap(vecs, n_neighbors, min_dist):
        return fixed_coords

    monkeypatch.setattr(proj_mod, "_project_umap", _fake_project_umap)
    # Ensure cache is bypassed
    monkeypatch.setattr(proj_mod, "_load_cache", lambda key: None)
    monkeypatch.setattr(proj_mod, "_save_cache", lambda key, data: None)

    with _build_client() as client:
        resp = client.get("/api/embedding_map?method=umap")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    points = body["data"]["points"]
    assert len(points) == n
    # All required fields present
    for pt in points:
        for field in (
            "image_id", "x", "y", "file_path", "thumbnail_path",
            "label", "rating", "score_general", "score_technical", "score_aesthetic",
            "score_spaq", "score_ava", "score_koniq", "score_paq2piq", "score_liqe",
        ):
            assert field in pt, f"Missing field: {field}"
    # x/y are in [0, 1]
    for pt in points:
        assert 0.0 <= pt["x"] <= 1.0
        assert 0.0 <= pt["y"] <= 1.0
    # meta fields present
    meta = body["data"]["meta"]
    assert meta["count"] == n
    assert meta["method"] == "umap"
    assert "computed_at" in meta
    assert "cache_key" in meta
    # UMAP requires n_neighbors < n_samples; default 30 clamps to n-1 here.
    assert meta["n_neighbors_effective"] == n - 1


def test_embedding_map_clamps_umap_n_neighbors(monkeypatch):
    """Default n_neighbors=30 must clamp below n_samples so UMAP does not fail."""
    import modules.db as db_mod
    import modules.projections as proj_mod

    n = 8
    rows = _fake_rows(n)
    monkeypatch.setattr(db_mod, "get_embeddings_with_metadata", lambda **kw: rows)

    captured = {}

    def _capture_umap(vecs, n_neighbors, min_dist):
        captured["n_neighbors"] = n_neighbors
        return _fake_coords(len(vecs))

    monkeypatch.setattr(proj_mod, "_project_umap", _capture_umap)
    monkeypatch.setattr(proj_mod, "_load_cache", lambda key: None)
    monkeypatch.setattr(proj_mod, "_save_cache", lambda key, data: None)

    with _build_client() as client:
        resp = client.get("/api/embedding_map?method=umap&n_neighbors=30")

    assert resp.status_code == 200
    assert captured["n_neighbors"] == n - 1
    assert resp.json()["data"]["meta"]["n_neighbors_effective"] == n - 1


def test_embedding_map_invalid_method():
    """Unsupported method value → 422 Unprocessable Entity."""
    with _build_client() as client:
        resp = client.get("/api/embedding_map?method=foo")
    assert resp.status_code == 422


def test_embedding_map_tsne_fallback(monkeypatch):
    """When umap raises ImportError, t-SNE is used and meta.method == 'tsne'."""
    import modules.db as db_mod
    import modules.projections as proj_mod

    n = 5
    rows = _fake_rows(n)
    monkeypatch.setattr(db_mod, "get_embeddings_with_metadata", lambda **kw: rows)

    def _raise_import(vecs, n_neighbors, min_dist):
        raise ImportError("umap-learn not installed")

    fixed_coords = _fake_coords(n)

    def _fake_project_tsne(vecs, n_neighbors):
        return fixed_coords

    monkeypatch.setattr(proj_mod, "_project_umap", _raise_import)
    monkeypatch.setattr(proj_mod, "_project_tsne", _fake_project_tsne)
    monkeypatch.setattr(proj_mod, "_load_cache", lambda key: None)
    monkeypatch.setattr(proj_mod, "_save_cache", lambda key, data: None)

    with _build_client() as client:
        resp = client.get("/api/embedding_map?method=umap")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["meta"]["method"] == "tsne"
    assert len(body["data"]["points"]) == n


def test_embedding_map_cache_hit(monkeypatch):
    """When cache returns data, db and projection are not called."""
    import modules.db as db_mod
    import modules.projections as proj_mod

    cached_data = {
        "points": [{"image_id": 1, "x": 0.5, "y": 0.5, "file_path": "/a.jpg",
                    "thumbnail_path": None, "label": None, "rating": None,
                    "score_general": 0.9, "score_technical": 0.5, "score_aesthetic": 0.6,
                    "score_spaq": None, "score_ava": None, "score_koniq": None,
                    "score_paq2piq": None, "score_liqe": None}],
        "meta": {"count": 1, "method": "umap", "computed_at": "2026-01-01T00:00:00+00:00",
                 "cache_key": "abc123"},
    }

    db_called = {"flag": False}

    def _fail_db(**kw):
        db_called["flag"] = True
        return []

    monkeypatch.setattr(db_mod, "get_embeddings_with_metadata", _fail_db)
    monkeypatch.setattr(proj_mod, "_load_cache", lambda key: cached_data)

    with _build_client() as client:
        resp = client.get("/api/embedding_map")

    assert resp.status_code == 200
    # DB should NOT have been called — cache short-circuited
    assert not db_called["flag"]
    assert resp.json()["data"] == cached_data


def test_make_cache_key_includes_sample_cap_and_method_specific_params():
    """Cache keys vary by max_points and ignore min_dist for non-UMAP methods."""
    import modules.projections as proj_mod

    key_umap_small = proj_mod._make_cache_key(
        folder_path="/photos",
        method="umap",
        max_points=100,
        n_neighbors=30,
        min_dist=0.1,
    )
    key_umap_large = proj_mod._make_cache_key(
        folder_path="/photos",
        method="umap",
        max_points=200,
        n_neighbors=30,
        min_dist=0.1,
    )
    assert key_umap_small != key_umap_large


def test_make_cache_key_separates_embedding_space_and_pca_dim():
    """Different embedding_space or pca_dim must produce distinct cache keys."""
    import modules.projections as proj_mod

    base = dict(
        folder_path="/photos", method="umap", max_points=100,
        n_neighbors=30, min_dist=0.1,
    )
    key_default = proj_mod._make_cache_key(**base)
    key_clip = proj_mod._make_cache_key(**base, embedding_space="clip_vit_b32_image")
    key_default_pca = proj_mod._make_cache_key(**base, pca_dim=50)

    # All three must be distinct.
    assert key_default != key_clip
    assert key_default != key_default_pca
    assert key_clip != key_default_pca

    # Default value (pca_dim=0) collides with the un-passed default.
    key_pca_zero = proj_mod._make_cache_key(**base, pca_dim=0)
    assert key_pca_zero == key_default

    key_umap_lo = proj_mod._make_cache_key(
        folder_path="/photos",
        method="umap",
        max_points=100,
        n_neighbors=30,
        min_dist=0.1,
    )
    key_umap_hi = proj_mod._make_cache_key(
        folder_path="/photos",
        method="umap",
        max_points=100,
        n_neighbors=30,
        min_dist=0.8,
    )
    assert key_umap_lo != key_umap_hi

    key_tsne_a = proj_mod._make_cache_key(
        folder_path="/photos",
        method="tsne",
        max_points=100,
        n_neighbors=30,
        min_dist=0.1,
    )
    key_tsne_b = proj_mod._make_cache_key(
        folder_path="/photos",
        method="tsne",
        max_points=100,
        n_neighbors=30,
        min_dist=0.8,
    )
    assert key_tsne_a == key_tsne_b


def test_embedding_map_unknown_space_returns_error_meta(monkeypatch):
    """Passing an unknown space_code returns success=True with meta.error."""
    import modules.projections as proj_mod

    # Cache must be bypassed so the unknown-space check actually runs.
    monkeypatch.setattr(proj_mod, "_load_cache", lambda key: None)
    monkeypatch.setattr(proj_mod, "_save_cache", lambda key, data: None)

    with _build_client() as client:
        resp = client.get("/api/embedding_map?space_code=does_not_exist")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["points"] == []
    assert body["data"]["meta"]["error"] == "unknown_embedding_space"
    assert body["data"]["meta"]["embedding_space"] == "does_not_exist"


def test_embedding_map_routes_through_projections_db_for_non_default_space(monkeypatch):
    """A non-default space_code must go through projections_db, not db."""
    import modules.db as db_mod
    import modules.projections as proj_mod
    import modules.projections_db as pdb_mod

    n = 5
    rows = _fake_rows(n, dim=8)

    # Default-space reader must NOT be hit.
    db_called = {"flag": False}

    def _fail_db(**kw):
        db_called["flag"] = True
        return []

    captured = {}

    def _fake_pdb(space_code, folder_path=None, limit=None):
        captured["space_code"] = space_code
        captured["limit"] = limit
        return rows

    monkeypatch.setattr(db_mod, "get_embeddings_with_metadata", _fail_db)
    monkeypatch.setattr(
        pdb_mod, "get_embeddings_with_metadata_for_space", _fake_pdb
    )
    monkeypatch.setattr(proj_mod, "_project_umap", lambda v, n_n, m_d: _fake_coords(len(v)))
    monkeypatch.setattr(proj_mod, "_load_cache", lambda key: None)
    monkeypatch.setattr(proj_mod, "_save_cache", lambda key, data: None)

    with _build_client() as client:
        resp = client.get("/api/embedding_map?space_code=clip_vit_b32_image")

    assert resp.status_code == 200
    assert not db_called["flag"], "default-space reader was called for non-default space"
    assert captured["space_code"] == "clip_vit_b32_image"
    body = resp.json()
    assert body["data"]["meta"]["embedding_space"] == "clip_vit_b32_image"


def test_embedding_map_pca_dim_off_when_zero(monkeypatch):
    """pca_dim=0 must skip the PCA pre-step (PCA function not called)."""
    import modules.db as db_mod
    import modules.projections as proj_mod

    n = 5
    rows = _fake_rows(n, dim=64)
    monkeypatch.setattr(db_mod, "get_embeddings_with_metadata", lambda **kw: rows)

    pca_called = {"flag": False}

    def _spy_pca(v, n_components):
        pca_called["flag"] = True
        return v

    monkeypatch.setattr(proj_mod, "_project_pca", _spy_pca)
    monkeypatch.setattr(proj_mod, "_project_umap", lambda v, n_n, m_d: _fake_coords(len(v)))
    monkeypatch.setattr(proj_mod, "_load_cache", lambda key: None)
    monkeypatch.setattr(proj_mod, "_save_cache", lambda key, data: None)

    with _build_client() as client:
        resp = client.get("/api/embedding_map?pca_dim=0")

    assert resp.status_code == 200
    assert not pca_called["flag"]
    assert resp.json()["data"]["meta"]["pca_dim"] == 0


def test_embedding_map_pca_dim_explicit_runs(monkeypatch):
    """An explicit non-zero pca_dim runs PCA with that target dim."""
    import modules.db as db_mod
    import modules.projections as proj_mod

    n = 8
    src_dim = 64
    rows = _fake_rows(n, dim=src_dim)
    monkeypatch.setattr(db_mod, "get_embeddings_with_metadata", lambda **kw: rows)

    pca_calls = []

    def _spy_pca(v, n_components):
        pca_calls.append((v.shape, n_components))
        # Return reduced shape so downstream UMAP receives the lower-dim matrix.
        import numpy as _np
        return _np.zeros((v.shape[0], n_components), dtype=_np.float32)

    monkeypatch.setattr(proj_mod, "_project_pca", _spy_pca)
    monkeypatch.setattr(proj_mod, "_project_umap", lambda v, n_n, m_d: _fake_coords(len(v)))
    monkeypatch.setattr(proj_mod, "_load_cache", lambda key: None)
    monkeypatch.setattr(proj_mod, "_save_cache", lambda key, data: None)

    with _build_client() as client:
        resp = client.get("/api/embedding_map?pca_dim=16")

    assert resp.status_code == 200
    assert len(pca_calls) == 1
    assert pca_calls[0][1] == 16  # n_components forwarded
    assert resp.json()["data"]["meta"]["pca_dim"] == 16


def test_resolve_pca_dim_auto_thresholds():
    """Auto mode (pca_dim=None): on for source_dim>=1280, off below."""
    import modules.projections as proj_mod

    # Auto: high-dim source -> 50.
    assert proj_mod._resolve_pca_dim(None, 1280) == 50
    # Auto: low-dim source -> 0 (off).
    assert proj_mod._resolve_pca_dim(None, 512) == 0
    # Explicit 0 always off.
    assert proj_mod._resolve_pca_dim(0, 1280) == 0
    # Explicit value >= source_dim is a no-op.
    assert proj_mod._resolve_pca_dim(2048, 1280) == 0
    # Explicit value < source_dim passes through.
    assert proj_mod._resolve_pca_dim(50, 768) == 50


def test_image_similar_endpoint_404_for_missing_image(monkeypatch):
    """GET /api/images/{id}/similar must 404 when the image does not exist."""
    import modules.db as db_mod

    class _FakeCursor:
        def __init__(self):
            self._row = None

        def execute(self, sql, params):
            self._row = None  # always "not found"

        def fetchone(self):
            return self._row

    class _FakeConn:
        def cursor(self):
            return _FakeCursor()

        def close(self):
            pass

    monkeypatch.setattr(db_mod, "get_db", lambda: _FakeConn())

    with _build_client() as client:
        resp = client.get("/api/images/9999/similar")

    assert resp.status_code == 404


def test_image_similar_endpoint_returns_results(monkeypatch):
    """Happy-path: returns query_image_id + results from search_similar_images."""
    import modules.db as db_mod
    import modules.similar_search as sim_mod

    class _FakeCursor:
        def execute(self, sql, params):
            self._row = (1,)

        def fetchone(self):
            return self._row

    class _FakeConn:
        def cursor(self):
            return _FakeCursor()

        def close(self):
            pass

    captured = {}

    def _fake_search(**kw):
        captured.update(kw)
        return [{"image_id": 2, "file_path": "/p/2.jpg", "similarity": 0.95}]

    monkeypatch.setattr(db_mod, "get_db", lambda: _FakeConn())
    monkeypatch.setattr(sim_mod, "search_similar_images", _fake_search)

    with _build_client() as client:
        resp = client.get(
            "/api/images/1/similar?limit=5&embedding_space=clip_vit_b32_image"
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["query_image_id"] == 1
    assert body["count"] == 1
    assert body["embedding_space"] == "clip_vit_b32_image"
    assert captured["example_image_id"] == 1
    assert captured["limit"] == 5
    assert captured["embedding_space"] == "clip_vit_b32_image"


def test_embedding_map_cache_separated_by_sample_limit(monkeypatch):
    """Different sample_limit values should not collide in cache."""
    import modules.db as db_mod
    import modules.projections as proj_mod

    rows = _fake_rows(8)
    cache_store = {}
    project_call_count = {"count": 0}

    def _fake_db(**kw):
        limit = kw.get("limit")
        return rows[:limit]

    def _fake_project_umap(vecs, n_neighbors, min_dist):
        project_call_count["count"] += 1
        return _fake_coords(len(vecs))

    monkeypatch.setattr(db_mod, "get_embeddings_with_metadata", _fake_db)
    monkeypatch.setattr(proj_mod, "_project_umap", _fake_project_umap)
    monkeypatch.setattr(proj_mod, "_load_cache", lambda key: cache_store.get(key))
    monkeypatch.setattr(
        proj_mod, "_save_cache", lambda key, data: cache_store.setdefault(key, data)
    )

    # Prime cache for sample_limit=3
    first = proj_mod.compute_embedding_map(method="umap", sample_limit=3)
    assert len(first["points"]) == 3
    assert project_call_count["count"] == 1

    # Same sample_limit should hit cache
    again = proj_mod.compute_embedding_map(method="umap", sample_limit=3)
    assert len(again["points"]) == 3
    assert again["meta"]["cache_key"] == first["meta"]["cache_key"]
    assert project_call_count["count"] == 1

    # Different sample_limit must produce different key and recompute
    second = proj_mod.compute_embedding_map(method="umap", sample_limit=5)
    assert len(second["points"]) == 5
    assert second["meta"]["cache_key"] != first["meta"]["cache_key"]
    assert project_call_count["count"] == 2


# ---------------------------------------------------------------------------
# /api/embedding_spaces
# ---------------------------------------------------------------------------

def test_embedding_spaces_postgres_returns_registry_rows(monkeypatch):
    """On Postgres the endpoint surfaces rows from embedding_spaces."""
    import modules.db as db_mod

    monkeypatch.setattr(db_mod, "_get_db_engine", lambda: "postgres")

    fake_rows = [
        {"code": "mobilenet_v2_imagenet_gap", "dim": 1280, "description": "default", "active": 1},
        {"code": "clip_vit_b32_image", "dim": 512, "description": "clip", "active": 1},
        {"code": "bioclip_2_image", "dim": 512, "description": "bioclip", "active": 1},
        {"code": "blip_vit_b16_image", "dim": 768, "description": "blip", "active": 1},
    ]

    captured = {}

    def _fake_execute_select(sql, params=None):
        captured["sql"] = sql
        return fake_rows

    import modules.db_postgres as db_pg_mod
    monkeypatch.setattr(db_pg_mod, "execute_select", _fake_execute_select)

    with _build_client() as client:
        resp = client.get("/api/embedding_spaces")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    codes = [s["code"] for s in data["spaces"]]
    assert codes == [
        "mobilenet_v2_imagenet_gap",
        "clip_vit_b32_image",
        "bioclip_2_image",
        "blip_vit_b16_image",
    ]
    default = next(s for s in data["spaces"] if s["is_default"])
    assert default["code"] == "mobilenet_v2_imagenet_gap"
    assert default["dim"] == 1280
    assert all(s["active"] is True for s in data["spaces"])
    assert data["meta"]["engine"] == "postgres"
    assert data["meta"]["default_code"] == "mobilenet_v2_imagenet_gap"
    # Active filter is part of the SQL the endpoint issues.
    assert "active" in captured["sql"].lower()


def test_embedding_spaces_firebird_falls_back_to_static_registry(monkeypatch):
    """On Firebird the endpoint synthesises rows from SPACE_DIMS."""
    import modules.db as db_mod
    from modules.embedding_spaces import DEFAULT_EMBEDDING_SPACE_CODE, SPACE_DIMS

    monkeypatch.setattr(db_mod, "_get_db_engine", lambda: "firebird")

    with _build_client() as client:
        resp = client.get("/api/embedding_spaces")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    codes = {s["code"] for s in data["spaces"]}
    assert codes == set(SPACE_DIMS.keys())
    for s in data["spaces"]:
        assert s["dim"] == SPACE_DIMS[s["code"]]
        assert s["description"] is None
        assert s["active"] is True
        assert s["is_default"] == (s["code"] == DEFAULT_EMBEDDING_SPACE_CODE)
    assert data["meta"]["engine"] == "firebird"
    assert data["meta"]["default_code"] == DEFAULT_EMBEDDING_SPACE_CODE


def test_embedding_spaces_postgres_empty_registry(monkeypatch):
    """An empty Postgres registry still returns a stable shape."""
    import modules.db as db_mod
    import modules.db_postgres as db_pg_mod

    monkeypatch.setattr(db_mod, "_get_db_engine", lambda: "postgres")
    monkeypatch.setattr(db_pg_mod, "execute_select", lambda sql, params=None: [])

    with _build_client() as client:
        resp = client.get("/api/embedding_spaces")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["spaces"] == []
    assert data["meta"]["engine"] == "postgres"
    assert data["meta"]["default_code"] == "mobilenet_v2_imagenet_gap"
