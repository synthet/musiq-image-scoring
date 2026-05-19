import pytest
from unittest.mock import MagicMock

def test_get_batch_image_embedding_presence_empty():
    from modules.db_legacy import get_batch_image_embedding_presence
    assert get_batch_image_embedding_presence([]) == {}

def test_get_batch_image_embedding_presence_postgres(monkeypatch):
    import modules.db_legacy as dbl
    from modules import db_postgres

    # Mock _get_db_engine to return "postgres"
    monkeypatch.setattr(dbl, "_get_db_engine", lambda: "postgres")
    
    # Mock _pg_embedding_table_for_dim
    monkeypatch.setattr(dbl, "_pg_embedding_table_for_dim", lambda dim: f"image_embeddings_mock_{dim}")

    # Mock db_postgres.execute_select
    select_calls = []
    def mock_select(query, params=None):
        select_calls.append((query, params))
        if "embedding_spaces" in query:
            return [
                {"id": 1, "code": "mobilenet_v2_imagenet_gap", "dim": 1280},
                {"id": 2, "code": "clip_vit_b32_image", "dim": 512}
            ]
        elif "image_embeddings_mock_1280" in query:
            return [{"image_id": 100, "embedding_space_id": 1}]
        elif "image_embeddings_mock_512" in query:
            return [{"image_id": 100, "embedding_space_id": 2}, {"image_id": 101, "embedding_space_id": 2}]
        elif "images" in query:
            return [{"id": 101}] # legacy check returns iid 101 as mobilenet
        return []

    monkeypatch.setattr(db_postgres, "execute_select", mock_select)

    res = dbl.get_batch_image_embedding_presence([100, 101, 102])
    
    assert res[100]["mobilenet_v2_imagenet_gap"] is True
    assert res[100]["clip_vit_b32_image"] is True
    assert res[101]["mobilenet_v2_imagenet_gap"] is True # due to legacy images fallback
    assert res[101]["clip_vit_b32_image"] is True
    assert res[102]["mobilenet_v2_imagenet_gap"] is False
    assert res[102]["clip_vit_b32_image"] is False

def test_get_batch_image_embedding_presence_firebird(monkeypatch):
    import modules.db_legacy as dbl

    # Mock _get_db_engine to return "firebird"
    monkeypatch.setattr(dbl, "_get_db_engine", lambda: "firebird")
    
    # Mock connector
    mock_conn = MagicMock()
    mock_conn.query.return_value = [{"id": 100}]
    monkeypatch.setattr(dbl, "get_connector", lambda: mock_conn)

    res = dbl.get_batch_image_embedding_presence([100, 101])
    
    assert res[100]["mobilenet_v2_imagenet_gap"] is True
    assert res[101]["mobilenet_v2_imagenet_gap"] is False

def test_sort_by_embeddings(monkeypatch):
    import modules.db_legacy as dbl

    # Test sort validation
    sort_by, order = dbl._validate_sort("embeddings", "asc")
    assert sort_by == "embeddings"
    assert order == "ASC"

    # Test build query components for Postgres
    monkeypatch.setattr(dbl, "_get_db_engine", lambda: "postgres")
    res_pg = dbl._build_image_query_components(sort_by="embeddings", order="desc")
    assert "image_embeddings" in res_pg["order_by"]
    assert "image_embeddings_512" in res_pg["order_by"]
    assert "image_embeddings_768" in res_pg["order_by"]
    assert "DESC" in res_pg["order_by"]

    # Test build query components for Firebird
    monkeypatch.setattr(dbl, "_get_db_engine", lambda: "firebird")
    res_fb = dbl._build_image_query_components(sort_by="embeddings", order="asc")
    assert "images.image_embedding IS NOT NULL" in res_fb["order_by"]
    assert "ASC" in res_fb["order_by"]

