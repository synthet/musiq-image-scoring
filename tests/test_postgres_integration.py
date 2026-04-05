"""
PostgreSQL + pgvector integration tests against database ``image_scoring_test``.

Opt-in: ``RUN_POSTGRES_TESTS=1`` or ``pytest -m postgres``.
Requires ``psycopg2-binary``, ``pgvector``, and a reachable server (e.g. ``docker compose up -d db``).
"""

import os
import sys

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
    for table in ("embedding_spaces", "image_embeddings"):
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


def test_insert_folder_and_image_with_embedding():
    from modules import db_postgres

    folder = db_postgres.execute_write_returning(
        "INSERT INTO folders (path) VALUES (%s) RETURNING id",
        ("integration/test_folder",),
    )
    assert folder is not None
    folder_id = folder["id"]

    emb = np.random.rand(1280).astype(np.float32)
    img = db_postgres.execute_write_returning(
        "INSERT INTO images (file_path, file_name, folder_id, score, image_embedding) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id, file_name",
        ("integration/a.jpg", "a.jpg", folder_id, 0.42, emb),
    )
    assert img is not None
    assert img["file_name"] == "a.jpg"

    row = db_postgres.execute_select_one(
        "SELECT file_name, score, folder_id FROM images WHERE id = %s",
        (img["id"],),
    )
    assert row["file_name"] == "a.jpg"
    assert abs(row["score"] - 0.42) < 1e-9
    assert row["folder_id"] == folder_id


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
