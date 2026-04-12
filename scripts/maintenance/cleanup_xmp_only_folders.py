#!/usr/bin/env python3
"""
Remove stale directories whose only files are .xmp sidecars (no camera RAW).

Useful after backup/sync mistakes (e.g. camera/year/ flat trees with orphan XMP).

Does not delete folders that contain any RAW file or any non-.xmp file (e.g. JPG, MOV).

Usage:
    python scripts/maintenance/cleanup_xmp_only_folders.py --root "E:\\\\Photos" --dry-run
    python scripts/maintenance/cleanup_xmp_only_folders.py --root "E:\\\\Photos" --yes
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Common camera RAW extensions (lowercase, with dot)
RAW_EXTS = frozenset(
    {
        ".3fr",
        ".arw",
        ".cr2",
        ".cr3",
        ".dcs",
        ".dcr",
        ".dng",
        ".drf",
        ".eip",
        ".erf",
        ".fff",
        ".iiq",
        ".k25",
        ".kdc",
        ".mdc",
        ".mef",
        ".mos",
        ".mrw",
        ".nef",
        ".nrw",
        ".orf",
        ".pef",
        ".raf",
        ".raw",
        ".rw2",
        ".rwl",
        ".sr2",
        ".srf",
        ".srw",
        ".x3f",
    }
)


def _is_raw_filename(name: str) -> bool:
    return Path(name).suffix.lower() in RAW_EXTS


def _only_xmp_files(filenames: list[str]) -> bool:
    if not filenames:
        return False
    return all(Path(f).suffix.lower() == ".xmp" for f in filenames)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", required=True, help="Root folder to scan (subfolders only)")
    ap.add_argument("--dry-run", action="store_true", help="List actions only")
    ap.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"Error: not a directory: {root}", file=sys.stderr)
        sys.exit(1)

    to_unlink: list[Path] = []
    to_rmdir: list[Path] = []

    for dirpath, _dirnames, filenames in os.walk(root, topdown=False):
        p = Path(dirpath)
        if p == root:
            continue
        if not filenames:
            continue
        if any(_is_raw_filename(f) for f in filenames):
            continue
        if not _only_xmp_files(filenames):
            continue
        for f in filenames:
            to_unlink.append(p / f)
        to_rmdir.append(p)

    if not to_unlink:
        print(f"No xmp-only folders found under {root}")
        return

    print(f"Found {len(to_unlink)} .xmp file(s) in {len(to_rmdir)} folder(s) (no RAW in those dirs)")
    for d in sorted(set(to_rmdir))[:40]:
        print(f"  {d}")
    if len(set(to_rmdir)) > 40:
        print(f"  ... and {len(set(to_rmdir)) - 40} more folders")

    if args.dry_run:
        print("\n[DRY RUN] No files removed.")
        return

    if not args.yes:
        reply = input("\nDelete these .xmp files and remove empty folders? [y/N]: ").strip().lower()
        if reply not in ("y", "yes"):
            print("Aborted.")
            return

    removed_files = 0
    for f in to_unlink:
        try:
            f.unlink()
            removed_files += 1
        except OSError as e:
            print(f"Failed to unlink {f}: {e}", file=sys.stderr)

    removed_dirs = 0
    for d in sorted(to_rmdir, key=lambda x: len(x.parts), reverse=True):
        try:
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
                removed_dirs += 1
        except OSError as e:
            print(f"Failed to rmdir {d}: {e}", file=sys.stderr)

    print(f"\nRemoved {removed_files} file(s); removed {removed_dirs} empty folder(s).")


if __name__ == "__main__":
    main()
