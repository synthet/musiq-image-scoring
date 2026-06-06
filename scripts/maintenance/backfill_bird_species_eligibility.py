#!/usr/bin/env python3
"""Audit bird-species eligibility, mark terminal no-match rows, and optionally enqueue backfill.

Classifies images into:
  - not_in_scope     — no birds keyword (bird phase N/A)
  - complete         — has species:* keyword
  - pending          — birds tag, still needs classification
  - exhausted        — BioCLIP run found no species (marked birds:species-exhausted)
  - failed / skipped_other — IPS state worth manual review

Gap mode (--mark-exhausted) targets images with IPS bird_species=done but no species:*
(one cause of perpetual ``awaiting_bird_species`` folder backlog).

Reconcile mode (--reconcile-classified) targets the mirror gap: images that already have
a ``species:*`` keyword but never got an ``image_phase_status`` row (legacy/import tagging).
The folder aggregate counts them as in-scope-but-incomplete, so the folder lingers as a
phantom ``awaiting_bird_species`` bucket that auto-drive re-picks every tick and skips with
``nothing_to_queue``. Writing IPS=done clears the phantom.

Usage (WSL, project root):
  source ~/.venvs/tf/bin/activate
  export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$(pwd)/FirebirdLinux/.../lib

  # Report only
  python scripts/maintenance/backfill_bird_species_eligibility.py --report

  # Mark ~done-without-species rows as exhausted (dry-run first)
  python scripts/maintenance/backfill_bird_species_eligibility.py --mark-exhausted --dry-run
  python scripts/maintenance/backfill_bird_species_eligibility.py --mark-exhausted

  # Reconcile classified-but-no-phase-row images (drains phantom folders; dry-run first)
  python scripts/maintenance/backfill_bird_species_eligibility.py --reconcile-classified --dry-run
  python scripts/maintenance/backfill_bird_species_eligibility.py --reconcile-classified

  # List folders that still have pending species work (for schedule_bird_species_bird_folders.py)
  python scripts/maintenance/backfill_bird_species_eligibility.py --list-pending-folders

  # Enqueue one job per pending folder (requires WebUI)
  python scripts/maintenance/backfill_bird_species_eligibility.py --enqueue --api-base http://127.0.0.1:7860
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import Counter

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_SQL_AUDIT = """
SELECT
    i.id AS image_id,
    i.file_path,
    COALESCE(f.path, '') AS folder_path,
    LOWER(TRIM(COALESCE(ips.status, ''))) AS ips_status,
    CASE WHEN ({birds}) THEN 1 ELSE 0 END AS has_birds,
    CASE WHEN ({species}) THEN 1 ELSE 0 END AS has_species,
    CASE WHEN ({exhausted}) THEN 1 ELSE 0 END AS has_exhausted_marker
FROM images i
LEFT JOIN folders f ON f.id = i.folder_id
LEFT JOIN pipeline_phases pp ON LOWER(TRIM(pp.code)) = 'bird_species'
LEFT JOIN image_phase_status ips ON ips.image_id = i.id AND ips.phase_id = pp.id
WHERE ({birds})
   OR ({species})
   OR ({exhausted})
   OR LOWER(TRIM(COALESCE(ips.status, ''))) IN ('done', 'failed', 'skipped', 'running', 'queued')
"""

_SQL_DONE_NO_SPECIES = """
SELECT
    i.id AS image_id,
    i.file_path,
    COALESCE(f.path, '') AS folder_path,
    COALESCE(i.keywords, '') AS keywords_csv
FROM images i
LEFT JOIN folders f ON f.id = i.folder_id
JOIN pipeline_phases pp ON LOWER(TRIM(pp.code)) = 'bird_species'
JOIN image_phase_status ips ON ips.image_id = i.id AND ips.phase_id = pp.id
WHERE LOWER(TRIM(ips.status)) = 'done'
  AND ({birds})
  AND NOT ({species})
  AND NOT ({exhausted})
