"""
Unit and Integration tests for AI Culling workflow.

Uses scoring_history_test.fdb (per tests-use-test-db-only rule).
Tests:
1. test_create_session - Session creation and persistence
2. test_import_images - Image import and grouping
3. test_auto_pick - Auto-pick best in groups
4. test_export_xmp - XMP sidecar export (with format verification)
5. test_full_workflow - End-to-end culling workflow
"""

import os
import sys
import shutil
import logging
import xml.etree.ElementTree as ET
import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import config as app_config
from modules import db
from modules.culling import CullingEngine
from modules.xmp import NAMESPACES

# Configure logging
logging.basicConfig(level=logging.WARNING)

pytestmark = pytest.mark.wsl


def _assert_xmp_pick_format(xmp_path: str, expected_pick: int) -> None:
    """Verify XMP sidecar has correct xmpDM:pick and xmpDM:good values."""
    tree = ET.parse(xmp_path)
    root = tree.getroot()
    desc = root.find('.//{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description')
    assert desc is not None, f"No rdf:Description in {xmp_path}"
    pick_key = f'{{{NAMESPACES["xmpDM"]}}}pick'
    good_key = f'{{{NAMESPACES["xmpDM"]}}}good'
    pick_val = desc.get(pick_key)
    good_val = desc.get(good_key)
    assert pick_val is not None, f"Missing xmpDM:pick in {xmp_path}"
    assert int(pick_val) == expected_pick, f"Expected pick={expected_pick}, got {pick_val}"
    if expected_pick == 1:
        assert good_val == 'true', f"Picked image should have good=true, got {good_val}"
    elif expected_pick == -1:
        assert good_val == 'false', f"Rejected image should have good=false, got {good_val}"


