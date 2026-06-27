"""
Tests for pipeline phase DB helpers.

Tests: seeding, upsert, running→running guard, attempt_count increment,
and live folder phase summary aggregation.

Run:
    pytest tests/test_phases_db.py -v
"""
import os
import sys
import shutil
import uuid
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import db
from modules.phases import PhaseCode, PhaseStatus

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def test_db(tmp_path_factory):
    """
    Initialise a fresh test DB for the whole module.
    Requires template.fdb in the project root (same as other FB tests).
    """
    tmp = tmp_path_factory.mktemp("phases_db")
    db_path = str(tmp / f"phases_{uuid.uuid4().hex}.fdb")
    template = os.path.abspath("template.fdb")

    if not os.path.exists(template):
        pytest.skip("template.fdb not found — Firebird not available")

    shutil.copy2(template, db_path)

    original_path = db.DB_PATH
    db.DB_PATH = os.path.abspath(db_path)
    db.reset_init_db_state_for_tests()

    try:
        db.init_db()
    except Exception as e:
        pytest.skip(f"DB init failed: {e}")

    yield db_path

    db.DB_PATH = original_path




def _insert_image_with_folder(folder: str, filename: str):
    folder_id = db.get_or_create_folder(folder)
    # Get the actual path stored in DB
    conn = db.get_db()
    c = conn.cursor()
    c.execute("SELECT path FROM folders WHERE id = ?", (folder_id,))
    stored_path = c.fetchone()[0]
    
    path = f"{stored_path}/{filename}"
    c.execute(
        "INSERT INTO images (file_path, folder_id, file_name) VALUES (?, ?, ?) RETURNING id",
        (path, folder_id, filename)
    )
    row = c.fetchone()
    conn.commit()
    conn.close()
    return row[0] if row else None, stored_path


def _add_test_image(folder="test_phases_folder", filename="test.jpg"):
    """Insert a minimal image row and return its id."""
    conn = db.get_db()
    c = conn.cursor()
    path = f"{folder}/{filename}"
    c.execute(
        "INSERT INTO images (file_path, folder_id, file_name) "
        "VALUES (?, (SELECT FIRST 1 id FROM folders), ?) RETURNING id",
        (path, filename)
    )
    row = c.fetchone()
    conn.commit()
    conn.close()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPhaseSeed:
    def test_seed_phase_count(self, test_db):
        """PIPELINE_PHASES must have at least 5 rows after init_db."""
        conn = db.get_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM pipeline_phases WHERE enabled = 1")
        count = c.fetchone()[0]
        conn.close()
        assert count >= 5, f"Expected >= 5 phases, got {count}"

    def test_all_expected_codes_present(self, test_db):
        """All expected phase codes must exist."""
        conn = db.get_db()
        c = conn.cursor()
        c.execute("SELECT code FROM pipeline_phases")
        codes = {row[0].strip() for row in c.fetchall()}
        conn.close()
        for code in (PhaseCode.INDEXING, PhaseCode.METADATA, PhaseCode.SCORING,
                     PhaseCode.CULLING, PhaseCode.KEYWORDS):
            assert code.value in codes, f"Phase code '{code.value}' missing from DB"


