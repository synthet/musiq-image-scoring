#!/usr/bin/env python3
"""
Backfill IPTC accessibility metadata (Alt Text, Extended Description) into IMAGE_XMP
and XMP sidecars using CLIP prompt ranking.

Run in WSL with ~/.venvs/tf (same env as the webapp).
"""
import argparse
import logging
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from modules import db, utils
from modules import clip_accessibility
from modules.tagging import TaggingRunner

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Generate and cache CLIP accessibility metadata (alt_text, extended_description)"
    )
    parser.add_argument("--folder", type=str, default=None, help="Restrict to images in this folder")
    parser.add_argument("--limit", type=int, default=None, help="Max images to process")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Re-generate even when image_xmp already has alt_text and extended_description",
    )
    parser.add_argument("--dry-run", action="store_true", help="List targets only; do not write")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing accessibility fields")
    args = parser.parse_args()

    db.init_db()
    conn = db.get_db()
    c = conn.cursor()

    query = "SELECT i.id, i.file_path, i.keywords FROM images i"
    where_parts = []
    params = []
    if not args.all:
        where_parts.append(
            "(NOT EXISTS (SELECT 1 FROM image_xmp x WHERE x.image_id = i.id "
            "AND x.alt_text IS NOT NULL AND TRIM(x.alt_text) <> '' "
            "AND x.extended_description IS NOT NULL AND TRIM(x.extended_description) <> ''))"
        )
    if args.folder:
        folder_path = args.folder.replace("\\", "/")
        if __import__("re").match(r"^[a-zA-Z]:", folder_path):
            folder_path = utils.convert_path_to_wsl(folder_path)
        folder_id = db.get_or_create_folder(folder_path)
        if not folder_id:
            logger.error("Folder not found: %s", folder_path)
            sys.exit(1)
        where_parts.append("i.folder_id = ?")
        params.append(folder_id)
    if where_parts:
        query += " WHERE " + " AND ".join(where_parts)
    query += " ORDER BY i.id"

    c.execute(query, tuple(params))
    rows = c.fetchall()
    conn.close()

    if args.limit:
        rows = rows[: args.limit]

    logger.info("Found %d images to process", len(rows))
    if args.dry_run:
        for row in rows[:10]:
            fp = row["file_path"] if hasattr(row, "keys") else row[1]
            logger.info("  %s", fp)
        if len(rows) > 10:
            logger.info("  ... and %d more", len(rows) - 10)
        return

    runner = TaggingRunner()
    if runner.scorer is None:
        from modules.tagging import KeywordScorer

        runner.scorer = KeywordScorer()
        runner.scorer.load_model()
    ok = 0
    skip = 0
    fail = 0

    for i, row in enumerate(rows):
        image_id = row["id"] if hasattr(row, "keys") else row[0]
        file_path = row["file_path"] if hasattr(row, "keys") else row[1]
        keywords_raw = row["keywords"] if hasattr(row, "keys") else (row[2] if len(row) > 2 else "")
        if not file_path:
            continue

        kw_list = [k.strip() for k in (keywords_raw or "").split(",") if k.strip()]
        acc = clip_accessibility.describe_from_clip(
            image_id=image_id,
            image_path=file_path,
            keywords=kw_list,
            scorer=runner.scorer,
            overwrite=args.overwrite or args.all,
        )
        if acc.get("error"):
            fail += 1
            logger.warning("image_id=%s: %s", image_id, acc.get("error"))
            continue
        if acc.get("skipped"):
            skip += 1
            continue

        alt_text = (acc.get("alt_text") or "").strip()
        extended = (acc.get("extended_description") or "").strip()
        if not alt_text and not extended:
            skip += 1
            continue

        db.upsert_image_xmp(image_id, {
            "alt_text": alt_text or None,
            "extended_description": extended or None,
        })
        runner.write_metadata(
            file_path,
            kw_list,
            alt_text=alt_text,
            extended_description=extended,
        )
        ok += 1
        if (i + 1) % 25 == 0:
            logger.info("Progress: %d/%d (ok=%d skip=%d fail=%d)", i + 1, len(rows), ok, skip, fail)

    logger.info("Backfill complete. ok=%d skip=%d fail=%d", ok, skip, fail)


if __name__ == "__main__":
    main()
