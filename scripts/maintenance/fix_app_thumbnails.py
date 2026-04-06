import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

import logging
from modules import db, thumbnails

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def fix_app_thumbnails():
    logger.info("Starting /app/thumbnails repair...")
    
    # Initialize DB connection
    db.init_db()
    
    conn = db.get_connector()
    # Get ALL images with thumbnails and let the python logic decide if they need repair
    rows = conn.query("SELECT id, thumbnail_path, thumbnail_path_win FROM images WHERE (thumbnail_path IS NOT NULL AND thumbnail_path != '') OR (thumbnail_path_win IS NOT NULL AND thumbnail_path_win != '')")
    
    to_repair = []
    for row in rows:
        if thumbnails.thumbnail_pair_needs_repair(row['thumbnail_path'], row['thumbnail_path_win']):
            to_repair.append(row)
            
    total = len(to_repair)
    fixed = 0
    failed = 0
    
    logger.info(f"Found {total} images needing repair.")
    
    for i, row in enumerate(to_repair):
        image_id = row['id']
        tp = row['thumbnail_path']
        tw = row['thumbnail_path_win']
        
        try:
            # Re-normalize using the updated functions
            success = db.update_image_thumbnail_paths(image_id, tp, tw)
            if success:
                fixed += 1
            else:
                failed += 1
        except Exception as e:
            logger.error(f"Error fixing {image_id}: {e}")
            failed += 1
            
        if (i+1) % 500 == 0:
            logger.info(f"Processed {i+1}/{total}...")
            
    logger.info(f"Repair complete. Total: {total}, Fixed: {fixed}, Failed: {failed}")

if __name__ == "__main__":
    fix_app_thumbnails()
