#!/usr/bin/env python3
"""
Recalculate composite scores (general, technical, aesthetic), ratings, and labels
from stored model scores using config.json percentile anchors and fusion weights.

Reads per-model scores from ``image_model_scores`` (legacy ``images.score_*``
columns removed on Postgres) plus TOPIQ from
image_model_scores. Does NOT re-run inference or change raw model scores.

Run in WSL with the app venv::

    source ~/.venvs/tf/bin/activate
    python scripts/analysis/recalc_composite_scores.py --dry-run
    python scripts/analysis/recalc_composite_scores.py --batch-size 500
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

project_root = str(Path(__file__).resolve().parents[2])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from modules import db  # noqa: E402
from modules import score_normalization as snorm  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

NEW_VERSION = "5.1.0"

LEGACY_MODELS = ("liqe", "ava", "spaq")
# Models read from image_model_scores (production rows only). `arniqa` joined the
# fusion in May 2026 after its full-corpus shadow backfill was promoted.
IMS_MODELS = ("topiq", "arniqa")
ALL_MODELS = LEGACY_MODELS + IMS_MODELS


def _wsl_path(path: str) -> str:
    p = path.replace("\\", "/")
    if len(p) >= 3 and p[1] == ":" and p[0].isalpha():
        return f"/mnt/{p[0].lower()}/{p[2:].lstrip('/')}"
    return p


def _folder_filter(folder_path: Optional[str], alias: str = "f") -> Tuple[str, List[Any]]:
    if not folder_path:
        return "", []
    target = _wsl_path(folder_path)
    return (
        f"AND ({alias}.path = ? OR {alias}.path LIKE ? OR {alias}.path LIKE ?)",
        [target, target + "/%", target + "\\%"],
    )


def _row_to_dict(row, cols: List[str]) -> dict:
    if isinstance(row, dict):
        return {str(k).lower(): v for k, v in row.items()}
    if hasattr(row, "keys"):
        return {str(k).lower(): row.get(k) for k in row.keys()}
    return dict(zip(cols, row))


def _rows_to_dicts(cursor) -> List[dict]:
    rows = cursor.fetchall()
    if not rows:
        return []
    cols = [desc[0].lower() for desc in cursor.description]
    return [_row_to_dict(row, cols) for row in rows]


def row_to_scores(row: dict) -> Dict[str, float]:
    """Build {model: normalized_score} from a DB row dict."""
    scores: Dict[str, float] = {}
    for model in ALL_MODELS:
        val = row.get(f"score_{model}")
        if val is None:
            val = row.get(model)
        if val is not None and isinstance(val, (int, float)) and val > 0:
            scores[model] = float(val)
    return scores


def fetch_scored_images(conn, folder_path: Optional[str] = None) -> List[dict]:
    """Fetch images with any per-model score in image_model_scores (or legacy columns on Firebird)."""
    fsql, fparams = _folder_filter(folder_path)
    model_names_for_exists = "', '".join(ALL_MODELS)
    if db._get_db_engine() == "postgres":
        where_scores = (
            "EXISTS (SELECT 1 FROM image_model_scores ims "
            f"WHERE ims.image_id = i.id AND ims.model_name IN ('{model_names_for_exists}') "
            "AND ims.status = 'success' AND ims.is_shadow = FALSE "
            "AND COALESCE(ims.normalized, ims.raw_score) IS NOT NULL)"
        )
    else:
        where_scores = (
            "(i.score_liqe IS NOT NULL OR i.score_ava IS NOT NULL OR i.score_spaq IS NOT NULL)"
        )
    query = f"""
        SELECT i.id, i.file_path,
               i.score_general, i.score_technical, i.score_aesthetic,
               i.rating, i.label
        FROM images i
        LEFT JOIN folders f ON f.id = i.folder_id
        WHERE {where_scores}
        {fsql}
    """
    c = conn.cursor()
    c.execute(query, fparams)
    rows = _rows_to_dicts(c)
    if not rows:
        return rows

    ids = [r["id"] for r in rows]
    # model -> {image_id: normalized} from image_model_scores (all fusion models on Postgres)
    models_to_load = ALL_MODELS if db._get_db_engine() == "postgres" else IMS_MODELS
    ims_by_model: Dict[str, Dict[int, float]] = {m: {} for m in models_to_load}
    batch_size = 5000
    model_ph = ",".join(["?"] * len(models_to_load))
    for start in range(0, len(ids), batch_size):
        batch = ids[start : start + batch_size]
        ph = ",".join(["?"] * len(batch))
        ims_query = f"""
            SELECT ims.image_id, ims.model_name,
                   COALESCE(ims.normalized, ims.raw_score) AS score_val
            FROM image_model_scores ims
            WHERE ims.image_id IN ({ph})
              AND ims.model_name IN ({model_ph})
              AND ims.status = 'success'
              AND ims.is_shadow = FALSE
              AND COALESCE(ims.normalized, ims.raw_score) IS NOT NULL
        """
        c.execute(ims_query, list(batch) + list(models_to_load))
        for ims_row in _rows_to_dicts(c):
            m = str(ims_row["model_name"]).lower()
            val = ims_row.get("score_val")
            if m in ims_by_model and val is not None:
                ims_by_model[m][ims_row["image_id"]] = float(val)

    for row in rows:
        rid = row["id"]
        for m in models_to_load:
            if rid in ims_by_model[m]:
                row[m] = ims_by_model[m][rid]
                row[f"score_{m}"] = ims_by_model[m][rid]

    return rows


def recalculate(rows: List[dict]) -> Tuple[List[tuple], dict]:
    """Compute new composites for each row. Returns (update tuples, stats dict)."""
    updates: List[tuple] = []
    changed = 0
    unchanged = 0
    old_rating_dist: Dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    new_rating_dist: Dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    deltas: List[tuple] = []

    for row in rows:
        scores = row_to_scores(row)
        if not scores:
            continue

        result = snorm.compute_all(scores)
        new_gen = result["general"]
        new_tech = result["technical"]
        new_aes = result["aesthetic"]
        new_rating = result["rating"]
        new_label = result["label"]

        old_gen = row.get("score_general") or 0.0
        old_tech = row.get("score_technical") or 0.0
        old_aes = row.get("score_aesthetic") or 0.0
        old_rating = row.get("rating") or 0
        old_label = row.get("label") or ""

        if old_rating in old_rating_dist:
            old_rating_dist[old_rating] += 1
        new_rating_dist[new_rating] = new_rating_dist.get(new_rating, 0) + 1

        is_different = (
            abs(new_gen - float(old_gen)) > 0.001
            or abs(new_tech - float(old_tech)) > 0.001
            or abs(new_aes - float(old_aes)) > 0.001
            or new_rating != old_rating
            or new_label != old_label
        )

        if is_different:
            changed += 1
            deltas.append((abs(new_gen - float(old_gen)), row.get("file_path", ""), old_gen, new_gen))
        else:
            unchanged += 1

        updates.append((
            new_gen, new_tech, new_aes,
            new_rating, new_label,
            NEW_VERSION,
            row["id"],
        ))

    deltas.sort(reverse=True)
    stats = {
        "changed": changed,
        "unchanged": unchanged,
        "old_rating_dist": old_rating_dist,
        "new_rating_dist": new_rating_dist,
        "top_deltas": deltas[:10],
    }
    return updates, stats


def apply_updates(conn, updates: List[tuple], batch_size: int = 500) -> None:
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Recalculate composite scores using config fusion weights"
    )
    parser.add_argument("--dry-run", action="store_true", help="Compute but don't write to DB")
    parser.add_argument("--batch-size", type=int, default=500, help="DB update batch size")
    parser.add_argument("--folder-path", type=str, default=None, help="Limit to folder path")
    args = parser.parse_args()

    snorm.reload_config()

    log.info("=== Composite Score Recalculation (v%s) ===", NEW_VERSION)
    log.info("Anchors: %s", snorm.get_percentile_anchors())
    log.info("Weights: %s", snorm.get_composite_weights())
    log.info("Rating thresholds: %s", snorm.get_rating_thresholds())
    log.info("Label thresholds: %s", snorm.get_label_thresholds())

    if not args.dry_run:
        log.info("%s", db.backup_database())

    conn = db.get_db()
    log.info("Fetching scored images...")
    t0 = time.time()
    rows = fetch_scored_images(conn, folder_path=args.folder_path)
    log.info("Fetched %d images in %.1fs", len(rows), time.time() - t0)

    if not rows:
        log.info("No scored images found. Nothing to do.")
        conn.close()
        return

    for m in IMS_MODELS:
        cnt = sum(1 for r in rows if r.get(m) is not None)
        log.info("Images with %s score: %d / %d", m.upper(), cnt, len(rows))

    t0 = time.time()
    updates, stats = recalculate(rows)
    log.info("Computed %d updates in %.1fs", len(updates), time.time() - t0)
    log.info("  Changed:   %d", stats["changed"])
    log.info("  Unchanged: %d", stats["unchanged"])
    log.info("  Old rating distribution: %s", stats["old_rating_dist"])
    log.info("  New rating distribution: %s", stats["new_rating_dist"])
    if stats["top_deltas"]:
        log.info("  Top |Δgeneral| samples:")
        for delta, path, old, new in stats["top_deltas"][:5]:
            log.info("    %.4f  %s  %.4f -> %.4f", delta, path, old, new)

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