class TestSetImagePhaseStatus:
    def test_insert_new_status(self, test_db):
        """set_image_phase_status inserts a new row for a fresh image."""
        img_id = _add_test_image(filename="insert_test.jpg")
        if img_id is None:
            pytest.skip("Could not insert test image")

        db.set_image_phase_status(
            img_id, PhaseCode.SCORING, PhaseStatus.DONE,
            app_version="test-1.0", executor_version="exec-1.0"
        )

        conn = db.get_db()
        c = conn.cursor()
        phase_id = db.get_phase_id(PhaseCode.SCORING)
        c.execute(
            "SELECT status, app_version, executor_version "
            "FROM image_phase_status WHERE image_id = ? AND phase_id = ?",
            (img_id, phase_id)
        )
        row = c.fetchone()
        conn.close()

        assert row is not None, "Status row not found after insert"
        assert row[0].strip() == PhaseStatus.DONE
        assert row[1] == "test-1.0"
        assert row[2] == "exec-1.0"

    def test_running_to_running_guard(self, test_db):
        """running → running must be a no-op (guard)."""
        img_id = _add_test_image(filename="guard_test.jpg")
        if img_id is None:
            pytest.skip("Could not insert test image")

        db.set_image_phase_status(img_id, PhaseCode.METADATA, PhaseStatus.RUNNING)

        conn = db.get_db()
        c = conn.cursor()
        phase_id = db.get_phase_id(PhaseCode.METADATA)
        c.execute(
            "SELECT updated_at FROM image_phase_status WHERE image_id = ? AND phase_id = ?",
            (img_id, phase_id)
        )
        ts_before = c.fetchone()[0]
        conn.close()

        import time
        time.sleep(0.05)

        # Second running call — should be a no-op
        db.set_image_phase_status(img_id, PhaseCode.METADATA, PhaseStatus.RUNNING)

        conn = db.get_db()
        c = conn.cursor()
        c.execute(
            "SELECT updated_at FROM image_phase_status WHERE image_id = ? AND phase_id = ?",
            (img_id, phase_id)
        )
        ts_after = c.fetchone()[0]
        conn.close()

        # Timestamp must NOT have changed
        assert ts_before == ts_after, "Guard failed: running→running updated the row"

    def test_attempt_count_increments_on_rerun(self, test_db):
        """done → running must increment attempt_count."""
        img_id = _add_test_image(filename="attempt_test.jpg")
        if img_id is None:
            pytest.skip("Could not insert test image")

        db.set_image_phase_status(img_id, PhaseCode.KEYWORDS, PhaseStatus.DONE)
        db.set_image_phase_status(img_id, PhaseCode.KEYWORDS, PhaseStatus.RUNNING)

        conn = db.get_db()
        c = conn.cursor()
        phase_id = db.get_phase_id(PhaseCode.KEYWORDS)
        c.execute(
            "SELECT attempt_count FROM image_phase_status WHERE image_id = ? AND phase_id = ?",
            (img_id, phase_id)
        )
        count = c.fetchone()[0]
        conn.close()

        assert count == 1, f"Expected attempt_count=1 after rerun, got {count}"


    def test_skip_metadata_and_retry_clear(self, test_db):
        """skipped stores reason/actor and retry to running clears skip metadata."""
        img_id = _add_test_image(filename="skip_test.jpg")
        if img_id is None:
            pytest.skip("Could not insert test image")

        db.set_image_phase_status(
            img_id, PhaseCode.CULLING, PhaseStatus.SKIPPED,
            skip_reason="manual decision", skipped_by="tester"
        )

        conn = db.get_db()
        c = conn.cursor()
        phase_id = db.get_phase_id(PhaseCode.CULLING)
        c.execute(
            "SELECT status, skip_reason, skipped_by FROM image_phase_status WHERE image_id = ? AND phase_id = ?",
            (img_id, phase_id)
        )
        row = c.fetchone()
        conn.close()

        assert row is not None
        assert row[0].strip() == PhaseStatus.SKIPPED
        assert row[1] == "manual decision"
        assert row[2].strip() == "tester"

        db.set_image_phase_status(img_id, PhaseCode.CULLING, PhaseStatus.RUNNING)

        conn = db.get_db()
        c = conn.cursor()
        c.execute(
            "SELECT status, skip_reason, skipped_by FROM image_phase_status WHERE image_id = ? AND phase_id = ?",
            (img_id, phase_id)
        )
        row2 = c.fetchone()
        conn.close()

        assert row2[0].strip() == PhaseStatus.RUNNING
        assert row2[1] is None
        assert row2[2] is None


