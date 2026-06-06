#!/usr/bin/env python3
"""Reconcile phantom phase-status rows: mark phases ``done`` where the work product already exists.

Targets the "phantom incomplete" class of folders surfaced by auto-drive stalls: images
that carry quality scores or keywords from an earlier run/import but whose
``image_phase_status`` row still reads ``not_started`` / ``failed``. The folder aggregate
counts them incomplete (``awaiting_scoring`` / ``awaiting_keywords``) while the JIT planner
correctly finds no work, so the drive churns ``nothing_to_queue`` / ``loop_detected`` and
eventually stalls.

Completeness is the negation of ``db.get_phase_incomplete_sql`` (the phase's own definition),
so this can never mark an image done that the phase itself would consider incomplete.
``done`` / ``skipped`` rows are never touched.

This is the operational analogue of the bird ``--reconcile-classified`` backfill; auto-drive
also runs the same reconcile at the start of each library drive (durable self-heal).

Usage (WSL, project root):
  source ~/.venvs/tf/bin/activate
  export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$(pwd)/FirebirdLinux/.../lib

  # Report only (dry-run; no writes)
  python scripts/maintenance/reconcile_phantom_phase_ips.py --report

  # Apply for scoring + keywords (dry-run first, then for real)
  python scripts/maintenance/reconcile_phantom_phase_ips.py --apply --dry-run
  python scripts/maintenance/reconcile_phantom_phase_ips.py --apply

  # Scope to one folder, or pick phases explicitly
  python scripts/maintenance/reconcile_phantom_phase_ips.py --apply --scope /mnt/d/Photos/Z8/180-600mm/2026/2026-05-24
  python scripts/maintenance/reconcile_phantom_phase_ips.py --apply --phases scoring keywords culling
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_DEFAULT_PHASES = ("scoring", "keywords")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--report", action="store_true",
        help="Dry-run: count phantom-complete images without writing (default if --apply omitted).",
    )
    parser.add_argument("--apply", action="store_true", help="Write IPS=done for phantom-complete images.")
    parser.add_argument("--dry-run", action="store_true", help="Force dry-run even with --apply.")
    parser.add_argument(
        "--phases", nargs="+", default=list(_DEFAULT_PHASES),
        help="Phases to reconcile (default: scoring keywords). Supported: indexing metadata scoring keywords culling.",
    )
    parser.add_argument("--scope", default=None, help="Limit to a folder path (and descendants).")
    parser.add_argument("--limit", type=int, default=100000, help="Max images per phase (default 100000).")
    args = parser.parse_args()

    dry_run = args.dry_run or not args.apply

    from modules import db

    result = db.reconcile_phantom_complete_image_phases(
        tuple(args.phases),
        scope_path=args.scope,
        limit=args.limit,
        dry_run=dry_run,
    )

    total = sum(result.values())
    verb = "would reconcile" if dry_run else "reconciled"
    for phase, n in result.items():
        logger.info("  %-10s %s %d phantom-complete image(s)", phase, verb, n)
    logger.info("%s %d image(s) across %d phase(s)%s", verb, total, len(result),
                "" if not dry_run else "  (dry-run — re-run with --apply to write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
