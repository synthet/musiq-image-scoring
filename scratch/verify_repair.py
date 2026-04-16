
import os
import sys
import logging

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from modules import db, config

# Configure logging to see what's happening
logging.basicConfig(level=logging.INFO)

TARGET_IMAGE_ID = 67336
TARGET_PATH = "/mnt/d/Photos/Z6ii/28-400mm/2026/2026-04-09/DSC_1065.NEF"

def break_image():
    print(f"--- Breaking image {TARGET_IMAGE_ID} ---")
    with db.connection() as conn:
        c = conn.cursor()
        
        # 1. Wipe scoring data
        c.execute("""
            UPDATE images 
            SET score_general = NULL, 
                score_technical = NULL, 
                score_aesthetic = NULL,
                score_spaq = NULL,
                score_koniq = NULL,
                score_liqe = NULL
            WHERE id = ?
        """, (TARGET_IMAGE_ID,))
        
        # 2. Ensure it's marked as 'done' or 'skipped' in image_phase_status
        # (It already is, but let's be sure it's 'done' for scoring)
        # First find the phase_id for 'scoring'
        c.execute("SELECT id FROM pipeline_phases WHERE code = 'scoring'")
        phase_id = c.fetchone()[0]
        
        c.execute("""
            UPDATE image_phase_status 
            SET status = 'done', 
                skip_reason = NULL,
                executor_version = '5.0.0'
            WHERE image_id = ? AND phase_id = ?
        """, (TARGET_IMAGE_ID, phase_id))
        
        conn.commit()
    print("Image corrupted: scores=NULL, status=done")

def verify_repair_plan():
    print("--- Building validation repair plan ---")
    folder_path = os.path.dirname(TARGET_PATH)
    # Signature: scope_paths, stage_codes=None, dry_run=True
    plan = db.build_validation_repair_plan(
        [folder_path],
        ["scoring"],
        True
    )
    
    stage_queues = plan.get("stage_queues", {})
    scoring_ids = stage_queues.get("scoring", [])
    if TARGET_IMAGE_ID in scoring_ids:
        print(f"SUCCESS: Image {TARGET_IMAGE_ID} found in scoring repair plan!")
    else:
        print(f"FAILURE: Image {TARGET_IMAGE_ID} NOT found in scoring repair plan.")
        print("Plan queues:", stage_queues)

if __name__ == "__main__":
    break_image()
    verify_repair_plan()
