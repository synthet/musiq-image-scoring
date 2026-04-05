#!/usr/bin/env python3
"""
Download curated Nikon NEF test samples into ``tests/fixtures/testing_samples`` (or a custom root).

Targets only hosts that serve raw .NEF bytes over HTTP(S) without a browser session.
See NEF_TESTING_SAMPLES_URLS.md for full list (galleries / Google Drive = manual).

  python scripts/python/download_nef_testing_samples.py
  python scripts/python/download_nef_testing_samples.py --dry-run
  python scripts/python/download_nef_testing_samples.py --force
  python scripts/python/download_nef_testing_samples.py --no-manifest

Root directory: NEF_TEST_SAMPLES_ROOT or repo ``tests/fixtures/testing_samples``

After a successful run (unless --dry-run / --no-manifest), writes manifest.json
and README.md (if missing) via nef_testing_manifest.refresh_testing_samples_artifacts.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from modules.testing_samples_paths import default_testing_samples_root  # noqa: E402

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from nef_testing_samples_sources import SAMPLES  # noqa: E402

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
MIN_NEF_BYTES = 50_000


def default_root() -> Path:
    env = os.environ.get("NEF_TEST_SAMPLES_ROOT")
    return Path(env) if env else Path(default_testing_samples_root())


def _is_probably_html(head: bytes) -> bool:
    h = head.lstrip()[:200].lower()
    return h.startswith(b"<") or b"<html" in h[:80]


def download_one(url: str, dest: Path, *, dry_run: bool, force: bool) -> str:
    """Returns status: ok | skip | err"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size >= MIN_NEF_BYTES and not force:
        print("  skip (already present)")
        return "skip"

    if dry_run:
        print(f"[dry-run] would fetch -> {dest}")
        return "ok"

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            chunk = resp.read(4096)
            if _is_probably_html(chunk):
                print(f"  reject: response looks like HTML (not a raw NEF): {url}", file=sys.stderr)
                return "err"
            tmp = dest.with_suffix(dest.suffix + ".part")
            with open(tmp, "wb") as f:
                f.write(chunk)
                shutil.copyfileobj(resp, f, length=256 * 1024)
        size = tmp.stat().st_size
        if size < MIN_NEF_BYTES:
            tmp.unlink(missing_ok=True)
            print(f"  reject: file too small ({size} B): {url}", file=sys.stderr)
            return "err"
        tmp.replace(dest)
        print(f"  saved {dest.name} ({size // 1024} KB)")
        return "ok"
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code}: {url}", file=sys.stderr)
        return "err"
    except urllib.error.URLError as e:
        print(f"  URL error {e}: {url}", file=sys.stderr)
        return "err"
    except OSError as e:
        print(f"  I/O error {e}: {dest}", file=sys.stderr)
        return "err"


def main() -> int:
    parser = argparse.ArgumentParser(description="Download Nikon NEF samples into the testing samples tree.")
    parser.add_argument("root", nargs="?", default=None, help="Override root (default: env or tests/fixtures/testing_samples)")
    parser.add_argument("--dry-run", action="store_true", help="Print planned downloads only")
    parser.add_argument("--force", action="store_true", help="Re-download even if file already exists")
    parser.add_argument(
        "--no-manifest",
        action="store_true",
        help="Do not write manifest.json / README after downloads",
    )
    args = parser.parse_args()

    root = Path(args.root) if args.root else default_root()
    print(f"Root: {root.resolve()}")

    errs = 0
    for sub, name, url in SAMPLES:
        dest = root / sub / name
        print(f"{sub}/{name}")
        st = download_one(url, dest, dry_run=args.dry_run, force=args.force)
        if st == "err":
            errs += 1

    if errs:
        print(f"\nCompleted with {errs} error(s).", file=sys.stderr)

    if not args.dry_run and not args.no_manifest:
        try:
            from nef_testing_manifest import refresh_testing_samples_artifacts

            mp, rp, data = refresh_testing_samples_artifacts(
                root,
                use_exiftool=True,
                write_readme_if_missing=True,
                force_readme=False,
            )
            print(f"\nWrote {mp} ({len(data['files'])} .NEF entries, exiftool_used={data['exiftool_used']})")
            if rp:
                print(f"Wrote {rp}")
        except Exception as e:
            print(f"\nManifest/README update failed: {e}", file=sys.stderr)

    if errs:
        return 1
    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
