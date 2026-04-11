import os
os.environ["PYTEST_CURRENT_TEST"] = "1"

import shutil
import time
import pytest
import tempfile
from unittest.mock import patch

from modules import db, clustering, selection_runner, db_postgres
from modules.phases import PhaseCode, PhaseStatus

# Force pool reset to ensure we use the test database configuration
db_postgres.reset_pool()


@pytest.fixture
def setup_db_and_images():
    # Use test DB
    os.environ["SKIP_DB_INIT"] = "0"
    db.init_db()

    # Unique folder per test run avoids stale rows / file_paths collisions in Postgres
    test_dir = tempfile.mkdtemp(prefix="test_sel_stop_")
    
    # Create test images
    image_paths = []
    for i in range(5):
        p = os.path.join(test_dir, f"img_{i}.jpg")
        with open(p, "w") as f:
            f.write("test")
        image_paths.append(p)
    
    # Import into DB
    folder_id = db.get_or_create_folder(test_dir)
    image_ids = []
    for p in image_paths:
        fname = os.path.basename(p)
        iid, _ = db.register_image_for_import(p, fname, "jpg", folder_id)
        assert iid is not None, f"register_image_for_import failed for {p}"
        image_ids.append(iid)
        db.update_image_field(iid, "score_general", 0.8)
    
    yield test_dir, image_ids, image_paths

    if os.path.isdir(test_dir):
        shutil.rmtree(test_dir, ignore_errors=True)

def test_selection_runner_graceful_stop(setup_db_and_images):
    test_dir, image_ids, image_paths = setup_db_and_images
    
    runner = selection_runner.SelectionRunner()
    job_id = db.create_job(test_dir)
    
    # Mock ClusteringEngine to be slow and check stop_event (force_rescan: engine sets RUNNING here)
    def mock_cluster(*args, **kwargs):
        stop_event = kwargs.get("stop_event")
        for iid in image_ids:
            db.set_image_phase_status(
                iid, PhaseCode.CULLING, PhaseStatus.RUNNING, job_id=job_id
            )
        yield ("Starting Clustering...", 0, 100)
        for i in range(10):
            if stop_event and stop_event.is_set():
                yield ("Interrupted", i, 100)
                return
            time.sleep(0.1)
        yield ("Done", 100, 100)

    with patch.object(clustering.ClusteringEngine, "cluster_images", side_effect=mock_cluster):
        # force_rescan: clustering drives RUNNING; mock_cluster also sets RUNNING once cluster starts
        runner.start_batch(test_dir, job_id=job_id, force_rescan=True)

        for _ in range(30):
            ph0 = db.get_image_phase_status(image_ids[0], PhaseCode.CULLING)
            if ph0 and ph0.get("status") == PhaseStatus.RUNNING.value:
                break
            time.sleep(0.1)
        else:
            assert False, "timed out waiting for CULLING RUNNING"

        # Stop before mock finishes and runner marks DONE (race otherwise)
        runner.stop()

        for _ in range(40):
            if not runner.is_running:
                break
            time.sleep(0.1)
        assert runner.is_running is False
        _, _, status, _, _ = runner.get_status()
        assert status == "stopped"

        for iid in image_ids:
            ph = db.get_image_phase_status(iid, PhaseCode.CULLING)
            assert ph is not None
            assert ph["status"] == PhaseStatus.RUNNING.value
            
        # Terminal "failed" reconciles in-flight rows to failed inside update_job_status.
        # "interrupted" reconciles to not_started (resumable) — matches graceful pause semantics.
        db.update_job_status(job_id, "interrupted")

        for iid in image_ids:
            ph = db.get_image_phase_status(iid, PhaseCode.CULLING)
            assert ph["status"] == PhaseStatus.NOT_STARTED.value
            
        print("Test passed successfully!")