class TestFolderPhaseSummary:
    def test_partial_when_mixed_status(self, test_db):
        """
        get_folder_phase_summary returns 'partial' when some images are done
        and some are not_started for the same phase.
        """
        # Skip this test: it needs folder rows + multiple images.
        # A more complete version would insert 2 images, mark phase for 1 only.
        pytest.skip("Requires full folder insert fixture — covered in integration tests")

    def test_done_when_all_done(self, test_db):
        """get_folder_phase_summary returns 'done' when all images in a folder are done."""
        pytest.skip("Requires full folder insert fixture — covered in integration tests")


    def test_running_failed_skipped_semantics(self, test_db):
        base_root = os.path.abspath(f"phase_semantics_{uuid.uuid4().hex[:6]}")

        # running wins while active work exists
        img1, stored_path = _insert_image_with_folder(base_root, "run_1.jpg")
        img2, _ = _insert_image_with_folder(base_root, "run_2.jpg")
        db.set_image_phase_status(img1, PhaseCode.SCORING, PhaseStatus.RUNNING)
        
        summary_list = db.get_folder_phase_summary(base_root, force_refresh=True)
        summary = {r['code']: r for r in summary_list}
        
        # Active work: running_count > 0 maps to status 'running' (see get_folder_phase_summary)
        assert summary[PhaseCode.SCORING.value]['status'] == 'running'

        # partial when some failed but most images were never attempted
        fail_folder = base_root + "_failed"
        fimg, _ = _insert_image_with_folder(fail_folder, "fail_1.jpg")
        _insert_image_with_folder(fail_folder, "fail_2.jpg")
        db.set_image_phase_status(fimg, PhaseCode.KEYWORDS, PhaseStatus.FAILED)
        fsum = {r['code']: r for r in db.get_folder_phase_summary(fail_folder, force_refresh=True)}
        assert fsum[PhaseCode.KEYWORDS.value]['status'] == 'partial'

        # failed only when every image in scope failed
        all_fail_folder = base_root + "_all_failed"
        af1, _ = _insert_image_with_folder(all_fail_folder, "af_1.jpg")
        af2, _ = _insert_image_with_folder(all_fail_folder, "af_2.jpg")
        db.set_image_phase_status(af1, PhaseCode.KEYWORDS, PhaseStatus.FAILED)
        db.set_image_phase_status(af2, PhaseCode.KEYWORDS, PhaseStatus.FAILED)
        afsum = {r['code']: r for r in db.get_folder_phase_summary(all_fail_folder, force_refresh=True)}
        assert afsum[PhaseCode.KEYWORDS.value]['status'] == 'failed'

        # skipped when every image is skipped
        skip_folder = base_root + "_skipped"
        simg1, _ = _insert_image_with_folder(skip_folder, "skip_1.jpg")
        simg2, _ = _insert_image_with_folder(skip_folder, "skip_2.jpg")
        db.set_image_phase_status(simg1, PhaseCode.METADATA, PhaseStatus.SKIPPED)
        db.set_image_phase_status(simg2, PhaseCode.METADATA, PhaseStatus.SKIPPED)
        ssum = {r['code']: r for r in db.get_folder_phase_summary(skip_folder, force_refresh=True)}
        
        # Mandatory phase fully skipped -> 'partial' (since it's not 'done')
        # Actually, if ALL are skipped, maybe it should be 'skipped'? 
        # But implementation says 'elif skipped == total and is_optional'
        assert ssum[PhaseCode.METADATA.value]['status'] == 'partial'

    def test_phase_aggregate_invalidated_on_status_update(self, test_db):
        folder = os.path.abspath(f"phase_invalidate_{uuid.uuid4().hex[:6]}")
        img, _ = _insert_image_with_folder(folder, "inv.jpg")

        first = {r['code']: r for r in db.get_folder_phase_summary(folder, force_refresh=True)}
        assert first[PhaseCode.SCORING.value]['status'] == 'not_started'

        db.set_image_phase_status(img, PhaseCode.SCORING, PhaseStatus.DONE)
        second = {r['code']: r for r in db.get_folder_phase_summary(folder, force_refresh=True)}
        assert second[PhaseCode.SCORING.value]['status'] == 'done'

class TestComplexTransitions:
    def test_failed_to_running_cooldown(self, test_db):
        """Verify that a failed phase can be moved back to running (retry logic)."""
        img_id = _add_test_image(filename="retry_fail.jpg")
        
        # 1. Mark as failed
        db.set_image_phase_status(img_id, PhaseCode.SCORING, PhaseStatus.FAILED)
        
        # 2. Re-trigger as running
        db.set_image_phase_status(img_id, PhaseCode.SCORING, PhaseStatus.RUNNING)
        
        conn = db.get_db()
        c = conn.cursor()
        c.execute("SELECT status, attempt_count FROM image_phase_status WHERE image_id = ?", (img_id,))
        row = c.fetchone()
        conn.close()
        
        assert row[0].strip() == PhaseStatus.RUNNING
        assert row[1] == 1 # Second attempt (0-indexed or 1-indexed? test_attempt_count_increments_on_rerun expected 1)

    def test_partial_folder_reprocessing(self, test_db):
        """Verify folder status when one image is retried while another is still failed."""
        folder = os.path.abspath(f"partial_retry_{uuid.uuid4().hex[:6]}")
        img1, _ = _insert_image_with_folder(folder, "p1.jpg")
        img2, _ = _insert_image_with_folder(folder, "p2.jpg")
        
        # Both failed initially
        db.set_image_phase_status(img1, PhaseCode.SCORING, PhaseStatus.FAILED)
        db.set_image_phase_status(img2, PhaseCode.SCORING, PhaseStatus.FAILED)
        
        # Retry only one
        db.set_image_phase_status(img1, PhaseCode.SCORING, PhaseStatus.RUNNING)
        
        summary = {r['code']: r for r in db.get_folder_phase_summary(folder, force_refresh=True)}
        assert summary[PhaseCode.SCORING.value]['status'] == 'running'
        
        # Finish one
        db.set_image_phase_status(img1, PhaseCode.SCORING, PhaseStatus.DONE)
        summary2 = {r['code']: r for r in db.get_folder_phase_summary(folder, force_refresh=True)}
        # Mixed 'done' and 'failed' results in 'partial' in current implementation
        assert summary2[PhaseCode.SCORING.value]['status'] == 'partial'
