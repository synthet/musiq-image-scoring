
import os
import sys
import logging
from unittest.mock import MagicMock

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import classes to test
from modules.pipeline import PrepWorker

def test_prepworker_audit():
    print("--- Testing PrepWorker Audit Safeguard (Logic Simulation) ---")
    
    # Configure logging to capture warnings
    logger = logging.getLogger("modules.pipeline")
    logger.setLevel(logging.WARNING)
    # Stream handler for output
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
    logger.addHandler(sh)
    
    # 1. Setup mock job with manual metadata and skip_existing=False
    class MockJob:
        def __init__(self):
            self.image_id = 99999
            self.image_path = "/test/path/img.jpg"
            self.skip_existing = False
            self.external_scores = {}

    job = MockJob()
    
    # Mock row with manual metadata (from DB)
    path_record = {
        "id": 99999,
        "rating": 5,
        "label": "Red",
        "cull_decision": "keep"
    }
    
    print(f"Simulating processing for image {job.image_id} with skip_existing={job.skip_existing}...")
    
    # The logic we added to PrepWorker.process:
    if not job.skip_existing:
        rating = path_record.get('rating')
        label = path_record.get('label')
        cull = path_record.get('cull_decision')
        if (rating and rating > 0) or (label and label.strip()) or (cull and cull.strip()):
            logger.warning(
                f"[AUDIT] Image {job.image_id} has manual metadata "
                f"(rating={rating}, label='{label}', cull='{cull}') "
                f"which will be OVERWRITTEN/RECALCULATED because 'Process ALL' is active."
            )

    print("--- Test Complete ---")

    print("--- Test Complete ---")

if __name__ == "__main__":
    test_prepworker_audit()
