"""
Tests for ``image_incidents`` (PostgreSQL). Opt-in: ``pytest -m postgres`` or ``RUN_POSTGRES_TESTS=1``.
"""

import os
import sys
import uuid

import pytest

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

pytestmark = [pytest.mark.postgres]


@pytest.fixture(autouse=True)
def _postgres_clean_each_test(postgres_test_session, clean_postgres):
    yield


def test_record_and_list_image_incidents():
    from modules import db
    from modules import db_postgres

    suffix = uuid.uuid4().hex[:8]
    folder_path = f"integration/incidents_{suffix}"
    fr = db_postgres.execute_write_returning(
        "INSERT INTO folders (path) VALUES (%s) RETURNING id",
        (folder_path,),
    )
    folder_id = fr["id"]
    fp = f"integration/img_{suffix}.jpg"
    img = db_postgres.execute_write_returning(
        "INSERT INTO images (file_path, file_name, folder_id, score) VALUES (%s, %s, %s, %s) RETURNING id",
        (fp, f"img_{suffix}.jpg", folder_id, 0.0),
    )
    image_id = img["id"]

    iid = db.record_image_incident(
        image_id,
        kind="validation",
        message="bad exif",
        phase_code="metadata",
        source="test",
        detail={"field": "iso"},
    )
    assert iid is not None

    out = db.list_image_incidents(limit=20, kind="validation")
    assert out["total"] >= 1
    found = [x for x in out["items"] if x["id"] == iid]
    assert len(found) == 1
    assert found[0]["message"] == "bad exif"
    assert found[0]["file_path"] == fp

    one = db.get_image_incident(iid)
    assert one is not None
    assert one["message"] == "bad exif"
    assert one["file_path"] == fp
    assert (one.get("phase_code") or "").strip() == "metadata"
