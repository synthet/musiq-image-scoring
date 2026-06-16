"""Normalize degenerate stack hierarchies (singleton roots, redundant single-leaf).

Dry-run is the default. Run from WSL with the app venv::

    python -m scripts.maintenance.normalize_degenerate_stacks --dry-run
    python -m scripts.maintenance.normalize_degenerate_stacks --only single_leaf
    python -m scripts.maintenance.normalize_degenerate_stacks  # live
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from modules import db  # noqa: E402
from modules.culling_analytics._common import resolve_folder_id  # noqa: E402
from modules.culling_analytics.hierarchy import find_degenerate_stack_ids  # noqa: E402

logger = logging.getLogger("normalize_degenerate_stacks")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--folder", help="Limit to images under this folder path.")
    parser.add_argument("--folder-id", type=int, help="Limit by folders.id.")
    parser.add_argument(
        "--only",
        choices=("all", "singleton_root", "single_leaf"),
        default="all",
        help="Which degenerate tier to normalize (default: all).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Report actions without writing (default).",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Apply normalize_stack_hierarchy for each matching stack.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON summary.")
    args = parser.parse_args(argv)

    dry_run = not args.live
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    fid, fpath = resolve_folder_id(args.folder, args.folder_id)
    if args.folder and fid is None:
        logger.error("Folder not found: %s", args.folder)
        return 2

    stack_ids = find_degenerate_stack_ids(fid, only=args.only)
    results: list[dict] = []

    for sid in stack_ids:
        if dry_run:
            results.append({"stack_id": sid, "action": "would_normalize", "dry_run": True})
            continue
        norm = db.normalize_stack_hierarchy(sid)
        results.append({"stack_id": sid, **norm})

    summary = {
        "folder_id": fid,
        "folder_path": fpath,
        "only": args.only,
        "dry_run": dry_run,
        "count": len(stack_ids),
        "results": results,
    }

    if args.json:
        print(json.dumps(summary, indent=2, default=str))
    else:
        mode = "DRY-RUN" if dry_run else "LIVE"
        print(f"normalize_degenerate_stacks [{mode}] only={args.only} count={len(stack_ids)}")
        for r in results[:25]:
            print(f"  stack_id={r['stack_id']} action={r.get('action')}")
        if len(results) > 25:
            print(f"  ... and {len(results) - 25} more")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
