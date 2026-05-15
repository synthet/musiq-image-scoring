"""
Tests for core database CRUD operations in modules/db.py.

Uses the test Firebird database (scoring_history_test.fdb).
Requires: Firebird client libraries installed and test DB initialised.

Run with: python -m pytest tests/test_db_core.py -v -m "db and firebird"
"""

import json
import os
import uuid

import pytest

try:
    import firebird.driver  # noqa: F401 — check availability only
except ImportError:
    pytest.skip("firebird-driver not installed", allow_module_level=True)

from modules import db

pytestmark = [pytest.mark.db, pytest.mark.firebird]


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def test_db():
    """Open a connection to the test database, yield it, then close."""
    db.DB_FILE = "scoring_history_test.fdb"
    db.DB_PATH = os.path.join(db._PROJECT_ROOT, db.DB_FILE)
    # Reset cached connection so our file redirect takes effect
    db._conn = None
    conn = db.get_db()
    yield conn
    conn.close()
    db._conn = None


# ---------------------------------------------------------------------------
# Folder management
# ---------------------------------------------------------------------------

def test_get_or_create_folder_creates_and_returns_id(test_db):
    folder_path = "/test/folder/create_test_unique"
    folder_id = db.get_or_create_folder(folder_path)
    assert isinstance(folder_id, int)
    assert folder_id > 0


def test_get_or_create_folder_idempotent(test_db):
    folder_path = "/test/folder/idempotent_unique"
    id1 = db.get_or_create_folder(folder_path)
    id2 = db.get_or_create_folder(folder_path)
    assert id1 == id2


def test_get_or_create_folder_nested_creates_parents(test_db):
    # Should not raise even with nested paths
    folder_path = "/test/parent_dir/child_dir/grandchild"
    folder_id = db.get_or_create_folder(folder_path)
    assert isinstance(folder_id, int)
    assert folder_id > 0


def test_get_or_create_folder_wsl_path_stops_at_mnt_parent(test_db):
    """Regression: posixpath.dirname('/mnt/d/...') becomes '/mnt'; must not recurse infinitely.

    On Windows-native Python, ``/mnt`` is not treated as a WSL path by ``paths.is_wsl_path``,
    so the old logic could hit ``os.path.abspath`` and RecursionError during prerequisite checks.
    """
    suffix = uuid.uuid4().hex[:12]
    folder_path = f"/mnt/d/test_wsl_mnt_boundary_{suffix}/photos/nested/leaf"
    folder_id = db.get_or_create_folder(folder_path)
    assert isinstance(folder_id, int)
    assert folder_id > 0


# ---------------------------------------------------------------------------
# Image CRUD
# ---------------------------------------------------------------------------

def test_register_image_for_import_returns_id(test_db):
    folder_id = db.get_or_create_folder("/test/import_folder")
    image_id = db.register_image_for_import(
        file_path="/test/import_folder/img_reg_test.jpg",
        file_name="img_reg_test.jpg",
        file_type="jpg",
        folder_id=folder_id,
    )
    assert isinstance(image_id, int)
    assert image_id > 0


def test_image_exists_false_before_insert(test_db):
    assert db.image_exists("/nonexistent/photo_unique_never_inserted.jpg") is False


def test_image_exists_true_after_insert(test_db):
    folder_id = db.get_or_create_folder("/test/exists_test")
    path = "/test/exists_test/exists_check.jpg"
    db.register_image_for_import(path, "exists_check.jpg", "jpg", folder_id)
    assert db.image_exists(path) is True


def test_find_image_id_by_path_returns_none_for_missing(test_db):
    result = db.find_image_id_by_path("/no/such/path_unique_999.jpg")
    assert result is None


def test_find_image_id_by_path_returns_id_after_insert(test_db):
    folder_id = db.get_or_create_folder("/test/find_by_path")
    path = "/test/find_by_path/findme.jpg"
    inserted_id = db.register_image_for_import(path, "findme.jpg", "jpg", folder_id)
    found_id = db.find_image_id_by_path(path)
    assert found_id == inserted_id


