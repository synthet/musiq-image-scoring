#!/usr/bin/env python3
"""
Write manifest.json (and optionally README.md) under the NEF testing samples root.

Records SHA-256 per .NEF and, when exiftool is on PATH, Make/Model/BitsPerSample/
NEFCompression/Compression/ImageSize.

  python scripts/python/build_nef_testing_manifest.py
  python scripts/python/build_nef_testing_manifest.py "<repo>\\tests\\fixtures\\testing_samples"
  python scripts/python/build_nef_testing_manifest.py --no-exiftool
  python scripts/python/build_nef_testing_manifest.py --force-readme
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from modules.testing_samples_paths import default_testing_samples_root  # noqa: E402

# Allow imports when run as script from repo root
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from nef_testing_manifest import refresh_testing_samples_artifacts  # noqa: E402


def default_root() -> Path:
    env = os.environ.get("NEF_TEST_SAMPLES_ROOT")
    return Path(env) if env else Path(default_testing_samples_root())


def main() -> int:
    parser = argparse.ArgumentParser(description="Build manifest.json for the NEF testing samples tree.")
    parser.add_argument("root", nargs="?", default=None, help="Testing samples root directory")
    parser.add_argument("--no-exiftool", action="store_true", help="Skip ExifTool (SHA-256 only)")
    parser.add_argument("--force-readme", action="store_true", help="Overwrite README.md from template")
    parser.add_argument("--no-readme", action="store_true", help="Do not write README.md")
    args = parser.parse_args()

    root = Path(args.root) if args.root else default_root()
    if not root.is_dir():
        print(f"Directory not found: {root}", file=sys.stderr)
        return 1

    mp, rp, data = refresh_testing_samples_artifacts(
        root,
        use_exiftool=not args.no_exiftool,
        write_readme_if_missing=not args.no_readme,
        force_readme=args.force_readme,
    )
    print(f"Wrote {mp}")
    if rp:
        print(f"Wrote {rp}")
    elif not args.no_readme and not args.force_readme:
        print("README.md unchanged (already exists; use --force-readme to replace)")

    print(f"Entries: {len(data['files'])}  exiftool_used={data['exiftool_used']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
