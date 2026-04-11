import os
import sys
import logging
import argparse

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from modules import db, utils
from modules.pipeline_orchestrator import PipelineOrchestrator
from modules.indexing_runner import IndexingRunner
from modules.metadata_runner import MetadataRunner
from modules.scoring import ScoringRunner
from modules.tagging import TaggingRunner
from modules.selection_runner import SelectionRunner

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def heal_all_ghost_folders(dry_run=True, target_folder=None):
    """Identify folders with significant data gaps and trigger processing."""
    logger.info("Starting Pipeline Data Health Check...")
    
    # 1. Get all folders
    if target_folder:
        folders = db.get_connector().query("SELECT id, path FROM folders WHERE path = ?", (target_folder,))
    else:
        folders = db.get_connector().query("SELECT id, path FROM folders ORDER BY id DESC")
    
    ghosts = []
    for f in folders:
        fid = f["id"]
        path = f["path"]
        
        # Fast check: fulfillment stats (subtree under path, same as phase rollups)
        stats = db.get_folder_fulfillment_stats_for_path(path)
        total = stats["total"]
        if total == 0:
            continue
            
        # If folder has images but 0% scores or thumbnails, it's a ghost
        is_ghost = False
        reason = []
        
        if stats["scored"] == 0 and total > 0:
            is_ghost = True
            reason.append("0% scores")
        elif stats["scored"] < (total * 0.5):
            is_ghost = True
            reason.append(f"Low scores ({stats['scored']}/{total})")
            
        if stats["thumbnails"] == 0 and total > 0:
            is_ghost = True
            reason.append("0% thumbnails")
            
        if is_ghost:
            logger.warning("GHOST FOLDER FOUND: %s (ID: %s) - %s", path, fid, ", ".join(reason))
            ghosts.append(path)

    if not ghosts:
        logger.info("No ghost folders found. System is healthy.")
        return

    logger.info("Found %s ghost folders to heal.", len(ghosts))
    
    if dry_run:
        logger.info("DRY RUN: Would trigger pipeline for %s folders.", len(ghosts))
        for g in ghosts:
            print(f"  - {g}")
        return

    # 2. Initialize orchestrator (singleton-ish)
    orchestrator = PipelineOrchestrator(
        indexing_runner=IndexingRunner(),
        metadata_runner=MetadataRunner(),
        scoring_runner=ScoringRunner(),
        tagging_runner=TaggingRunner(),
        selection_runner=SelectionRunner()
    )

    import time
    logger.info("Starting healing process...")
    for path in ghosts:
        local_path = utils.convert_path_to_local(path)
        logger.info("Healing: %s (local: %s)", path, local_path)
        
        # Trigger it
        job_id = orchestrator.start(local_path, force_rerun=False)
        if job_id:
            logger.info("  Triggered Job ID: %s. Waiting for completion...", job_id)
            # Poll for completion
            while True:
                job = db.get_job(job_id)
                status = job.get("status") if job else "unknown"
                if status in ("completed", "failed", "stopped", "paused"):
                    logger.info("  Job %s finished with status: %s", job_id, status)
                    break
                time.sleep(10) # check every 10 seconds
        else:
            logger.info("  Already running or no work identified (check logs).")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Heal pipeline data discrepancies.")
    parser.add_argument("--run", action="store_true", help="Actually trigger the healing jobs (default is dry run).")
    parser.add_argument("--folder", type=str, help="Specifically heal only this folder path.")
    args = parser.parse_args()
    
    db.init_db()
    heal_all_ghost_folders(dry_run=not args.run, target_folder=args.folder)