# ---------------------------------------------------------------------------
# Job queue
# ---------------------------------------------------------------------------

def test_create_job_returns_integer_id(test_db):
    job_id = db.create_job("/test/jobs/path", phase_code="scoring")
    assert isinstance(job_id, int)
    assert job_id > 0


def test_enqueue_job_returns_id_and_position(test_db):
    job_id, position = db.enqueue_job(
        "/test/enqueue/path",
        phase_code="scoring",
        job_type="scoring",
    )
    assert isinstance(job_id, int)
    assert job_id > 0
    assert isinstance(position, int)
    assert position >= 1


def test_enqueue_job_maintenance_without_phase_code_stores_payload(test_db):
    """Regression: POST /api/maintenance/start passes job_type only (no phase_code)."""
    from modules.maintenance_job_display import maintenance_job_input_path

    qp = {"action": "reconcile", "limit": 10}
    job_id, _pos = db.enqueue_job(
        maintenance_job_input_path("reconcile", qp),
        job_type="maintenance",
        queue_payload=json.dumps(qp),
    )
    assert isinstance(job_id, int) and job_id > 0
    row = db.get_job(job_id)
    assert row["job_type"] == "maintenance"
    payload = json.loads(row["queue_payload"])
    assert payload["action"] == "reconcile"
    assert payload["limit"] == 10


def test_update_job_status_changes_status(test_db):
    job_id = db.create_job("/test/job_status/path")
    db.update_job_status(job_id, "running")
    # Read back via raw SQL
    conn = db.get_db()
    c = conn.cursor()
    c.execute("SELECT status FROM jobs WHERE id = ?", (job_id,))
    row = c.fetchone()
    conn.close()
    assert row is not None
    assert row[0].strip() == "running"




def test_update_job_status_rejects_invalid_transition(test_db):
    job_id = db.create_job("/test/job_invalid/path")
    db.update_job_status(job_id, "completed")
    with pytest.raises(ValueError):
        db.update_job_status(job_id, "paused")


def test_request_cancel_job_returns_not_found_for_missing(test_db):
    result = db.request_cancel_job(999999)
    assert result.get("success") is False
    assert result.get("reason") == "not_found"


def test_dequeue_next_job_returns_job_or_none(test_db):
    # Just verify it doesn't raise and returns None or a dict
    result = db.dequeue_next_job()
    assert result is None or isinstance(result, dict)


# ---------------------------------------------------------------------------
# Phase status
# ---------------------------------------------------------------------------

def test_set_image_phase_status_inserts_row(test_db):
    suffix = uuid.uuid4().hex[:12]
    folder_id = db.get_or_create_folder(f"/test/phase_status_{suffix}")
    image_id, _ = db.register_image_for_import(
        f"/test/phase_status_{suffix}/phase_img.jpg", "phase_img.jpg", "jpg", folder_id
    )
    # Should not raise
    db.set_image_phase_status(image_id, "scoring", "done")
    phases = db.get_image_phase_statuses(image_id)
    assert "scoring" in phases
    assert phases["scoring"]["status"] == "done"


def test_set_image_phase_status_upserts_on_second_call(test_db):
    suffix = uuid.uuid4().hex[:12]
    folder_id = db.get_or_create_folder(f"/test/phase_upsert_{suffix}")
    image_id, _ = db.register_image_for_import(
        f"/test/phase_upsert_{suffix}/upsert_img.jpg", "upsert_img.jpg", "jpg", folder_id
    )
    db.set_image_phase_status(image_id, "scoring", "running")
    db.set_image_phase_status(image_id, "scoring", "done")
    phases = db.get_image_phase_statuses(image_id)
    assert phases["scoring"]["status"] == "done"


