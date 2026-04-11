
import os
import shutil
import time
import threading
import pytest
from unittest.mock import MagicMock, patch

from modules import db, clustering, selection_runner, selection
from modules.phases import PhaseCode, PhaseStatus
from modules.version import APP_VERSION

@pytest.fixture
def setup_db_and_images():
    # Use test DB
    print("Before setting SKIP_DB_INIT")
    os.environ['SKIP_DB_INIT'] = '0'
    db.init_db()
    print("After db.init_db()")
    
    # Create temp folder
    test_dir = os.path.abspath("temp_test_selection_stop")
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    os.makedirs(test_dir)
    
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
        iid = db.register_image_for_import(p, fname, "jpg", folder_id)
        image_ids.append(iid)
        # Give them a score so policy-check passes
        db.update_image_field(iid, "score_general", 0.8)
    
    yield test_dir, image_ids, image_paths
    
    # Cleanup
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)

def test_selection_runner_graceful_stop(setup_db_and_images):
    test_dir, image_ids, image_paths = setup_db_and_images
    
    runner = selection_runner.SelectionRunner()
    job_id = db.create_job(test_dir)
    
    # Mock ClusteringEngine to be slow and check stop_event
    def mock_cluster(*args, **kwargs):
        stop_event = kwargs.get("stop_event")
        yield ("Starting Clustering...", 0, 100)
        # Sleep to allow time for stop() to be called
        for i in range(10):
            if stop_event and stop_event.is_set():
                yield ("Interrupted", i, 100)
                return
            time.sleep(0.1)
        yield ("Done", 100, 100)

    with patch.object(clustering.ClusteringEngine, "cluster_images", side_effect=mock_cluster):
        # Start the runner
        runner.start_batch(test_dir, job_id=job_id)
        
        # Wait for it to start running
        time.sleep(0.2)
        is_running, _, status, _, _ = runner.get_status()
        assert is_running is True
        
        # Verify images are marked as RUNNING
        for iid in image_ids:
            ph = db.get_image_phase_status(iid, PhaseCode.CULLING)
            assert ph["status"] == PhaseStatus.RUNNING.value
            
        # Stop the runner
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
            
        # Mark job as failed/suspended manually to simulate what happens at startup 
        # or if we want to test reconciliation.
        # Actually reconcile_stale_running_phases_for_jobs works for all RUNNING images 
        # that aren't in actively "running" jobs.
        # So we set job status to 'failed' (interrupted)
        db.update_job_status(job_id, "failed")
        
        # Now reconcile
        count = db.reconcile_stale_running_phases_for_jobs()
        assert count >= len(image_ids)
        
        # Verify images are now NOT_STARTED
        for iid in image_ids:
            ph = db.get_image_phase_status(iid, PhaseCode.CULLING)
            assert ph["status"] == PhaseStatus.NOT_STARTED.value
            
        print("Test passed successfully!")

if __name__ == "__main__":
    os.environ["PYTEST_CURRENT_TEST"] = "1"
    print("Starting manual test...")
    # Mocking the setup_db_and_images logic
    test_dir = os.path.abspath("temp_test_selection_stop_manual")
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    os.makedirs(test_dir)
    print(f"Created test dir: {test_dir}")
    
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
        
        # Import into DB
        print("Importing test images into DB...")
        folder_id = db.get_or_create_folder(test_dir)
        image_ids = []
        for p in image_paths:
            fname = os.path.basename(p)
            iid = db.register_image_for_import(p, fname, "jpg", folder_id)
            image_ids.append(iid)
            db.update_image_field(iid, "score_general", 0.8)
        print(f"Imported {len(image_ids)} images.")
        
        print("Running test_selection_runner_graceful_stop...")
        test_selection_runner_graceful_stop((test_dir, image_ids, image_paths))
    finally:
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)
