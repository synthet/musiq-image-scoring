#!/usr/bin/env python3
"""
Remove image rows (and related data) whose paths fall under given directory prefixes.

Uses merged config (config.json + environment.json) for DB connection.
Run with --dry-run first (default). Use --execute to apply.

Example (WSL or Windows venv with DB reachable):

  python scripts/maintenance/purge_images_under_prefixes.py \\
    --prefix "D:\\\\Photos\\\\Lightroom" --prefix "/mnt/d/Photos/Lightroom" --execute
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# Repo root on path
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description="Purge images under path prefixes from the DB.")
    parser.add_argument(
        "--prefix",
        action="append",
        dest="prefixes",
        default=[],
        help="Directory prefix (repeatable). Windows or /mnt/... form.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete rows (default is dry-run).",
    )
    parser.add_argument(
        "--no-folder-cache",
        action="store_true",
        help="Do not delete matching rows from the folders cache table.",
    )
    args = parser.parse_args()
    if not args.prefixes:
        parser.error("Provide at least one --prefix")

    os.environ.setdefault("PYTHONPATH", _ROOT)
    from modules import db

    result = db.purge_images_under_path_prefixes(
        args.prefixes,
        dry_run=not args.execute,
        purge_folder_cache=not args.no_folder_cache,
    )
    print(json.dumps(result, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
