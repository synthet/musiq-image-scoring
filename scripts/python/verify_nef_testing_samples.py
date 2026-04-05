#!/usr/bin/env python3
"""
Verify Nikon NEF samples under tests/fixtures/testing_samples (exifread + rawpy).

Optional --exiftool prints Make/Model/BitsPerSample/NEFCompression/Compression/ImageSize
when the exiftool binary is on PATH.

See NEF_TESTING_SAMPLES_URLS.md; use build_nef_testing_manifest.py for manifest.json.

  python scripts/python/verify_nef_testing_samples.py
  python scripts/python/verify_nef_testing_samples.py --exiftool
  python scripts/python/verify_nef_testing_samples.py "<repo>\\tests\\fixtures\\testing_samples"
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import exifread
import rawpy

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from modules.testing_samples_paths import default_testing_samples_root  # noqa: E402

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))


def verify_nef_exiftool(file_path: str) -> None:
    from nef_testing_manifest import exiftool_available, read_exiftool_tags

    if not exiftool_available():
        print("  [exiftool] not on PATH (install ExifTool for full Nikon RAW tags)")
        return
    tags = read_exiftool_tags(Path(file_path))
    if "ExifToolError" in tags:
        print(f"  [exiftool] {tags['ExifToolError']}")
        return
    for key in ("Make", "Model", "ImageSize", "BitsPerSample", "NEFCompression", "Compression"):
        if key in tags:
            print(f"  [exiftool] {key}: {tags[key]}")


def verify_nef(file_path: str, *, with_exiftool: bool) -> None:
    print(f"--- Verifying: {file_path} ---")
    try:
        with open(file_path, "rb") as f:
            tags = exifread.process_file(f, details=False)
            model = tags.get("Image Model", "Unknown")
            software = tags.get("Image Software", "Unknown")
            print(f"  Camera Model (EXIF): {model}")
            print(f"  Software: {software}")
    except Exception as e:
        print(f"  EXIF error: {e}")
        print()
        return

    try:
        with rawpy.imread(file_path) as raw:
            print(f"  Dimensions: {raw.sizes.width}x{raw.sizes.height}")
            print(f"  RAW Type: {raw.raw_type}")
            cfa = raw.color_desc
            print(f"  Color Filter Array: {cfa.decode() if isinstance(cfa, bytes) else cfa}")
    except Exception as e:
        print(f"  rawpy: {e} (common for Z8 High Efficiency until LibRaw/rawpy catch up)")

    if with_exiftool:
        verify_nef_exiftool(file_path)
    print()


def default_root() -> str:
    return os.environ.get("NEF_TEST_SAMPLES_ROOT", default_testing_samples_root())


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify NEF samples (exifread, rawpy, optional exiftool).")
    parser.add_argument("root", nargs="?", default=None, help="Testing samples root (default: repo tests/fixtures/testing_samples)")
    parser.add_argument("--exiftool", action="store_true", help="Also print ExifTool Nikon RAW tags")
    args = parser.parse_args()

    root_dir = args.root if args.root else default_root()
    if not os.path.isdir(root_dir):
        print(f"Directory not found: {root_dir}", file=sys.stderr)
        return 1

    found = 0
    for subdir in sorted(os.listdir(root_dir)):
        subdir_path = os.path.join(root_dir, subdir)
        if not os.path.isdir(subdir_path):
            continue
        for nef_file in sorted(f for f in os.listdir(subdir_path) if f.lower().endswith(".nef")):
            found += 1
            verify_nef(os.path.join(subdir_path, nef_file), with_exiftool=args.exiftool)

    if found == 0:
        print(f"No .NEF files under {root_dir}. Run download_nef_testing_samples.py first.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
