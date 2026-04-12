import sys
import os
import argparse
import logging
from pathlib import Path

# Add project root to path to import modules
project_root = str(Path(__file__).resolve().parents[2])
if project_root not in sys.path:
    sys.path.append(project_root)

from modules import db

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def recalc_scores(dry_run=False):
    """
    Recalculate score_general and rating for all images in DB using new formula.
    New Formula: 0.50 * LIQE + 0.30 * AVA + 0.20 * SPAQ
    """
    conn = db.get_db()
    
    if not dry_run:
        backup_msg = db.backup_database()
        logger.info("%s", backup_msg)
        if backup_msg.lower().startswith("failed to"):
            choice = input(f"{backup_msg} Continue with recalculation? (y/N): ")
            if choice.lower() != "y":
                logger.info("Aborting recalculation.")
                return

    c = conn.cursor()
    
    try:
        # Get all images with valid component scores
        # We need LIQE, AVA, SPAQ. KonIQ and PaQ are ignored.
        query = """
        SELECT id, file_path, score_liqe, score_ava, score_spaq, score_general, rating 
        FROM images 
        WHERE score_liqe IS NOT NULL AND score_ava IS NOT NULL AND score_spaq IS NOT NULL
        """
        
        c.execute(query)
        rows = c.fetchall()
        
        logger.info(f"Found {len(rows)} images with component scores.")
        
        updated_count = 0
        
        for row in rows:
            img_id = row[0]
            file_path = row[1]
            liqe = row[2]
            ava = row[3]
            spaq = row[4]
            old_score = row[5]
            old_rating = row[6]
            
            # Helper: Normalize if value appears to be Raw (> 1.0)
            # Assumption: Normalized scores are <= 1.0. Raw scores for these models are typically > 1.0
            # LIQE (1-5), AVA (1-10), SPAQ (0-100)
            
            def norm_liqe(v):
                if v > 1.01: return max(0.0, min(1.0, (v - 1.0) / 4.0)) # Raw 1-5
                return max(0.0, min(1.0, v)) # Already norm
                
            def norm_ava(v):
                if v > 1.01: return max(0.0, min(1.0, (v - 1.0) / 9.0)) # Raw 1-10
                return max(0.0, min(1.0, v))
                
            def norm_spaq(v):
                if v > 1.01: return max(0.0, min(1.0, v / 100.0)) # Raw 0-100
                return max(0.0, min(1.0, v))

            n_liqe = norm_liqe(liqe)
            n_ava = norm_ava(ava)
            n_spaq = norm_spaq(spaq)
            
            # Calculate Components
            # Technical = LIQE
            val_technical = n_liqe
            
            # Aesthetic = 0.6 * AVA + 0.4 * SPAQ
            val_aesthetic = (0.60 * n_ava) + (0.40 * n_spaq)
            
            # General = 0.5 * Technical + 0.5 * Aesthetic
            # (matches: 0.5*LIQE + 0.3*AVA + 0.2*SPAQ)
            val_general = (0.50 * val_technical) + (0.50 * val_aesthetic)
            
            # Calculate Rating
            new_rating = 1
            if val_general >= 0.85: new_rating = 5
            elif val_general >= 0.70: new_rating = 4
            elif val_general >= 0.55: new_rating = 3
            elif val_general >= 0.40: new_rating = 2
            
            # Calculate Label
            # Red=Reject, Purple=Aesthetic beats tech, Blue=Portfolio, Green=Reference, Yellow=Maybe
            new_label = "Yellow"
            if val_technical < 0.40: new_label = "Red"
            elif val_technical < 0.65 and val_aesthetic > val_technical and val_aesthetic > 0.48: new_label = "Purple"
            elif val_aesthetic > 0.70 and val_technical > 0.70: new_label = "Blue"
            elif val_technical > 0.65: new_label = "Green"
            
            # Update Check
            # We enforce update if any component suggests stale data
            # To be safe, we just update everything if meaningful change or dry run
            
            if not dry_run:
                # Update all score columns
                c.execute("""
                    UPDATE images 
                    SET score_general = ?, 
                        score_technical = ?,
                        score_aesthetic = ?,
                        rating = ?, 
                        label = ?,
                        model_version = ? 
                    WHERE id = ?
                """, (val_general, val_technical, val_aesthetic, new_rating, new_label, "3.0.0", img_id))
                updated_count += 1
            else:
                if updated_count < 10: # Log first 10 for review
                    logger.info(f"Dry Run ID {img_id}: Gen {old_score:.3f}->{val_general:.3f} | Tech {val_technical:.3f} | Aes {val_aesthetic:.3f}")
                updated_count += 1

                    
        if not dry_run:
            conn.commit()
            logger.info(f"Updated {updated_count} images.")
        else:
            logger.info(f"Dry Run: Would update {updated_count} images.")
            
    except Exception as e:
        logger.error(f"Error recalculating scores: {e}")
        if not dry_run:
            conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Recalculate scores in DB')
    parser.add_argument('--dry-run', action='store_true', help='Do not commit changes')
    args = parser.parse_args()
    
    recalc_scores(args.dry_run)
