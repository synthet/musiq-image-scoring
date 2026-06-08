#!/usr/bin/env python3
"""Finalize phantom-scored images: backfill composite scores from stored per-model rows
and flip the scoring phase to ``done`` — no re-inference.

A phantom-scored image has ``image_model_scores`` rows (inference succeeded) but a NULL
``images.score_general`` and a non-terminal ``scoring`` phase row, because a scoring job
was interrupted between persisting per-model scores and the ResultWorker finalize step.
The folder then churns in auto-drive (``awaiting_scoring`` forever) while the JIT planner
sees no work. See ``modules/phantom_score_finalize.py`` for the full rationale.

Dry-run by default; pass --apply to write.

Usage (WSL, project root):
  source ~/.venvs/tf/bin/activate
  export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$(pwd)/FirebirdLinux/.../lib

  # Preview a single folder (no writes)
  python scripts/maintenance/finalize_phantom_scores.py --scope /mnt/d/Photos/Z8/180-600mm/2026/2026-05-24
  # Apply it
  python scripts/maintenance/finalize_phantom_scores.py --scope /mnt/d/Photos/Z8/180-600mm/2026/2026-05-24 --apply
  # Whole library preview
  python scripts/maintenance/finalize_phantom_scores.py --all
  # Specific images
  python scripts/maintenance/finalize_phantom_scores.py --image-ids 176827,176828 --apply
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--scope", help="Folder subtree to finalize (e.g. /mnt/d/Photos/.../2026-05-24)")
    target.add_argument("--all", action="store_true", help="Scan the whole library")
    target.add_argument("--image-ids", help="Comma-separated image ids to finalize")
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry-run preview)")
    parser.add_argument("--limit", type=int, default=5000, help="Max candidates per run (default 5000)")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON only")
    args = parser.parse_args()

    from modules.phantom_score_finalize import finalize_phantom_scores

    image_ids = None
    if args.image_ids:
        image_ids = [int(x) for x in args.image_ids.split(",") if x.strip()]

    summary = finalize_phantom_scores(
        scope_path=None if (args.all or image_ids) else args.scope,
        image_ids=image_ids,
        dry_run=not args.apply,
        limit=args.limit,
    )

    if args.json:
        print(json.dumps(summary, indent=2, default=str))
        return 0

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{mode}] phantom-score finalize")
    print(f"  candidates:            {summary['candidates']}")
    print(f"  composites backfilled: {summary['composites_backfilled']}")
    print(f"  phase finalized:       {summary['phase_finalized']}")
    if summary.get("no_model_scores"):
        print(f"  skipped (no model rows): {summary['no_model_scores']}")
    for s in summary.get("samples", []):
        print(
            f"    img {s['image_id']}: prev_phase={s['prev_phase_status']} "
            f"null_general={s['was_score_general_null']} -> score_general={s['score_general']}"
        )
    if not args.apply and summary["candidates"]:
        print("  (dry-run — re-run with --apply to write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
