"""
Reset ``image_phase_status`` rows that failed with a specific (already-fixed) error.

When a runner bug is fixed, the ``failed`` rows it left behind stay failed forever: the
per-tick reconciler ``reset_retryable_stale_phase_failures`` only heals rows whose
``last_error`` starts with ``stale_running_reconciled``, and the auto-drive loop guard
keeps counting the failed jobs, so the folder is never retried.

This tool resets such rows to ``not_started`` so the next pipeline pass picks them up.
It is deliberately narrow: you must name the error text, and it is a dry run unless you
pass ``--apply``.

Usage (WSL + ~/.venvs/tf):
  python scripts/maintenance/reset_failed_phase_rows_by_error.py \\
      --error-like "name 'scan_stop' is not defined" \\
      --phase indexing --folder /mnt/d/Photos/Z8/105mm/2026/2026-07-04

  # ...then re-run with --apply once the dry-run counts look right.
"""

import argparse
import logging
import os
import sys

# Ensure project root is in PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from modules import utils
from modules.db_legacy import get_connector, set_image_phase_status

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def _folder_prefixes(folder: str) -> list:
    """Both the given form and its WSL form, so Windows/WSL storage both match."""
    raw = folder.rstrip('/\\')
    prefixes = {raw}
    try:
        converted = utils.convert_path_to_wsl(raw)
        if converted:
            prefixes.add(str(converted).rstrip('/\\'))
    except Exception:
        logger.debug("path conversion failed for %s", raw, exc_info=True)
    return sorted(prefixes)


def find_rows(*, error_like, phase=None, folder=None, max_attempt_count=0, limit=500):
    sql = [
        "SELECT ips.image_id, pp.code AS phase_code, i.file_path, ips.attempt_count",
        "FROM image_phase_status ips",
        "JOIN pipeline_phases pp ON pp.id = ips.phase_id",
        "JOIN images i ON i.id = ips.image_id",
        "WHERE LOWER(TRIM(ips.status)) = 'failed'",
        "  AND LOWER(COALESCE(ips.last_error, '')) LIKE ?",
    ]
    params: list = [f"%{error_like.strip().lower()}%"]
    if phase:
        sql.append("  AND LOWER(TRIM(pp.code)) = ?")
        params.append(phase.strip().lower())
    if max_attempt_count is not None:
        sql.append("  AND COALESCE(ips.attempt_count, 0) <= ?")
        params.append(int(max_attempt_count))
    if folder:
        prefixes = _folder_prefixes(folder)
        sql.append("  AND (" + " OR ".join(["i.file_path LIKE ?"] * len(prefixes)) + ")")
        params.extend(f"{p}%" for p in prefixes)
    sql.append("ORDER BY ips.image_id")
    sql.append("FETCH FIRST ? ROWS ONLY")
    params.append(int(limit))
    return get_connector().query("\n".join(sql), tuple(params)) or []


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--error-like", required=True,
                        help="Substring of image_phase_status.last_error to match (case-insensitive)")
    parser.add_argument("--phase", help="Restrict to one phase_code (e.g. indexing)")
    parser.add_argument("--folder", help="Restrict to images whose file_path starts with this folder")
    parser.add_argument("--max-attempt-count", type=int, default=0,
                        help="Only reset rows with attempt_count <= this (default 0: never really tried)")
    parser.add_argument("--limit", type=int, default=500, help="Maximum rows to touch (default 500)")
    parser.add_argument("--apply", action="store_true",
                        help="Actually write the reset. Without it this is a dry run.")
    args = parser.parse_args()

    rows = find_rows(
        error_like=args.error_like,
        phase=args.phase,
        folder=args.folder,
        max_attempt_count=args.max_attempt_count,
        limit=args.limit,
    )
    if not rows:
        logger.info("No matching failed rows.")
        return 0

    by_phase = {}
    for row in rows:
        by_phase[str(row.get("phase_code") or "?")] = by_phase.get(str(row.get("phase_code") or "?"), 0) + 1
    logger.info("Matched %d failed row(s): %s", len(rows), by_phase)
    for row in rows[:5]:
        logger.info("  sample: image_id=%s phase=%s attempts=%s path=%s",
                    row.get("image_id"), row.get("phase_code"),
                    row.get("attempt_count"), row.get("file_path"))
    if len(rows) > 5:
        logger.info("  ... and %d more", len(rows) - 5)

    if not args.apply:
        logger.info("Dry run — re-run with --apply to reset these rows to not_started.")
        return 0

    reset = 0
    for row in rows:
        image_id = int(row["image_id"])
        code = str(row.get("phase_code") or "").strip().lower()
        if not code:
            continue
        try:
            set_image_phase_status(image_id, code, "not_started")
            reset += 1
        except Exception:
            logger.warning("reset failed image_id=%s phase=%s", image_id, code, exc_info=True)
    logger.info("Reset %d of %d row(s) to not_started.", reset, len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