def test_get_image_phase_status_matches_statuses_dict(test_db):
    folder_id = db.get_or_create_folder("/test/phase_get_one")
    suffix = uuid.uuid4().hex[:12]
    fp = f"/test/phase_get_one/one_{suffix}.jpg"
    image_id, _ = db.register_image_for_import(fp, f"one_{suffix}.jpg", "jpg", folder_id)
    assert image_id is not None
    assert db.get_image_phase_status(image_id, "indexing") is None
    db.set_image_phase_status(image_id, "indexing", "done")
    one = db.get_image_phase_status(image_id, "indexing")
    all_phases = db.get_image_phase_statuses(image_id)
    assert one == all_phases["indexing"]


# ---------------------------------------------------------------------------
# Stacks
# ---------------------------------------------------------------------------

def test_create_stack_returns_id(test_db):
    stack_id = db.create_stack("test_stack_unique")
    assert isinstance(stack_id, int)
    assert stack_id > 0


def test_create_stack_from_images_and_get_images(test_db):
    folder_id = db.get_or_create_folder("/test/stack_images")
    img1 = db.register_image_for_import(
        "/test/stack_images/stack_a.jpg", "stack_a.jpg", "jpg", folder_id
    )
    img2 = db.register_image_for_import(
        "/test/stack_images/stack_b.jpg", "stack_b.jpg", "jpg", folder_id
    )
    stack_id = db.create_stack_from_images([img1, img2], name="test_stack_from_imgs")
    assert stack_id > 0
    images = db.get_images_in_stack(stack_id)
    image_ids = [img["id"] for img in images]
    assert img1 in image_ids
    assert img2 in image_ids


def test_dissolve_stack_removes_stack(test_db):
    folder_id = db.get_or_create_folder("/test/dissolve_stack")
    img_id = db.register_image_for_import(
        "/test/dissolve_stack/dissolve_img.jpg", "dissolve_img.jpg", "jpg", folder_id
    )
    stack_id = db.create_stack_from_images([img_id], name="dissolve_me")
    db.dissolve_stack(stack_id)
    images = db.get_images_in_stack(stack_id)
    assert images == [] or all(img.get("stack_id") is None for img in images)


# ---------------------------------------------------------------------------
# XMP table
# ---------------------------------------------------------------------------

def test_upsert_image_xmp_inserts_and_get_returns_data(test_db):
    folder_id = db.get_or_create_folder("/test/xmp_table")
    image_id = db.register_image_for_import(
        "/test/xmp_table/xmp_img.jpg", "xmp_img.jpg", "jpg", folder_id
    )
    data = {"rating": 3, "label": "Red", "pick_status": 1}
    result = db.upsert_image_xmp(image_id, data)
    assert result is True

    xmp_row = db.get_image_xmp(image_id)
    assert xmp_row is not None
    assert xmp_row["rating"] == 3
    assert xmp_row["label"] == "Red"


def test_get_image_xmp_returns_none_for_missing(test_db):
    result = db.get_image_xmp(999999)
    assert result is None


def test_upsert_image_xmp_updates_on_second_call(test_db):
    folder_id = db.get_or_create_folder("/test/xmp_upsert")
    image_id = db.register_image_for_import(
        "/test/xmp_upsert/xmp_upd.jpg", "xmp_upd.jpg", "jpg", folder_id
    )
    db.upsert_image_xmp(image_id, {"rating": 2})
    db.upsert_image_xmp(image_id, {"rating": 5})
    xmp_row = db.get_image_xmp(image_id)
    assert xmp_row["rating"] == 5


# ---------------------------------------------------------------------------
# Folder listing
# ---------------------------------------------------------------------------

def test_get_all_folders_returns_list(test_db):
    # Ensure at least one folder exists
    db.get_or_create_folder("/test/all_folders_check")
    folders = db.get_all_folders()
    assert isinstance(folders, list)
    assert len(folders) >= 1
