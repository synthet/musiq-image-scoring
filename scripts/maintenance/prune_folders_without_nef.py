"""
Remove from the database folder subtrees that contain no Nikon NEF images.

CLI wrapper for ``modules.folder_prune_nef.run_prune_folders_without_nef``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--root",
        default=None,
        help="Only consider folders under this path (normalized prefix match).",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete rows; default is dry-run.",
    )
    parser.add_argument(
        "--limit-images",
        type=int,
        default=0,
        help="If > 0, stop after deleting this many images (execute mode only).",
    )
    args = parser.parse_args()

    from modules.folder_prune_nef import run_prune_folders_without_nef

    result = run_prune_folders_without_nef(
        root=args.root,
        dry_run=not args.execute,
        limit_images=args.limit_images or 0,
    )
    print(result.get("message", result))
    if args.execute is False and result.get("prune_folder_count") is not None:
        print(
            f"  folders (no NEF subtree): {result.get('prune_folder_count')} | "
            f"top-level roots: {result.get('top_level_prune_roots')} | "
            f"image rows: {result.get('image_paths_count')}"
        )
    if result.get("root_paths"):
        for p in result["root_paths"][:25]:
            print(f"  root: {p}")
        if len(result["root_paths"]) > 25:
            print(f"  ... and {len(result['root_paths']) - 25} more roots")
    if result.get("errors"):
        for e in result["errors"][:20]:
            print(f"  error: {e}")
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
