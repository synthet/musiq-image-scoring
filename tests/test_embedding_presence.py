from unittest.mock import MagicMock

def test_get_batch_image_embedding_presence_empty():
    from modules.db_legacy import get_batch_image_embedding_presence
    assert get_batch_image_embedding_presence([]) == {}

def test_get_batch_image_embedding_presence_postgres(monkeypatch):
    import modules.db_legacy as dbl
    from modules import db_postgres

    # Mock _get_db_engine to return "postgres"
    monkeypatch.setattr(dbl, "_get_db_engine", lambda: "postgres")
    monkeypatch.setattr(dbl, "_postgres_images_has_image_embedding_column", lambda: True)
    monkeypatch.setattr(dbl, "_write_legacy_image_embedding_column", lambda: True)

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

def test_postgres_has_default_embedding_sql_table_only(monkeypatch):
    import modules.db_legacy as dbl

    monkeypatch.setattr(dbl, "_get_db_engine", lambda: "postgres")
    monkeypatch.setattr(dbl, "_postgres_images_has_image_embedding_column", lambda: True)
    monkeypatch.setattr(dbl, "_write_legacy_image_embedding_column", lambda: False)
    sql = dbl._postgres_has_default_embedding_sql("i")
    assert "image_embeddings" in sql
    assert "image_embedding IS NOT NULL" not in sql


def test_update_image_embedding_skips_legacy_column_when_disabled(monkeypatch):
    import modules.db_legacy as dbl
    from modules import db_postgres

    monkeypatch.setattr(dbl, "_get_db_engine", lambda: "postgres")
    monkeypatch.setattr(dbl, "_postgres_images_has_image_embedding_column", lambda: True)
    monkeypatch.setattr(dbl, "_write_legacy_image_embedding_column", lambda: False)

    class _Conn:
        type = "postgres"

    monkeypatch.setattr(dbl, "get_connector", lambda: _Conn())
    monkeypatch.setattr(dbl, "_embedding_bytes_to_pg", lambda b: b"vec")
    monkeypatch.setattr(
        "modules.embedding_spaces.get_default_embedding_space_id",
        lambda: 1,
    )

    writes = []

    def _capture_write(sql, params=None):
        writes.append(sql.strip().upper())

    monkeypatch.setattr(db_postgres, "execute_write", _capture_write)

    dbl.update_image_embedding(42, b"\x00" * 5120)

    assert not any("UPDATE IMAGES SET IMAGE_EMBEDDING" in w for w in writes)
    assert any("INSERT INTO IMAGE_EMBEDDINGS" in w for w in writes)


def test_get_batch_presence_postgres_skips_legacy_column_when_disabled(monkeypatch):
    import modules.db_legacy as dbl
    from modules import db_postgres

    monkeypatch.setattr(dbl, "_get_db_engine", lambda: "postgres")
    monkeypatch.setattr(dbl, "_postgres_images_has_image_embedding_column", lambda: True)
    monkeypatch.setattr(dbl, "_write_legacy_image_embedding_column", lambda: False)
    monkeypatch.setattr(dbl, "_pg_embedding_table_for_dim", lambda dim: f"image_embeddings_{dim}")

    select_calls = []

    def mock_select(query, params=None):
        select_calls.append(query)
        if "embedding_spaces" in query:
            return [{"id": 1, "code": "mobilenet_v2_imagenet_gap", "dim": 1280}]
        return []

    monkeypatch.setattr(db_postgres, "execute_select", mock_select)

    dbl.get_batch_image_embedding_presence([100])

    assert not any("images" in q and "image_embedding IS NOT NULL" in q for q in select_calls)


def test_maybe_warn_legacy_embedding_drift_logs_once(monkeypatch, caplog):
    import logging

    import modules.db_legacy as dbl
    from modules import db_postgres

    dbl._legacy_embedding_drift_warned = False
    monkeypatch.setattr(dbl, "_get_db_engine", lambda: "postgres")
    monkeypatch.setattr(dbl, "_postgres_images_has_image_embedding_column", lambda: True)
    monkeypatch.setattr(dbl, "_write_legacy_image_embedding_column", lambda: True)
    monkeypatch.setattr(
        db_postgres,
        "execute_select_one",
        lambda *a, **k: {"c": 3},
    )

    with caplog.at_level(logging.WARNING):
        dbl._maybe_warn_legacy_embedding_column_drift()
        dbl._maybe_warn_legacy_embedding_column_drift()

    assert sum(1 for r in caplog.records if "image_embeddings rows" in r.message) == 1


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

