"""
Remove from the database images under a root whose first subfolder is not allowed.

**Config** (``config.json`` / ``environment.json``, under ``indexing``):

- ``photos_prune_root`` — root directory (default ``D:\\Photos`` if unset).
- ``photos_prune_top_segment_whitelist`` — extra top-level folder names to always keep
  (case-insensitive); union with the allow regex below.
- ``photos_prune_top_segment_allow_regex`` — optional regex (full match on first segment);
  omit to use the built-in Nikon D/Z pattern.

Uses merged config for the DB. Default is dry-run; pass ``--execute`` to apply.
See ``preview_photos_prune_folders.py`` for a sample allow/deny table (no DB).

Example:

  python scripts/maintenance/prune_photos_keep_camera_folders.py --execute

  python scripts/maintenance/prune_photos_keep_camera_folders.py \\
    --root "D:\\\\Photos" --whitelist TestingSamples --execute

Custom regex (overrides config regex for this run):

  python scripts/maintenance/prune_photos_keep_camera_folders.py \\
    --allow-regex "^[DdZz].*" --execute
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--root",
        default=None,
        help="Photos root; default indexing.photos_prune_root or D:\\Photos.",
    )
    parser.add_argument(
        "--whitelist",
        action="append",
        dest="whitelist",
        default=[],
        metavar="NAME",
        help="Extra top-level folder name to keep (repeatable); merged with config whitelist.",
    )
    parser.add_argument(
        "--allow-regex",
        default=None,
        help="Override allow regex for this run (fullmatch on first segment).",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete rows (default is dry-run).",
    )
    parser.add_argument(
        "--limit-images",
        type=int,
        default=0,
        help="If > 0, stop after deleting this many images (execute mode only).",
    )
    args = parser.parse_args()

    os.environ.setdefault("PYTHONPATH", _ROOT)
    from modules.photos_top_segment_prune import run_prune_keep_top_segment_pattern

    result = run_prune_keep_top_segment_pattern(
        root=args.root,
        allow_pattern=args.allow_regex,
        extra_whitelist=args.whitelist or None,
        dry_run=not args.execute,
        limit_images=args.limit_images or 0,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
