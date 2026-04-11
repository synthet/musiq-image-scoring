import os
import sys
import logging

# Set up logging to stdout
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add project root to path
sys.path.append(os.getcwd())

from modules import db, utils, exif_extractor

def run_cleanup():
    logger.info("Starting cleanup script...")
    
    # 1. Prune Missing Files
    logger.info("Checking for orphaned database records...")
    rows = db.get_connector().query("SELECT id, file_path FROM images")
    to_prune = []
    
    for row in rows:
        # Robust handling for RowWrapper/dict/tuple
        if hasattr(row, 'get'):
            mid = row.get("id")
            mpath = row.get("file_path")
        elif isinstance(row, (list, tuple)) and len(row) >= 2:
            mid, mpath = row[0], row[1]
        else:
            mid = row["id"]
            mpath = row["file_path"]
            
        if not mpath:
            to_prune.append((mid, mpath))
            continue
            
        resolved = utils.resolve_file_path(mpath, mid)
        if not resolved:
            to_prune.append((mid, mpath))
            
    logger.info(f"Found {len(to_prune)} orphaned records.")
    
    for mid, mpath in to_prune:
        logger.info(f"Pruning: ID={mid}, Path={mpath}")
        if mpath:
            db.delete_image(mpath)
        else:
            # Handle null paths directly
            db.get_connector().execute("DELETE FROM images WHERE id = %s", (mid,))
            
    logger.info(f"Pruned {len(to_prune)} records.")
    
    # 2. Backfill EXIF Dates
    logger.info("Starting EXIF date backfill...")
    stats = exif_extractor.backfill_exif_dates(limit=None)
    logger.info(f"Backfill complete: {stats}")
    
    # 3. Final Health Check
    from modules import mcp_server
    health = mcp_server.get_error_summary()
    logger.info(f"Final health summary: {health}")

if __name__ == "__main__":
    try:
        run_cleanup()
        logger.info("Cleanup script finished successfully.")
    except Exception as e:
        logger.error(f"Cleanup script failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
