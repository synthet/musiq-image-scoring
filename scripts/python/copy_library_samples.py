#!/usr/bin/env python3
"""
Copy representative NEF files from the user's local photo library into
``tests/fixtures/testing_samples`` for camera+lens diversity testing.

  python scripts/python/copy_library_samples.py
  python scripts/python/copy_library_samples.py --dry-run
  python scripts/python/copy_library_samples.py --force

After copying, updates manifest.json via nef_testing_manifest.

These files are personal photos and MUST NOT be committed to git.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from modules.testing_samples_paths import default_testing_samples_root  # noqa: E402

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from library_samples_sources import LIBRARY_SAMPLES  # noqa: E402


def default_root() -> Path:
    env = os.environ.get("NEF_TEST_SAMPLES_ROOT")
    return Path(env) if env else Path(default_testing_samples_root())


def copy_one(src: Path, dest: Path, *, dry_run: bool, force: bool) -> str:
    """Returns status: ok | skip | err"""
    dest.parent.mkdir(parents=True, exist_ok=True)

    if not src.exists():
        print(f"  ERROR: source not found: {src}", file=sys.stderr)
        return "err"

    if dest.exists() and not force:
        src_size = src.stat().st_size
        dest_size = dest.stat().st_size
        if src_size == dest_size:
            print("  skip (already present, same size)")
            return "skip"

    if dry_run:
        print(f"  [dry-run] would copy {src} -> {dest}")
        return "ok"

    try:
        shutil.copy2(src, dest)
        size = dest.stat().st_size
        print(f"  copied {dest.name} ({size // 1024 // 1024:.0f} MB)")
        return "ok"
    except OSError as e:
        print(f"  ERROR: {e}", file=sys.stderr)
        return "err"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Copy personal library NEF samples into the testing samples tree."
    )
    parser.add_argument("root", nargs="?", default=None,
                        help="Override root (default: tests/fixtures/testing_samples)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print planned copies only")
    parser.add_argument("--force", action="store_true",
                        help="Re-copy even if file already exists")
    parser.add_argument("--no-manifest", action="store_true",
                        help="Do not update manifest.json after copies")
    args = parser.parse_args()

    root = Path(args.root) if args.root else default_root()
    print(f"Root: {root.resolve()}")
    print(f"Samples: {len(LIBRARY_SAMPLES)} camera+lens combinations\n")

    stats = {"ok": 0, "skip": 0, "err": 0}
    for sub, name, src_path in LIBRARY_SAMPLES:
        dest = root / sub / name
        src = Path(src_path)
        print(f"{sub}/{name}")
        st = copy_one(src, dest, dry_run=args.dry_run, force=args.force)
        stats[st] += 1

    print(f"\n--- Summary: {stats['ok']} copied, {stats['skip']} skipped, {stats['err']} errors ---")

    if not args.dry_run and not args.no_manifest and stats["err"] < len(LIBRARY_SAMPLES):
        try:
            from nef_testing_manifest import refresh_testing_samples_artifacts

            mp, rp, data = refresh_testing_samples_artifacts(
                root,
                use_exiftool=True,
                write_readme_if_missing=False,
                force_readme=False,
            )
            print(f"\nUpdated {mp} ({len(data['files'])} .NEF entries)")
        except Exception as e:
            print(f"\nManifest update failed: {e}", file=sys.stderr)

    return 1 if stats["err"] > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
