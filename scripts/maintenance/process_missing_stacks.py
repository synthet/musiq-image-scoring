import sys
import os
import logging
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from modules import db, clustering

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(PROJECT_ROOT, 'process_missing_stacks.log'), encoding='utf-8')
    ]
)

def main():
    report_path = os.path.join(PROJECT_ROOT, "missing_stacks_report.md")
    
    if not os.path.exists(report_path):
        logging.error(f"Report not found: {report_path}")
        return

    logging.info("Initializing Database...")
    try:
        db.init_db()
    except Exception as e:
        logging.error(f"Failed to init DB: {e}")
        return

    logging.info("Initializing Clustering Engine...")
    engine = clustering.ClusteringEngine()

    folders_to_process = []
    current_category = None
    
    logging.info(f"Reading report: {report_path}")
    
    photo_root = r"D:\Photos"
    
    with open(report_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            if line.startswith("## "):
                # Extract category name, removing '## ' 
                current_category = line[3:].strip()
                continue
                
            if line.startswith("- `") and current_category:
                # Extract path content: - `2007-04-12` -> 2007-04-12
                # Remove '- `' at start and '`' at end if present
                content = line[3:].strip().rstrip('`')
                
                # Construct full path
                full_path = os.path.join(photo_root, current_category, content)
                folders_to_process.append(full_path)

    logging.info(f"Found {len(folders_to_process)} folders to process.")
    
    processed_count = 0
    errors = 0
    
    for i, folder in enumerate(folders_to_process):
        logging.info(f"[{i+1}/{len(folders_to_process)}] Processing: {folder}")
        
        if not os.path.exists(folder):
            logging.warning(f"Folder not found: {folder}")
            continue
            
        try:
            # force_rescan=False because we know these are missing stacks? 
            # Request implies processing missing stacks. If check found 0 stacks, then force_rescan=True is safer to clear any partial state? 
            # Or just run it. The user report says "NO stacks recorded".
            # So force_rescan shouldn't be needed unless there's bad data.
            # But let's be safe and use force_rescan=True to ensure clean start for that folder.
            
            # Use the generator
            for status in engine.cluster_images(target_folder=folder, force_rescan=True):
                # We can log status updates sparingly if needed
                # For now just let it run
                pass
                
            logging.info(f"Completed: {folder}")
            processed_count += 1
        except Exception as e:
            logging.error(f"Error processing {folder}: {e}")
            errors += 1

    logging.info(f"Job Initial Complete. Processed: {processed_count}, Errors: {errors}")

if __name__ == "__main__":
    main()
