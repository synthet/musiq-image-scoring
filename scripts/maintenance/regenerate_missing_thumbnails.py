#!/usr/bin/env python3
"""
Regenerate thumbnails for images whose DB thumbnail paths do not resolve to a
real file (or optionally force regeneration for a folder / single file).

Uses the same generation pipeline as the WebUI (modules.thumbnails.generate_thumbnail)
and persists paths via db.update_image_thumbnail_paths (thumbnail_path + thumbnail_path_win).

Usage (WSL, same venv as webapp — see AGENTS.md):
  python scripts/maintenance/regenerate_missing_thumbnails.py \\
      --under "D:\\Photos\\Z8\\105mm\\2026\\2026-04-04" --dry-run

  python scripts/maintenance/regenerate_missing_thumbnails.py \\
      --file "D:\\Photos\\Z8\\105mm\\2026\\2026-04-04\\DSC_4935.NEF"

  # Whole library (careful — large):
  python scripts/maintenance/regenerate_missing_thumbnails.py --all --limit 500

Bounded global batches are also available from the Web UI (Runs → Tools):
POST /api/maintenance/regenerate-thumbnails
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from modules import db, thumbnails  # noqa: E402
from modules.thumbnail_maintenance import (  # noqa: E402
    filesystem_path_for_image,
    folder_like_patterns,
    resolved_thumb_ok,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _thumb_fs_candidates(file_path: str) -> list[str]:
    """Canonical thumbnail locations (nested layout + legacy flat), same hash as modules.thumbnails."""
    h = hashlib.md5(str(file_path).encode("utf-8")).hexdigest()
    root = thumbnails.canonical_thumbnails_dir()
    return [
        os.path.join(root, h[:2], f"{h}.jpg"),
        os.path.join(root, f"{h}.jpg"),
    ]


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Regenerate missing image thumbnails and update the DB.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument(
        "--under",
        metavar="FOLDER",
        help="Only images whose file_path is under this folder (prefix match).",
    )
    g.add_argument("--file", metavar="PATH", help="Single image file_path as stored in the database.")
    g.add_argument("--all", action="store_true", help="Scan all images (use with care on large DBs).")

    ap.add_argument("--dry-run", action="store_true", help="Log actions only; do not write files or DB.")
    ap.add_argument(
        "--force",
        action="store_true",
        help="Remove existing canonical thumbnail files first, then regenerate (even if DB resolves).",
    )
    ap.add_argument(
        "--regenerate-all-in-scope",
        action="store_true",
        help="Also process rows whose thumbnail already resolves (still skips missing originals).",
    )
    ap.add_argument("--limit", type=int, default=0, help="Max rows to process (0 = no limit).")
    ap.add_argument("-q", "--quiet", action="store_true", help="Warnings and errors only.")
    return ap.parse_args()


def main() -> int:
    args = _parse_args()
    if args.quiet:
        logger.setLevel(logging.WARNING)

    db.init_db()
    conn = db.get_db()
    cur = conn.cursor()

    params: list[object] = []
    where_parts: list[str] = []

    if args.file:
        fp = os.path.normpath(args.file)
        variants = {fp, fp.replace("\\", "/")}
        m = re.match(r"^([a-zA-Z]):[\\/](.*)", fp)
        if m:
            drive = m.group(1).lower()
            rest = m.group(2).replace("\\", "/")
            variants.add(f"/mnt/{drive}/{rest}")
        where_parts.append("(" + " OR ".join(["file_path = ?"] * len(variants)) + ")")
        params.extend(variants)
    elif args.under:
        patterns = folder_like_patterns(args.under)
        where_parts.append("(" + " OR ".join(["file_path LIKE ?"] * len(patterns)) + ")")
        params.extend(patterns)

    sql = "SELECT id, file_path, thumbnail_path, thumbnail_path_win FROM images"
    if where_parts:
        sql += " WHERE " + " AND ".join(where_parts)

    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()

    total = len(rows)
    processed = 0
    regenerated = 0
    dry_run_would = 0
    skipped_ok = 0
    skipped_no_file = 0
    failed = 0

    logger.info("Selected %s row(s) from images.", total)

    for row in rows:
        if args.limit and processed >= args.limit:
            break

        rid = row["id"] if hasattr(row, "keys") else row[0]
        file_path = row["file_path"] if hasattr(row, "keys") else row[1]
        tp = row["thumbnail_path"] if hasattr(row, "keys") else row[2]
        tw = row["thumbnail_path_win"] if hasattr(row, "keys") else row[3]

        processed += 1

        if not file_path or not str(file_path).strip():
            skipped_no_file += 1
            continue

        fs_path = filesystem_path_for_image(file_path)
        if not fs_path:
            logger.warning("Original missing on disk id=%s path=%s", rid, file_path)
            skipped_no_file += 1
            continue

        if (
            not args.regenerate_all_in_scope
            and resolved_thumb_ok(tp, tw)
            and not args.force
        ):
            skipped_ok += 1
            continue

        if args.force and not args.dry_run:
            for c in _thumb_fs_candidates(file_path):
                if os.path.isfile(c):
                    try:
                        os.remove(c)
                    except OSError as e:
                        logger.warning("Could not remove %s: %s", c, e)

        if args.dry_run:
            logger.info(
                "[dry-run] would regenerate id=%s file=%s (thumb_ok=%s)",
                rid,
                file_path,
                resolved_thumb_ok(tp, tw),
            )
            dry_run_would += 1
            continue

        gen_kw = {}
        if fs_path != file_path:
            gen_kw["source_path"] = fs_path
        new_thumb = thumbnails.generate_thumbnail(file_path, **gen_kw)
        if not new_thumb or not os.path.isfile(new_thumb) or os.path.getsize(new_thumb) <= 0:
            logger.error("Thumbnail generation failed id=%s file=%s", rid, file_path)
            failed += 1
            continue

        if db.update_image_thumbnail_paths(int(rid), new_thumb, None):
            regenerated += 1
            logger.info("OK id=%s -> %s", rid, new_thumb)
        else:
            logger.error("DB update failed id=%s (thumb file at %s)", rid, new_thumb)
            failed += 1

    logger.info(
        "Done. selected=%s processed=%s regenerated=%s dry_run_would=%s "
        "skipped_thumb_ok=%s skipped_missing_original=%s failed=%s",
        total,
        processed,
        regenerated,
        dry_run_would,
        skipped_ok,
        skipped_no_file,
        failed,
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