class TestCullingWorkflow:
    """Test suite for culling workflow operations."""

    @pytest.fixture(scope="class", autouse=True)
    def setup_database_fixture(self, postgres_test_session):
        """Fixture: use scoring_history_test.fdb, create temp dir for test image files."""
        if app_config.get_database_engine() == "postgres":
            from modules import db_postgres

            db_postgres.truncate_app_tables()
            db_postgres.reset_pool()
            try:
                from modules.db_connector import reset_connector

                reset_connector()
            except Exception:
                pass

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        temp_dir = os.path.join(project_root, 'temp_test_cull')
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        os.makedirs(temp_dir, exist_ok=True)

        self.__class__.test_images_dir = os.path.join(temp_dir, 'test_images')
        os.makedirs(self.test_images_dir, exist_ok=True)

        # Use scoring_history_test.fdb (set by conftest / db.py under pytest)
        db.init_db()
        self._create_test_images()

        yield

        shutil.rmtree(temp_dir, ignore_errors=True)
        try:
            db.get_db().close()
        except Exception:
            pass
    

    def _create_test_images(self):
        """Insert test images with scores for culling tests."""
        conn = db.get_db()
        c = conn.cursor()
        
        # Create test folder
        # Create test folder using DB logic to ensure path normalization matches
        folder_id = db.get_or_create_folder(self.test_images_dir)


        
        # Create test images (3 groups of 3 similar images each)
        # Group 1: Wedding photos (similar timestamps, varying scores)

        test_images = [
            (f'{self.test_images_dir}/wedding_001.jpg', 'wedding_001.jpg', 0.85, 0.80, 0.75, folder_id),
            (f'{self.test_images_dir}/wedding_002.jpg', 'wedding_002.jpg', 0.92, 0.88, 0.85, folder_id),  # Best in group
            (f'{self.test_images_dir}/wedding_003.jpg', 'wedding_003.jpg', 0.78, 0.75, 0.70, folder_id),
            # Group 2: Portrait photos
            (f'{self.test_images_dir}/portrait_001.jpg', 'portrait_001.jpg', 0.88, 0.85, 0.82, folder_id),  # Best
            (f'{self.test_images_dir}/portrait_002.jpg', 'portrait_002.jpg', 0.75, 0.72, 0.70, folder_id),
            # Single image (no group)
            (f'{self.test_images_dir}/landscape_001.jpg', 'landscape_001.jpg', 0.90, 0.87, 0.85, folder_id),
        ]
        
        for path, name, gen, tech, aes, fid in test_images:
            c.execute("""
                UPDATE OR INSERT INTO images (file_path, file_name, score_general, score_technical, score_aesthetic, folder_id)
                VALUES (?, ?, ?, ?, ?, ?)
                MATCHING (file_path)
            """, (path, name, gen, tech, aes, fid))
            
            # Create dummy image files for XMP tests
            with open(path, 'w') as f:
                f.write('dummy image data')
        
        conn.commit()
        conn.close()
    
    def _cleanup_session(self, session_id):
        """Helper to clean up a culling session."""
        try:
            conn = db.get_db()
            c = conn.cursor()
            c.execute("DELETE FROM culling_picks WHERE session_id = ?", (session_id,))
            c.execute("DELETE FROM culling_sessions WHERE id = ?", (session_id,))
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()


    def test_create_session(self):
        """Test that culling sessions are created and persisted correctly."""
        engine = CullingEngine()
        session_id = engine.create_session(self.test_images_dir, mode='automated')
        
        assert session_id is not None, "Session should be created"
        assert session_id > 0, "Session ID should be positive"
        
        # Verify session exists in DB
        session = db.get_culling_session(session_id)
        assert session is not None, "Session should be retrievable from DB"
        assert session['folder_path'] == self.test_images_dir, "Session folder path should match"
        assert session['mode'] == 'automated', "Session mode should be automated"
        
        # Cleanup
        self._cleanup_session(session_id)

    @pytest.mark.ml
    def test_import_images(self):
        """Test image import and grouping functionality."""
        
        engine = CullingEngine()
        
        # Create session
        session_id = engine.create_session(self.test_images_dir)
        assert session_id is not None, "Session should be created"
        
        # Import images
        stats = engine.import_images(
            session_id, 
            distance_threshold=0.3,  # Relaxed threshold for test
            time_gap_seconds=300
        )
        
        # Verify import stats
        assert 'error' not in stats, f"Import should succeed: {stats.get('error')}"
        assert stats.get('total', 0) == 6, f"Should import 6 images, got {stats.get('total')}"
        
        # Cleanup
        self._cleanup_session(session_id)

    @pytest.mark.ml
    def test_auto_pick(self):
        """Test auto-pick selects best image in each group."""
        
        engine = CullingEngine()
        
        # Create and populate session
        session_id = engine.create_session(self.test_images_dir)
        stats = engine.import_images(session_id, distance_threshold=0.3)
        
        # Run auto-pick
        pick_stats = engine.auto_pick_all(session_id, score_field='score_general')
        
        assert 'picked' in pick_stats, "Should have pick count"
        assert pick_stats['picked'] > 0, "Should pick at least one image"
        
        # Verify picks
        picks = engine.get_picks(session_id)
        assert len(picks) > 0, "Should have picked images"
        
        # Cleanup
        self._cleanup_session(session_id)

    @pytest.mark.ml
    def test_export_xmp(self):
        """Test XMP sidecar export for culling decisions and verify format (xmpDM:pick, xmpDM:good)."""
        engine = CullingEngine()

        # Run full cull workflow without auto-export
        result = engine.run_full_cull(
            self.test_images_dir,
            distance_threshold=0.3,
            auto_export=False
        )

        session_id = result.get('session_id')
        assert session_id, "Should have session ID"

        # Now export to XMP (using new Pick/Reject flag system)
        export_stats = engine.export_to_xmp(session_id)

        assert 'exported' in export_stats, "Should have export count"
        assert 'errors' in export_stats, "Should have error count"

        # Check that XMP files were created and verify format (xmpDM:pick, xmpDM:good)
        picks = engine.get_picks(session_id)
        rejects = engine.get_rejects(session_id)
        expected_by_path = {os.path.normpath(p['file_path']): 1 for p in picks}
        expected_by_path.update({os.path.normpath(r['file_path']): -1 for r in rejects})

        xmp_files = [f for f in os.listdir(self.test_images_dir) if f.endswith('.xmp')]
        assert len(xmp_files) > 0, f"Should create XMP files, found: {xmp_files}"

        for xmp_file in xmp_files:
            base = xmp_file.replace('.xmp', '')
            img_path = os.path.normpath(os.path.join(self.test_images_dir, base + '.jpg'))
            xmp_path = os.path.join(self.test_images_dir, xmp_file)
            expected_pick = expected_by_path.get(img_path)
            if expected_pick is not None:
                _assert_xmp_pick_format(xmp_path, expected_pick)

        # Cleanup
        self._cleanup_session(session_id)

        for xmp_file in xmp_files:
            try:
                os.remove(os.path.join(self.test_images_dir, xmp_file))
            except Exception:
                pass

    @pytest.mark.ml
    def test_full_workflow(self):
        """End-to-end test of complete culling workflow."""
        
        engine = CullingEngine()
        
        # Run complete workflow
        result = engine.run_full_cull(
            self.test_images_dir,
            distance_threshold=0.3,
            time_gap_seconds=300,
            score_field='score_general',
            auto_export=True
        )
        
        # Verify results
        assert 'error' not in result, f"Workflow should succeed: {result.get('error')}"
        assert result.get('session_id'), "Should have session ID"
        assert result.get('total', 0) > 0, "Should have imported images"
        assert result.get('picked', 0) > 0, "Should have picked images"
        assert result.get('exported') == True, "Should have exported"
        
        # Cleanup
        self._cleanup_session(result['session_id'])
        
        # Clean up XMP files
        xmp_files = [f for f in os.listdir(self.test_images_dir) if f.endswith('.xmp')]
        for xmp_file in xmp_files:
            try:
                os.remove(os.path.join(self.test_images_dir, xmp_file))
            except Exception:
                pass

    @pytest.mark.ml
    @pytest.mark.sample_data
    def test_full_workflow_real_data(self):
        """Optional: run full cull on a folder with real scored images. Set IMAGE_SCORING_TEST_CULLING_FOLDER."""
        folder = os.environ.get("IMAGE_SCORING_TEST_CULLING_FOLDER")
        if not folder or not os.path.isdir(folder):
            pytest.skip("Set IMAGE_SCORING_TEST_CULLING_FOLDER to run real-data culling test")

        engine = CullingEngine()
        result = engine.run_full_cull(
            folder,
            distance_threshold=0.3,
            time_gap_seconds=300,
            score_field='score_general',
            auto_export=False,
        )

        assert 'error' not in result, f"Workflow should succeed: {result.get('error')}"
        assert result.get('session_id'), "Should have session ID"
        assert result.get('total', 0) > 0, "Should import images from real folder"
        assert result.get('picked', 0) > 0, "Should pick at least one image"

        # Cleanup
        self._cleanup_session(result['session_id'])