"""

_SQL_CLASSIFIED_NO_IPS = """
SELECT
    i.id AS image_id,
    COALESCE(f.path, '') AS folder_path
FROM images i
LEFT JOIN folders f ON f.id = i.folder_id
JOIN pipeline_phases pp ON LOWER(TRIM(pp.code)) = 'bird_species'
WHERE ({birds})
  AND ({species})
  AND NOT EXISTS (
      SELECT 1 FROM image_phase_status ips
      WHERE ips.image_id = i.id AND ips.phase_id = pp.id
  )
"""

_SQL_PENDING_FOLDERS = """
SELECT DISTINCT f.path AS folder_path
FROM images i
JOIN folders f ON f.id = i.folder_id
WHERE ({pending})
  AND f.path IS NOT NULL AND TRIM(f.path) <> ''
ORDER BY 1
"""


def _fragments():
    from modules.db_legacy import _sql_image_has_birds_keyword
    from modules.bird_species_eligibility import _sql_exhausted_marker, sql_bird_species_pending_predicate

    birds = _sql_image_has_birds_keyword("i")
    species = """EXISTS (
        SELECT 1 FROM image_keywords ik_s
        JOIN keywords_dim kd_s ON kd_s.keyword_id = ik_s.keyword_id
        WHERE ik_s.image_id = i.id AND LOWER(kd_s.keyword_norm) LIKE 'species:%'
    )"""
    exhausted = _sql_exhausted_marker("i")
    pending = sql_bird_species_pending_predicate("i")
    return birds, species, exhausted, pending


def _report(limit: int = 0) -> Counter:
    from modules import db
    from modules.bird_species_eligibility import classify_image_row

    db.init_db()
    birds, species, exhausted, pending = _fragments()
    sql = _SQL_AUDIT.format(birds=birds, species=species, exhausted=exhausted)
    if limit > 0:
        sql += f" LIMIT {int(limit)}"
    rows = db.get_connector().query(sql)
    counts: Counter = Counter()
    for row in rows:
        cat = classify_image_row(
            image_id=int(row["image_id"]),
            has_birds=bool(row.get("has_birds")),
            has_species=bool(row.get("has_species")),
            has_exhausted_marker=bool(row.get("has_exhausted_marker")),
            ips_status=row.get("ips_status"),
        )
        counts[cat.value] += 1
    return counts


def _mark_exhausted(*, dry_run: bool, limit: int) -> int:
    from modules import db
    from modules.bird_species_eligibility import mark_species_exhausted

    db.init_db()
    birds, species, exhausted, _pending = _fragments()
    sql = _SQL_DONE_NO_SPECIES.format(birds=birds, species=species, exhausted=exhausted)
    if limit > 0:
        sql += f" LIMIT {int(limit)}"
    rows = db.get_connector().query(sql)
    marked = 0
    for row in rows:
        if mark_species_exhausted(
            int(row["image_id"]),
            existing_keywords_csv=str(row.get("keywords_csv") or ""),
            dry_run=dry_run,
        ):
            marked += 1
    return marked


def _reconcile_classified(*, dry_run: bool, limit: int) -> int:
    """Set bird_species IPS=done for classified images that never got an IPS row.

    Drains phantom ``awaiting_bird_species`` folders: images with a ``species:*``
    keyword but no per-image phase row, which the folder aggregate otherwise
    counts as in-scope-but-incomplete forever.
    """
    from modules import db
    from modules.bird_species_eligibility import mark_species_classified_done

    db.init_db()
    birds, species, _exhausted, _pending = _fragments()
    sql = _SQL_CLASSIFIED_NO_IPS.format(birds=birds, species=species)
    if limit > 0:
        sql += f" LIMIT {int(limit)}"
    rows = db.get_connector().query(sql)
    reconciled = 0
    for row in rows:
        if mark_species_classified_done(int(row["image_id"]), dry_run=dry_run):
            reconciled += 1
    return reconciled


def _list_pending_folders() -> list[str]:
    from modules import db

    db.init_db()
    _birds, _species, _exhausted, pending = _fragments()
    rows = db.get_connector().query(_SQL_PENDING_FOLDERS.format(pending=pending))
    return [str(r["folder_path"]).strip() for r in rows if r.get("folder_path")]


def _enqueue_folders(folder_paths: list[str], *, api_base: str, dry_run: bool) -> int:
    if dry_run:
        for p in folder_paths[:30]:
            logger.info("would enqueue: %s", p)
        if len(folder_paths) > 30:
            logger.info("... and %d more", len(folder_paths) - 30)
        return 0
    from scripts.schedule_bird_species_bird_folders import _post_bird_species_chunk

    ok = 0
    for path in folder_paths:
        try:
            resp = _post_bird_species_chunk(
                api_base,
                [path],
                overwrite=False,
                threshold=0.1,
                top_k=3,
                candidate_species=None,
                timeout_sec=120,
            )
        except Exception as exc:
            logger.error("enqueue failed for %s: %s", path, exc)
            continue
        if resp.get("success"):
            ok += 1
            data = resp.get("data") or {}
            logger.info("queued job_id=%s folder=%s", data.get("job_id"), path)
    return ok


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--report", action="store_true", help="Print eligibility counts and exit")
    p.add_argument(
        "--mark-exhausted",
        action="store_true",
        help="Mark done-without-species images as birds:species-exhausted",
    )
    p.add_argument(
        "--reconcile-classified",
        action="store_true",
        help="Set bird_species IPS=done for species:* images missing a phase row (drains phantom folders)",
    )
    p.add_argument("--list-pending-folders", action="store_true", help="Print distinct folders with pending work")
    p.add_argument("--enqueue", action="store_true", help="POST one bird_species job per pending folder (WebUI up)")
    p.add_argument("--dry-run", action="store_true", help="No writes / no HTTP POST")
    p.add_argument("--limit", type=int, default=0, help="Max rows per action (0 = all)")
    p.add_argument(
        "--api-base",
        default=os.environ.get("IMGSCORE_API_BASE", "http://127.0.0.1:7860"),
        help="WebUI base for --enqueue",
    )
    p.add_argument("--output-json", default="", metavar="PATH", help="Write pending folder list as JSON array")
    args = p.parse_args()

    if not any(
        (args.report, args.mark_exhausted, args.reconcile_classified, args.list_pending_folders, args.enqueue)
    ):
        args.report = True

    if args.report:
        counts = _report(limit=args.limit)
        logger.info("Eligibility counts (bird-tagged / species / IPS activity subset):")
        for key, val in sorted(counts.items()):
            logger.info("  %s: %s", key, val)

    if args.mark_exhausted:
        n = _mark_exhausted(dry_run=args.dry_run, limit=args.limit)
        logger.info(
            "%s %d image(s) as species-exhausted (done IPS, no species:*)",
            "Would mark" if args.dry_run else "Marked",
            n,
        )

    if args.reconcile_classified:
        n = _reconcile_classified(dry_run=args.dry_run, limit=args.limit)
        logger.info(
            "%s %d classified image(s) as bird_species done (species:*, no phase row)",
            "Would reconcile" if args.dry_run else "Reconciled",
            n,
        )

    folders: list[str] = []
    if args.list_pending_folders or args.enqueue or args.output_json:
        folders = _list_pending_folders()
        if args.limit > 0:
            folders = folders[: args.limit]
        logger.info("Pending species folders: %d", len(folders))

    if args.output_json and folders:
        out = os.path.abspath(args.output_json)
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(folders, fh, indent=2)
        logger.info("Wrote %s", out)

    if args.list_pending_folders:
        for fp in folders[:50]:
            print(fp)
        if len(folders) > 50:
            print(f"... and {len(folders) - 50} more", file=sys.stderr)

    if args.enqueue:
        if not folders:
            logger.warning("No pending folders to enqueue.")
            return 1
        n = _enqueue_folders(folders, api_base=args.api_base, dry_run=args.dry_run)
        logger.info("Enqueued %d folder job(s).", n)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
