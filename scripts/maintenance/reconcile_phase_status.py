"""
Reconcile Image Phase Status

This maintenance script audits the image_phase_status table against the 
ground-truth data stored in the main images table.
It identifies cases of "status drift" where the recorded status is 
e.g., 'skipped' or 'not_started', but the underlying data is actually 
present, and corrects the status to 'done'. 

Usage:
  python scripts/maintenance/reconcile_phase_status.py [--dry-run]
"""

import sys
import os
import argparse
import logging
from typing import Dict, Any

# Ensure project root is in PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from modules import db
from modules.db_legacy import get_connector, set_image_phase_status

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def reconcile(dry_run: bool = False):
    db = get_connector()
    
    # Process phases
    if db._get_db_engine() == "postgres":
        indexing_present = f"({db._postgres_has_default_embedding_sql('i')})"
    else:
        indexing_present = "i.image_embedding IS NOT NULL"

    phases_to_check = {
        'indexing': indexing_present,
        'metadata': "(i.rating IS NOT NULL AND i.label IS NOT NULL)",
        'scoring': "(i.score_general IS NOT NULL AND i.score_general > 0)",
        'keywords': "(i.keywords IS NOT NULL AND i.keywords != '')"
    }

    total_drift_fixed = 0

    for phase_code, data_condition in phases_to_check.items():
        logger.info(f"Checking drift for phase: {phase_code}")
        
        # Find images where data exists but status is not 'done'
        # Or status is 'done' but data does NOT exist
        
        # Drift 1: Data exists, but status is not done (e.g. skipped, not_started, missing)
        query_fix_to_done = f"""
            SELECT i.id, ips.status
            FROM images i
            LEFT JOIN pipeline_phases pp ON pp.code = ?
            LEFT JOIN image_phase_status ips ON ips.image_id = i.id AND ips.phase_id = pp.id
            WHERE {data_condition} 
              AND (ips.status IS NULL OR LOWER(TRIM(ips.status)) != 'done')
        """
        
        rows_to_done = db.query(query_fix_to_done, (phase_code,))
        if rows_to_done:
            logger.info(f"  Found {len(rows_to_done)} images with {phase_code} data but status is not 'done'.")
            if not dry_run:
                for row in rows_to_done:
                    set_image_phase_status(row['id'], phase_code, 'done')
                logger.info(f"  -> Fixed {len(rows_to_done)} rows to 'done'.")
            total_drift_fixed += len(rows_to_done)

        # Drift 2: Data is missing, but status is 'done'
        query_fix_to_not_started = f"""
            SELECT i.id, ips.status
            FROM images i
            JOIN pipeline_phases pp ON pp.code = ?
            JOIN image_phase_status ips ON ips.image_id = i.id AND ips.phase_id = pp.id
            WHERE NOT ({data_condition})
              AND LOWER(TRIM(ips.status)) = 'done'
        """
        
        rows_to_not_started = db.query(query_fix_to_not_started, (phase_code,))
        if rows_to_not_started:
            logger.info(f"  Found {len(rows_to_not_started)} images with status 'done' but missing {phase_code} data.")
            if not dry_run:
                for row in rows_to_not_started:
                    set_image_phase_status(row['id'], phase_code, 'not_started')
                logger.info(f"  -> Fixed {len(rows_to_not_started)} rows to 'not_started'.")
            total_drift_fixed += len(rows_to_not_started)

    if dry_run:
        logger.info(f"DRY RUN COMPLETE. {total_drift_fixed} total drift issues identified.")
    else:
        logger.info(f"RECONCILIATION COMPLETE. {total_drift_fixed} total drift issues fixed.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Reconcile image phase status with underlying data.")
    parser.add_argument('--dry-run', action='store_true', help="Print what would be changed without actually writing to the DB")
    args = parser.parse_args()
    
    reconcile(dry_run=args.dry_run)