if __name__ == "__main__":
    os.environ["PYTEST_CURRENT_TEST"] = "1"
    print("Starting manual test...")
    # Use a unique folder for each manual run to avoid DB collisions
    test_dir_base = os.path.abspath("temp_test_selection_stop_manual")
    test_dir = f"{test_dir_base}_{int(time.time())}"
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    os.makedirs(test_dir)
    print(f"Created unique test dir: {test_dir}")
    
    try:
        print("Initializing DB...")
        db.init_db()
        print("DB initialized.")
        
        # Create test images
        image_paths = []
        for i in range(5):
            p = os.path.join(test_dir, f"img_{i}.jpg")
            with open(p, "w") as f:
                f.write("test")
            image_paths.append(p)
        
        # Clean up existing DB records for this folder to avoid unique constraint issues
        try:
            path_pattern = test_dir + os.sep + "%"
            db.get_connector().execute("DELETE FROM image_phase_status WHERE image_id IN (SELECT id FROM images WHERE file_path LIKE ?)", (path_pattern,))
            db.get_connector().execute("DELETE FROM images WHERE file_path LIKE ?", (path_pattern,))
            print("Cleaned up existing DB records for test folder.")
        except Exception as e:
            print(f"Cleanup failed: {e}")
            raise e

        # Import into DB
        print("Importing test images into DB...")
        folder_id = db.get_or_create_folder(test_dir)
        image_ids = []
        for p in image_paths:
            fname = os.path.basename(p)
            iid, _ = db.register_image_for_import(p, fname, "jpg", folder_id)
            if iid is None:
                print(f"Failed to register image: {p}")
                continue
            image_ids.append(iid)
            db.update_image_field(iid, "score_general", 0.8)
        print(f"Imported {len(image_ids)} images.")
        
        if not image_ids:
            assert False, "No images were imported successfully."
        
        runner = selection_runner.SelectionRunner()
        job_id = db.create_job(test_dir, phase_code=PhaseCode.CULLING)
        
        # Diagnostic: print all status changes
        original_set_status = db.set_image_phase_status
        def diagnostic_set_status(image_id, phase_code, status, **kwargs):
            print(f"DIAGNOSTIC: set_image_phase_status(img={image_id}, phase={phase_code}, status={status})")
            return original_set_status(image_id, phase_code, status, **kwargs)

        # Mock ClusteringEngine to be slow and check stop_event
        def mock_cluster(*args, **kwargs):
            print("MOCK CLUSTER CALLED")
            # In force_rescan mode, clustering engine is responsible for setting status to RUNNING
            for iid in image_ids:
                db.set_image_phase_status(iid, PhaseCode.CULLING, PhaseStatus.RUNNING.value, job_id=job_id)
            
            stop_event = kwargs.get("stop_event")
            yield ("Starting Clustering...", 0, 100)
            # Sleep longer to allow time for stop() to be called and polling to see RUNNING
            for i in range(30):
                if stop_event and stop_event.is_set():
                    print("MOCK CLUSTER DETECTED STOP")
                    yield ("Interrupted", i, 100)
                    return
                time.sleep(0.1)
            yield ("Done", 100, 100)

        with patch("modules.db.set_image_phase_status", side_effect=diagnostic_set_status), \
             patch("modules.clustering.ClusteringEngine.cluster_images", side_effect=mock_cluster):
            print("Starting batch...")
            runner.start_batch(test_dir, job_id=job_id, force_rescan=True)
            
            # Wait for it to start running (up to 2 seconds)
            print("Waiting for RUNNING status...")
            for _ in range(20):
                ph = db.get_image_phase_status(image_ids[0], PhaseCode.CULLING)
                if ph and ph["status"] == PhaseStatus.RUNNING.value:
                    print("Status is RUNNING.")
                    break
                time.sleep(0.1)
            else:
                ph = db.get_image_phase_status(image_ids[0], PhaseCode.CULLING)
                print(f"Timed out waiting for RUNNING. Last ph: {ph}")
                assert False, "Timed out waiting for images to be marked as RUNNING"
            
            # Stop the runner
            print("Stopping runner...")
            runner.stop()
            
            # Wait for thread to finish
            for _ in range(20):
                if not runner.is_running:
                    break
                time.sleep(0.1)
                
            assert runner.is_running is False
            _, _, status, _, _ = runner.get_status()
            assert status == "stopped"

            # Verify images are STILL marked as RUNNING (not DONE)
            for iid in image_ids:
                ph = db.get_image_phase_status(iid, PhaseCode.CULLING)
                assert ph["status"] == PhaseStatus.RUNNING.value
                
            # Mark job as interrupted manually. This should trigger automatic reconciliation to 'not_started'.
            print("Updating job status to interrupted...")
            db.update_job_status(job_id, "interrupted")
            
            # Verify images are now NOT_STARTED (resumable)
            for iid in image_ids:
                ph = db.get_image_phase_status(iid, PhaseCode.CULLING)
                assert ph["status"] == PhaseStatus.NOT_STARTED.value
            
            print("Manual test PASSED!")
            for iid in image_ids:
                ph = db.get_image_phase_status(iid, PhaseCode.CULLING)
                assert ph["status"] == PhaseStatus.NOT_STARTED.value
                
            print("Test passed successfully!")
    finally:
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)
