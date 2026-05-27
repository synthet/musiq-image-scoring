"""
PostgreSQL + pgvector integration tests against database ``image_scoring_test``.

Opt-in: ``RUN_POSTGRES_TESTS=1`` or ``pytest -m postgres``.
Requires ``psycopg2-binary``, ``pgvector``, and a reachable server (e.g. ``docker compose up -d db``).
"""

import os
import sys
import uuid

import numpy as np
import pytest

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

pytestmark = [pytest.mark.postgres]


@pytest.fixture(autouse=True)
def _postgres_clean_each_test(postgres_test_session, clean_postgres):
    yield


def test_vector_extension_and_core_tables():
    from modules import db_postgres

    ext = db_postgres.execute_select_one(
        "SELECT extname FROM pg_extension WHERE extname = %s",
        ("vector",),
    )
    assert ext is not None
    assert ext["extname"] == "vector"

    for table in ("images", "folders", "jobs"):
        row = db_postgres.execute_select_one(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = %s",
            (table,),
        )
        assert row is not None, f"missing table {table}"


def test_embedding_spaces_and_image_embeddings_tables():
    """Verify embedding_spaces registry and image_embeddings table exist with proper structure."""
    from modules import db_postgres

    # Check embedding_spaces table
    for table in (
        "embedding_spaces",
        "image_embeddings",
        "image_embeddings_512",
        "image_embeddings_768",
    ):
        row = db_postgres.execute_select_one(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = %s",
            (table,),
        )
        assert row is not None, f"missing table {table}"

    # Verify embedding_spaces seed row
    space = db_postgres.execute_select_one(
        "SELECT id, code, dim FROM embedding_spaces WHERE code = %s",
        ("mobilenet_v2_imagenet_gap",),
    )
    assert space is not None, "missing default embedding space"
    assert space["dim"] == 1280


def test_multi_dim_embedding_spaces_and_hnsw_indexes():
    """CLIP, BioCLIP, BLIP rows must exist with matching HNSW cosine indexes."""
    from modules import db_postgres

    expected_spaces = {
        "clip_vit_b32_image": 512,
        "bioclip_2_image": 768,
        "blip_vit_b16_image": 768,
    }
    for code, dim in expected_spaces.items():
        row = db_postgres.execute_select_one(
            "SELECT code, dim, active FROM embedding_spaces WHERE code = %s",
            (code,),
        )
        assert row is not None, f"embedding_spaces row missing for {code}"
        assert int(row["dim"]) == dim, f"wrong dim for {code}"
        assert int(row["active"] or 0) == 1, f"space {code} must be active"

    for table in ("image_embeddings_512", "image_embeddings_768"):
        hnsw = db_postgres.execute_select_one(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname = 'public' AND tablename = %s AND indexname = %s",
            (table, f"idx_{table}_hnsw"),
        )
        assert hnsw is not None, f"missing HNSW index on {table}"
        # Fact tables must enforce uniqueness on (image_id, embedding_space_id)
        uq = db_postgres.execute_select_one(
            "SELECT conname FROM pg_constraint "
            "WHERE conrelid = %s::regclass AND contype = 'u'",
            (table,),
        )
        assert uq is not None, f"missing unique constraint on {table}"


def test_update_image_embeddings_batch_for_space_upsert_and_dim_validation():
    """Round-trip upsert for 512-d and 768-d spaces; dim mismatch raises."""
    from modules import db, db_postgres

    suffix = uuid.uuid4().hex[:10]
    folder = db_postgres.execute_write_returning(
        "INSERT INTO folders (path) VALUES (%s) RETURNING id",
        (f"integration/emb_space_{suffix}",),
    )
    img = db_postgres.execute_write_returning(
        "INSERT INTO images (file_path, file_name, folder_id) VALUES (%s, %s, %s) RETURNING id",
        (f"integration/emb_space_{suffix}/a.jpg", f"a_{suffix}.jpg", folder["id"]),
    )
    image_id = img["id"]

    clip_vec = np.random.rand(512).astype(np.float32)
    blip_vec = np.random.rand(768).astype(np.float32)

    written = db.update_image_embeddings_batch_for_space(
        "clip_vit_b32_image",
        [(image_id, clip_vec, "openai/clip-vit-base-patch32")],
    )
    assert written == 1
    row = db_postgres.execute_select_one(
        "SELECT model_version FROM image_embeddings_512 e "
        "JOIN embedding_spaces s ON s.id = e.embedding_space_id "
        "WHERE e.image_id = %s AND s.code = %s",
        (image_id, "clip_vit_b32_image"),
    )
    assert row is not None
    assert row["model_version"] == "openai/clip-vit-base-patch32"

    # Upsert replaces the row (second call must not raise on unique key).
    clip_vec2 = np.random.rand(512).astype(np.float32)
    written2 = db.update_image_embeddings_batch_for_space(
        "clip_vit_b32_image",
        [(image_id, clip_vec2, "openai/clip-vit-base-patch32")],
    )
    assert written2 == 1

    written_blip = db.update_image_embeddings_batch_for_space(
        "blip_vit_b16_image",
        [(image_id, blip_vec, "Salesforce/blip-image-captioning-base")],
    )
    assert written_blip == 1
    row_blip = db_postgres.execute_select_one(
        "SELECT 1 AS ok FROM image_embeddings_768 e "
        "JOIN embedding_spaces s ON s.id = e.embedding_space_id "
        "WHERE e.image_id = %s AND s.code = %s",
        (image_id, "blip_vit_b16_image"),
    )
    assert row_blip is not None

    # Wrong dim for the registered space must fail loudly.
    bad = np.random.rand(256).astype(np.float32)
    with pytest.raises(ValueError):
        db.update_image_embeddings_batch_for_space(
            "clip_vit_b32_image",
            [(image_id, bad, None)],
        )


