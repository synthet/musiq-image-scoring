"""
Unit tests for resolved_paths functionality in modules/db.py

Uses scoring_history_test.fdb only (see tests-use-test-db-only rule).
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import db

pytestmark = pytest.mark.db

# All rows use this path prefix so setup/teardown can isolate from other tests.
_RP_ROOT = "/mnt/d/__rp_test__"


class TestResolvedPaths:
    """Test suite for resolved_paths / file_paths (WIN) functionality."""

    @classmethod
    def setup_class(cls):
        db.init_db()
        cls._wipe_rp_test_data()
        cls._seed_images()

    @classmethod
    def teardown_class(cls):
        cls._wipe_rp_test_data()

    @classmethod
    def _wipe_rp_test_data(cls):
        conn = db.get_db()
        c = conn.cursor()
        try:
            c.execute(
                "DELETE FROM file_paths WHERE image_id IN "
                "(SELECT id FROM images WHERE file_path STARTING WITH ?)",
                (_RP_ROOT,),
            )
            c.execute("DELETE FROM images WHERE file_path STARTING WITH ?", (_RP_ROOT,))
            c.execute("DELETE FROM folders WHERE path STARTING WITH ?", (_RP_ROOT,))
            conn.commit()
        finally:
            conn.close()

    @classmethod
    def _seed_images(cls):
        folder_id = db.get_or_create_folder(f"{_RP_ROOT}/photos")
        conn = db.get_db()
        c = conn.cursor()
        test_images = [
            (f"{_RP_ROOT}/photos/test1.jpg", "test1.jpg"),
            (f"{_RP_ROOT}/photos/image2.nef", "image2.nef"),
            (f"{_RP_ROOT}/photos/test3.jpg", "test3.jpg"),
            (f"{_RP_ROOT}/photos/test4.png", "test4.png"),
        ]
        for path, name in test_images:
            c.execute(
                """
                INSERT INTO images (job_id, file_path, file_name, score_general, folder_id, created_at)
                VALUES (NULL, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (path, name, 0.5, folder_id),
            )
        conn.commit()
        conn.close()


def test_convert_to_windows_path():
    """Test WSL path to Windows path conversion."""
    from modules.db import _convert_to_windows_path

    assert _convert_to_windows_path("/mnt/d/Photos/test.jpg") == "D:\\Photos\\test.jpg"
    assert _convert_to_windows_path("/mnt/c/Users/Test/img.nef") == "C:\\Users\\Test\\img.nef"
    assert _convert_to_windows_path("D:\\Photos\\test.jpg") == "D:\\Photos\\test.jpg"
    assert _convert_to_windows_path("D:/Photos/test.jpg") == "D:\\Photos\\test.jpg"
    assert _convert_to_windows_path("D:/mnt/d/Photos/test.jpg") == "D:\\Photos\\test.jpg"
    assert _convert_to_windows_path(r"D:\mnt\d\Photos\test.jpg") == "D:\\Photos\\test.jpg"
    assert _convert_to_windows_path("D:/mnt/c/Users/x/a.jpg") == "C:\\Users\\x\\a.jpg"
    assert _convert_to_windows_path(None) is None
    assert _convert_to_windows_path("") is None


def test_resolve_windows_path():
    """Test storing and retrieving resolved paths."""
    TestResolvedPaths.setup_class()

    conn = db.get_db()
    c = conn.cursor()
    c.execute(
        "SELECT id, file_path FROM images WHERE file_path STARTING WITH ? FETCH FIRST 1 ROWS ONLY",
        (f"{_RP_ROOT}/photos/",),
    )
    row = c.fetchone()
    conn.close()

    assert row is not None, "No WSL-format paths found in test data"
    image_id = row[0]
    wsl_path = row[1]

    result = db.resolve_windows_path(image_id, wsl_path, verify=False)
    assert result is not None, f"resolve_windows_path returned None for path: {wsl_path}"
    assert result.startswith("D:\\"), f"Expected path starting with 'D:\\\\', got '{result}'"

    stored = db.get_resolved_path(image_id, verified_only=False)
    assert stored == result, f"Stored path '{stored}' doesn't match result '{result}'"

    TestResolvedPaths.teardown_class()


def test_get_resolved_path_verified():
    """Test that verified_only parameter works correctly."""
    TestResolvedPaths.setup_class()

    conn = db.get_db()
    c = conn.cursor()
    c.execute(
        "SELECT id FROM images WHERE file_path STARTING WITH ? OFFSET 1 ROWS FETCH NEXT 1 ROWS ONLY",
        (_RP_ROOT,),
    )
    row = c.fetchone()
    assert row is not None
    image_id = row[0]
    conn.close()

    conn = db.get_db()
    c = conn.cursor()
    c.execute("DELETE FROM file_paths WHERE image_id = ?", (image_id,))
    conn.commit()
    conn.close()

    path = "C:\\this_file_should_not_exist_xyz_123.jpg"
    db.resolve_windows_path(image_id, path, verify=False)

    result = db.get_resolved_path(image_id, verified_only=False)
    assert result is not None, "Path should be retrievable when verified_only=False"
    assert result == path

    result_verified = db.get_resolved_path(image_id, verified_only=True)
    assert result_verified is None, f"Expected None for unverified path, but got {result_verified}"

    TestResolvedPaths.teardown_class()


def test_upsert_creates_resolved_path():
    """Test that upsert_image creates resolved_path automatically."""
    TestResolvedPaths.setup_class()

    image_path = f"{_RP_ROOT}/NewFolder/new_image.jpg"
    result = {
        "image_path": image_path,
        "image_name": "new_image.jpg",
        "score": 0.75,
        "score_general": 0.75,
        "score_technical": 0.65,
        "score_aesthetic": 0.70,
    }

    db.upsert_image(job_id=None, result=result)

    conn = db.get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM images WHERE file_path = ?", (image_path,))
    row = c.fetchone()
    conn.close()

    assert row is not None
    image_id = row[0]

    resolved = db.get_resolved_path(image_id, verified_only=False)
    assert resolved is not None
    assert resolved == "D:\\__rp_test__\\NewFolder\\new_image.jpg"

    TestResolvedPaths.teardown_class()


if __name__ == "__main__":
    print("=" * 60)
    print("Run via: pytest tests/test_resolved_paths.py -v")
    print("=" * 60)
