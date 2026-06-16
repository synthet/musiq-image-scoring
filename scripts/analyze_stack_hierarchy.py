"""Read-only stack / sub-stack hierarchy audit (statistics, tiers, RCA).

Run from WSL with the app venv::

    source ~/.venvs/tf/bin/activate
    python -m scripts.analyze_stack_hierarchy --json
    python -m scripts.analyze_stack_hierarchy --folder /mnt/d/Photos/2024 --sample 10
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone

from modules.culling_analytics._common import resolve_folder_id, utc_now_iso
from modules.culling_analytics.flags import compute_library_flags
from modules.culling_analytics.hierarchy import (
    DEFAULT_MIN_POPULATED_STACK,
    compute_library_hierarchy,
    compute_stack_hierarchy_detail,
    find_degenerate_stack_ids,
)

logger = logging.getLogger("analyze_stack_hierarchy")


def _build_report(
    *,
    folder_path: str | None,
    folder_id: int | None,
    min_populated_stack: int,
    sample: int,
) -> dict:
    fid, fpath = resolve_folder_id(folder_path, folder_id)
    if folder_path and fid is None:
        return {
            "error": "folder_not_found",
            "folder_path": folder_path,
            "generated_at": utc_now_iso(),
        }

    hierarchy = compute_library_hierarchy(fid, min_populated_stack=min_populated_stack)
    flags = compute_library_flags(fid)

    degenerate_ids = find_degenerate_stack_ids(fid, only="all")
    samples: list[dict] = []
    for sid in degenerate_ids[:sample]:
        detail = compute_stack_hierarchy_detail(sid, min_populated_stack=min_populated_stack)
        samples.append(detail)

    return {
        "scope": "folder" if fid is not None else "library",
        "folder_id": fid,
        "folder_path": fpath,
        "generated_at": utc_now_iso(),
        "overall": {
            "flags": flags,
            "hierarchy": hierarchy,
        },
        "per_stack_tier": hierarchy.get("tiers"),
        "per_substack_tier": {
            "total_substacks": hierarchy.get("total_substacks"),
            "singleton_leaves_all": hierarchy.get("singleton_leaves_all"),
            "singleton_leaf_pct": hierarchy.get("singleton_leaf_pct"),
            "expected_singleton_leaves": hierarchy.get("expected_singleton_leaves"),
            "decisions_avg": hierarchy.get("decisions_by_level", {}).get("per_substack_avg"),
        },
        "degenerate": {
            "stack_ids": degenerate_ids,
            "count": len(degenerate_ids),
            "samples": samples,
        },
        "populated": hierarchy.get("tiers", {}).get("populated"),
    }


def _print_human(report: dict) -> None:
    if report.get("error"):
        print(f"Error: {report['error']} ({report.get('folder_path')})")
        return

    h = report.get("overall", {}).get("hierarchy", {})
    print(f"Stack hierarchy audit — {report.get('scope')} — {report.get('generated_at')}")
    if report.get("folder_path"):
        print(f"Folder: {report['folder_path']}")

    print("\n--- Degenerate tiers ---")
    print(f"  Singleton root stacks:  {h.get('singleton_root_stacks', 0)}")
    print(f"  Single-leaf (1:1):      {h.get('single_leaf_stacks', 0)}")
    print(f"  Flat (no sub-stacks):   {h.get('flat_stacks', 0)}")

    print("\n--- Populated tiers ---")
    print(f"  Multi-leaf stacks:      {h.get('populated_multi_leaf_stacks', 0)}")
    print(f"  Expected singleton leaves:{h.get('expected_singleton_leaves', 0)}")
    print(f"  Total sub-stacks:       {h.get('total_substacks', 0)}")
    print(f"  Singleton leaf %:       {h.get('singleton_leaf_pct', 0)}%")

    dec = h.get("decisions_by_level", {})
    lib = dec.get("library", {})
    print("\n--- Library decisions (cull_decision) ---")
    print(f"  pick={lib.get('pick', 0)} reject={lib.get('reject', 0)} "
          f"neutral={lib.get('neutral', 0)} unset={lib.get('unset', 0)}")

    deg = report.get("degenerate", {})
    print(f"\n--- Degenerate stack ids ({deg.get('count', 0)}) ---")
    for sid in (deg.get("stack_ids") or [])[:15]:
        print(f"  stack_id={sid}")
    if deg.get("count", 0) > 15:
        print(f"  ... and {deg['count'] - 15} more")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--folder", help="Limit to images under this folder path.")
    parser.add_argument("--folder-id", type=int, help="Limit by folders.id.")
    parser.add_argument("--json", action="store_true", help="Emit JSON to stdout.")
    parser.add_argument(
        "--min-populated-stack",
        type=int,
        default=DEFAULT_MIN_POPULATED_STACK,
        help=f"Min stack size for populated tier heuristic (default {DEFAULT_MIN_POPULATED_STACK}).",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=10,
        help="Max degenerate stack detail samples in JSON output.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    try:
        report = _build_report(
            folder_path=args.folder,
            folder_id=args.folder_id,
            min_populated_stack=args.min_populated_stack,
            sample=max(0, args.sample),
        )
    except Exception as e:
        logger.exception("analyze_stack_hierarchy failed")
        if args.json:
            print(json.dumps({"error": str(e), "generated_at": datetime.now(timezone.utc).isoformat()}))
        else:
            print(f"Failed: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        _print_human(report)

    return 0 if not report.get("error") else 2


if __name__ == "__main__":
    raise SystemExit(main())
