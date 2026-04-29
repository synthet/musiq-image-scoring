#!/usr/bin/env python3
"""
Write a redacted support bundle (zip) for image-scoring-backend.

Never includes secrets.json contents. Redacts keys whose names suggest secrets
and common password fields in nested structures.

Usage:
    python scripts/export_debug_bundle.py
    python scripts/export_debug_bundle.py --output /tmp/bundle.zip
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def main() -> int:
    root = _repo_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    os.chdir(root)

    parser = argparse.ArgumentParser(description="Export redacted debug bundle (zip)")
    default_dir = root / "exports" / "debug-bundles"
    default_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    default_zip = default_dir / f"debug-bundle-{ts}.zip"
    parser.add_argument("--output", "-o", type=Path, default=default_zip, help="Output .zip path")
    args = parser.parse_args()

    from modules.debug_bundle_export import write_redacted_debug_bundle

    result = write_redacted_debug_bundle(repo_root=root, output_zip=args.output)
    if not result.get("success"):
        print(result.get("error", "bundle failed"), file=sys.stderr)
        return 1
    print(result["path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
