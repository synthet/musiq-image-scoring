#!/usr/bin/env python3
"""
Recalculate composite scores (general, technical, aesthetic), ratings, and labels
for all images in the Firebird DB using the v5.0 percentile normalization formulas.

Individual model scores (score_liqe, score_ava, score_spaq) are NOT changed.
Only derived columns are updated: score_general, score_technical, score_aesthetic,
rating, label, model_version.

Usage:
    python scripts/python/recalc_scores_v5.py [--dry-run] [--batch-size 500]
"""

import argparse
import os
import sys
import time
import logging

project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from modules import score_normalization as snorm
from modules import db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

NEW_VERSION = "5.0.0"


def fetch_all_scored_images(conn):
    """Fetch all images that have at least one model score."""
    c = conn.cursor()
    c.execute("""
        SELECT id, file_path, score_liqe, score_ava, score_spaq,
               score_general, score_technical, score_aesthetic,
               rating, label
        FROM images
        WHERE score_liqe IS NOT NULL
           OR score_ava IS NOT NULL
           OR score_spaq IS NOT NULL
    """)
    cols = [desc[0].lower() for desc in c.description]
    rows = []
    for row in c.fetchall():
        rows.append(dict(zip(cols, row)))
    return rows


def recalculate(rows, dry_run=False):
    """Compute new composites for each row. Returns list of update tuples."""
    updates = []
    changed = 0
    unchanged = 0
    stats = {"rating_dist": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}}

    for row in rows:
        scores = {}
        for model in ("liqe", "ava", "spaq"):
            val = row.get(f"score_{model}")
            if val is not None and isinstance(val, (int, float)) and val > 0:
                scores[model] = float(val)

        if not scores:
            continue

        result = snorm.compute_all(scores)
        new_gen = result["general"]
        new_tech = result["technical"]
        new_aes = result["aesthetic"]
        new_rating = result["rating"]
        new_label = result["label"]

        old_gen = row.get("score_general") or 0
        old_rating = row.get("rating") or 0
        old_label = row.get("label") or ""

        is_different = (
            abs(new_gen - old_gen) > 0.001
            or new_rating != old_rating
            or new_label != old_label
        )

        if is_different:
            changed += 1
        else:
            unchanged += 1

        stats["rating_dist"][new_rating] = stats["rating_dist"].get(new_rating, 0) + 1

        updates.append((
            new_gen, new_tech, new_aes,
            new_rating, new_label,
            NEW_VERSION,
            row["id"],
        ))

    log.info("Recalculation complete:")
    log.info("  Changed:   %d", changed)
    log.info("  Unchanged: %d", unchanged)
    log.info("  Rating distribution: %s", stats["rating_dist"])

    return updates


def apply_updates(conn, updates, batch_size=500):
    """Write updates to DB in batches."""
    c = conn.cursor()
    total = len(updates)
    log.info("Applying %d updates (batch_size=%d)...", total, batch_size)

    for i in range(0, total, batch_size):
        batch = updates[i : i + batch_size]
        for upd in batch:
            c.execute(
                """UPDATE images
                   SET score_general = ?, score_technical = ?, score_aesthetic = ?,
                       rating = ?, label = ?, model_version = ?
                   WHERE id = ?""",
                upd,
            )
        conn.commit()
        done = min(i + batch_size, total)
        log.info("  %d / %d (%.0f%%)", done, total, 100.0 * done / total)

    log.info("All updates applied.")


def main():
    parser = argparse.ArgumentParser(description="Recalculate scores using v5.0 percentile normalization")
    parser.add_argument("--dry-run", action="store_true", help="Compute but don't write to DB")
    parser.add_argument("--batch-size", type=int, default=500, help="DB update batch size")
    args = parser.parse_args()

    snorm.reload_config()

    log.info("=== Score Recalculation (v5.0 Percentile Normalization) ===")
    log.info("Anchors: %s", snorm.get_percentile_anchors())
    log.info("Weights: %s", snorm.get_composite_weights())
    log.info("Rating thresholds: %s", snorm.get_rating_thresholds())
    log.info("Label thresholds: %s", snorm.get_label_thresholds())

    log.info("%s", db.backup_database())

    conn = db.get_db()
    log.info("Fetching all scored images...")
    t0 = time.time()
    rows = fetch_all_scored_images(conn)
    log.info("Fetched %d images in %.1fs", len(rows), time.time() - t0)

    if not rows:
        log.info("No scored images found. Nothing to do.")
        conn.close()
        return

    t0 = time.time()
    updates = recalculate(rows, dry_run=args.dry_run)
    log.info("Computed %d updates in %.1fs", len(updates), time.time() - t0)

    if args.dry_run:
        log.info("DRY RUN - no changes written.")
    else:
        t0 = time.time()
        apply_updates(conn, updates, batch_size=args.batch_size)
        log.info("DB writes completed in %.1fs", time.time() - t0)

    conn.close()
    log.info("Done.")


if __name__ == "__main__":
    main()