def test_pg_embedding_table_for_dim_resolution():
    """The dim→table mapping must match the migration and init_db DDL."""
    from modules import db

    assert db._pg_embedding_table_for_dim(1280) == "image_embeddings"
    assert db._pg_embedding_table_for_dim(512) == "image_embeddings_512"
    assert db._pg_embedding_table_for_dim(768) == "image_embeddings_768"
    with pytest.raises(ValueError):
        db._pg_embedding_table_for_dim(1024)


def test_insert_folder_and_image_with_embedding():
    from modules import db, db_postgres

    suffix = uuid.uuid4().hex[:10]
    folder_path = f"integration/test_folder_{suffix}"
    folder = db_postgres.execute_write_returning(
        "INSERT INTO folders (path) VALUES (%s) RETURNING id",
        (folder_path,),
    )
    assert folder is not None
    folder_id = folder["id"]

    emb = np.random.rand(1280).astype(np.float32)
    file_path = f"integration/a_{suffix}.jpg"
    file_name = f"a_{suffix}.jpg"
    img = db_postgres.execute_write_returning(
        "INSERT INTO images (file_path, file_name, folder_id, score) "
        "VALUES (%s, %s, %s, %s) RETURNING id, file_name",
        (file_path, file_name, folder_id, 0.42),
    )
    assert img is not None
    assert img["file_name"] == file_name

    db.update_image_embedding(img["id"], emb.tobytes())
    got = db.get_image_embedding(img["id"])
    assert got is not None
    assert len(got) == emb.nbytes

    row = db_postgres.execute_select_one(
        "SELECT file_name, score, folder_id FROM images WHERE id = %s",
        (img["id"],),
    )
    assert row["file_name"] == file_name
    assert abs(row["score"] - 0.42) < 1e-9
    assert row["folder_id"] == folder_id


def test_images_table_legacy_image_embedding_column_absent():
    """Migration 0024 removes images.image_embedding; canonical store is image_embeddings."""
    from modules import db, db_postgres

    row = db_postgres.execute_select_one(
        """
        SELECT 1 AS x FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'images'
          AND column_name = 'image_embedding'
        LIMIT 1
        """
    )
    if row is not None:
        pytest.skip("images.image_embedding still present; run alembic upgrade head (0024)")
    assert db._postgres_images_has_image_embedding_column() is False


def test_upsert_image_re_resolves_stale_folder_id():
    """Stale ``folder_id`` in payload must not violate ``images_folder_id_fkey``."""
    from modules import db

    image_path = os.path.normpath(
        os.path.abspath(os.path.join("integration", "stale_folder_id_upsert_test", "x.jpg"))
    )
    bogus_id = 9_999_999
    result = {
        "image_path": image_path,
        "image_name": "x.jpg",
        "folder_id": bogus_id,
        "score": 0.5,
        "score_general": 0.5,
        "score_technical": 0.5,
        "score_aesthetic": 0.5,
        "summary": {
            "weighted_scores": {
                "general": 0.5,
                "technical": 0.5,
                "aesthetic": 0.5,
            }
        },
        "models": {},
    }
    db.upsert_image(job_id=None, result=result)

    row = db.get_connector().query_one(
        "SELECT folder_id FROM images WHERE file_path = ?",
        (image_path,),
    )
    assert row is not None
    fid = row["folder_id"]
    assert fid is not None
    assert fid != bogus_id
    ok = db.get_connector().query_one("SELECT 1 AS ok FROM folders WHERE id = ?", (fid,))
    assert ok is not None


def test_enqueue_job_round_trips_description():
    from modules import db

    jid, _ = db.enqueue_job(
        "/tmp/scope_desc_test",
        phase_code="scoring",
        job_type="scoring",
        queue_payload={"trigger": "postgres_integration"},
        description="Integration test: jobs.description round-trip.",
    )
    row = db.get_job(jid)
    assert row.get("description") == "Integration test: jobs.description round-trip."
