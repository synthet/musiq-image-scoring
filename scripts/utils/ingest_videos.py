#!/usr/bin/env python3
"""
Video library tool: ingest from any folder/drive, optionally filter by date, optionally
de-duplicate Nikon vs Z8 trees, then run organize_videos.py (unless disabled).

Ingest copies media into --dest root, skipping SHA-256 duplicates already in the library.
When --source lies inside --dest, that subtree is excluded from the duplicate index.

  python ingest_videos.py --source F:/
  python ingest_videos.py --source F:/ --since 2026-03-02 --videos-only
  python ingest_videos.py --dedupe-nikon-z8
  python ingest_videos.py --dedupe-nikon-z8 --source E:/DCIM
  python ingest_videos.py --source D:/Incoming --dry-run
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

# Keep in sync with organize_videos.py
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".webm", ".m4v", ".flv", ".3gp", ".mpeg", ".mpg", ".ogv"}
IMAGE_EXTS = {".jpg", ".jpeg"}
MEDIA_EXTS = VIDEO_EXTS | IMAGE_EXTS

CHUNK = 8 * 1024 * 1024


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(CHUNK):
            h.update(block)
    return h.hexdigest()


def _is_under(path: Path, ancestor: Path) -> bool:
    try:
        path.resolve().relative_to(ancestor.resolve())
        return True
    except ValueError:
        return False


def _unique_dest_name(dest_root: Path, name: str, reserved: set[str]) -> str:
    if name not in reserved and not (dest_root / name).exists():
        return name
    stem = Path(name).stem
    suffix = Path(name).suffix
    h = hashlib.sha256(name.encode("utf-8", errors="replace")).hexdigest()[:8]
    candidate = f"{stem}_{h}{suffix}"
    n = 0
    while candidate in reserved or (dest_root / candidate).exists():
        n += 1
        candidate = f"{stem}_{h}_{n}{suffix}"
    return candidate


def _collect_media_files(root: Path, exts: set[str]) -> list[Path]:
    out: list[Path] = []
    if not root.exists():
        return out
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in exts:
            out.append(p)
    return out


def _library_hashes(dest: Path, exclude_under: Path | None, exts: set[str]) -> set[str]:
    seen: set[str] = set()
    for p in _collect_media_files(dest, exts):
        if exclude_under is not None and _is_under(p, exclude_under):
            continue
        try:
            seen.add(_sha256(p))
        except OSError as e:
            print(f"WARN hash dest (skip index): {p}: {e}", flush=True)
    return seen


def _parse_ymd(s: str) -> datetime:
    return datetime.strptime(s.strip(), "%Y-%m-%d")


def _pick_keeper(paths: list[Path], nikon_dir: Path, z8_dir: Path) -> Path:
    def sort_key(p: Path) -> tuple[int, str]:
        r = p.resolve()
        in_n = _is_under(r, nikon_dir)
        in_z = _is_under(r, z8_dir)
        if in_n:
            tier = 0
        elif in_z:
            tier = 1
        else:
            tier = 2
        return (tier, str(r).lower())

    return sorted(paths, key=sort_key)[0]


def _prune_empty_dirs(top: Path) -> None:
    if not top.exists():
        return
    dirs = sorted({p for p in top.rglob("*") if p.is_dir()}, key=lambda p: len(p.parts), reverse=True)
    for d in dirs:
        try:
            d.rmdir()
        except OSError:
            pass


def _run_organize(dest: Path) -> int:
    organize = Path(__file__).resolve().parent / "organize_videos.py"
    if not organize.exists():
        print(f"organize_videos.py not found: {organize}", file=sys.stderr)
        return 1
    print(f"\nRunning: {sys.executable} {organize} {dest}", flush=True)
    return subprocess.run([sys.executable, str(organize), str(dest)], check=False).returncode


def dedupe_flatten_nikon_z8(video_root: Path, dry_run: bool) -> int:
    """Remove duplicate videos under Nikon/ and Z8/, flatten survivors to dest root. Returns error count."""
    nikon_dir = video_root / "Nikon"
    z8_dir = video_root / "Z8"

    all_paths: list[Path] = []
    all_paths.extend(_collect_media_files(nikon_dir, VIDEO_EXTS))
    all_paths.extend(_collect_media_files(z8_dir, VIDEO_EXTS))

    if not all_paths:
        print(f"No video files under {nikon_dir} or {z8_dir}.")
        return 0

    print(f"Scanning {len(all_paths)} video file(s) under Nikon/Z8 for duplicates…\n", flush=True)

    by_hash: dict[str, list[Path]] = defaultdict(list)
    errors = 0
    for p in all_paths:
        try:
            by_hash[_sha256(p)].append(p)
        except OSError as e:
            print(f"ERROR hash {p}: {e}", flush=True)
            errors += 1

    removed = 0
    for _digest, paths in sorted(by_hash.items(), key=lambda x: x[0]):
        if len(paths) <= 1:
            continue
        keeper = _pick_keeper(paths, nikon_dir, z8_dir)
        for p in paths:
            if p.resolve() == keeper.resolve():
                continue
            if dry_run:
                print(f"WOULD DELETE duplicate: {p}\n  (keeping {keeper})", flush=True)
            else:
                try:
                    p.unlink()
                    print(f"DELETED duplicate: {p}", flush=True)
                except OSError as e:
                    print(f"ERROR delete {p}: {e}", flush=True)
                    errors += 1
                    continue
            removed += 1

    print(f"\nDuplicate groups resolved: removed {removed} file(s). Errors: {errors}.\n", flush=True)

    survivors: list[Path] = []
    for p in _collect_media_files(nikon_dir, VIDEO_EXTS) + _collect_media_files(z8_dir, VIDEO_EXTS):
        if p.is_file():
            survivors.append(p)

    reserved: set[str] = {p.name for p in video_root.iterdir() if p.is_file()}
    moved = 0
    for path in sorted(survivors, key=lambda x: len(x.parts), reverse=True):
        if path.parent == video_root:
            reserved.add(path.name)
            continue
        target_name = _unique_dest_name(video_root, path.name, reserved)
        dest = video_root / target_name
        reserved.add(target_name)
        if dry_run:
            print(f"WOULD MOVE to root: {path} -> {dest}", flush=True)
            moved += 1
            continue
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(dest))
            print(f"MOVE: {path.relative_to(video_root)} -> {dest.name}", flush=True)
            moved += 1
        except OSError as e:
            print(f"ERROR move {path} -> {dest}: {e}", flush=True)
            errors += 1

    if not dry_run:
        _prune_empty_dirs(z8_dir)
        _prune_empty_dirs(nikon_dir)
        for d in (z8_dir, nikon_dir):
            try:
                if d.exists() and not any(d.iterdir()):
                    d.rmdir()
            except OSError:
                pass

    print(f"\nFlattened {moved} file(s) to {video_root}.", flush=True)
    return errors


def ingest_from_source(
    source: Path,
    dest_root: Path,
    since: datetime | None,
    exts: set[str],
    dry_run: bool,
) -> int:
    """Copy new media into dest root; returns error count."""
    exclude_from_index: Path | None = None
    try:
        source.relative_to(dest_root)
        exclude_from_index = source
    except ValueError:
        pass

    print(f"Source: {source}", flush=True)
    print(f"Dest:   {dest_root}", flush=True)
    if since:
        print(f"Filter: mtime >= {since.isoformat()} (local)", flush=True)
    if exclude_from_index:
        print(f"Index:  excluding duplicate check under {exclude_from_index} (inside dest)", flush=True)
    print(flush=True)

    library = _library_hashes(dest_root, exclude_from_index, exts)
    print(f"Library has {len(library)} distinct media file hash(es) indexed.\n", flush=True)

    sources = _collect_media_files(source, exts)
    if since:
        filtered: list[Path] = []
        skipped_old = 0
        for path in sources:
            try:
                mtime = datetime.fromtimestamp(path.stat().st_mtime)
            except OSError as e:
                print(f"SKIP stat: {path}: {e}", flush=True)
                continue
            if mtime < since:
                skipped_old += 1
            else:
                filtered.append(path)
        sources = filtered
        print(f"Skipped (before --since): {skipped_old} file(s).\n", flush=True)

    if not sources:
        print("No matching media files under source.")
        return 0

    reserved: set[str] = {p.name for p in dest_root.iterdir() if p.is_file()}
    batch_hashes: set[str] = set()
    copied = 0
    skipped_dup = 0
    errors = 0

    for path in sorted(sources):
        try:
            digest = _sha256(path)
        except OSError as e:
            print(f"ERROR hash: {path}: {e}", flush=True)
            errors += 1
            continue

        if digest in library or digest in batch_hashes:
            print(f"SKIP duplicate: {path}", flush=True)
            skipped_dup += 1
            continue

        name = _unique_dest_name(dest_root, path.name, reserved)
        reserved.add(name)
        dest_path = dest_root / name

        if dry_run:
            print(f"WOULD COPY: {path} -> {dest_path}", flush=True)
            copied += 1
            batch_hashes.add(digest)
            library.add(digest)
            continue

        dest_root.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(path, dest_path)
        except OSError as e:
            print(f"ERROR copy: {path} -> {dest_path}: {e}", flush=True)
            errors += 1
            reserved.discard(name)
            continue

        print(f"COPY: {path.name} -> {dest_path.name}", flush=True)
        copied += 1
        batch_hashes.add(digest)
        library.add(digest)

    print(
        f"\nIngest done. Copied: {copied}. Skipped (duplicate content): {skipped_dup}. Errors: {errors}.",
        flush=True,
    )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ingest media into the video library, optionally dedupe Nikon/Z8, then organize.",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help="Folder or drive to copy from (e.g. F:/). Omit if only running --dedupe-nikon-z8.",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=Path(r"D:\Videos"),
        help="Library root (default: D:\\Videos)",
    )
    parser.add_argument(
        "--since",
        type=str,
        default=None,
        metavar="YYYY-MM-DD",
        help="Only ingest files with mtime on or after this local date (ingest only)",
    )
    parser.add_argument(
        "--videos-only",
        action="store_true",
        help="Ingest video extensions only (no JPEG sidecars; ingest only)",
    )
    parser.add_argument(
        "--dedupe-nikon-z8",
        action="store_true",
        help="De-duplicate under dest/Nikon and dest/Z8 by hash, flatten to dest root, then organize",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show actions without writing")
    parser.add_argument("--no-organize", action="store_true", help="Do not run organize_videos.py")
    args = parser.parse_args()

    if not args.source and not args.dedupe_nikon_z8:
        parser.error("Specify --source and/or --dedupe-nikon-z8")

    dest_root = args.dest.resolve()
    if not dest_root.is_dir() and not args.dry_run:
        try:
            dest_root.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            print(f"Error: cannot create dest {dest_root}: {e}", file=sys.stderr)
            return 1

    since: datetime | None = None
    if args.since:
        try:
            since = _parse_ymd(args.since)
        except ValueError:
            print(f"Error: --since must be YYYY-MM-DD, got {args.since!r}", file=sys.stderr)
            return 1
        if not args.source:
            print("Error: --since requires --source", file=sys.stderr)
            return 1

    exts = VIDEO_EXTS if args.videos_only else MEDIA_EXTS

    total_errors = 0

    if args.dedupe_nikon_z8:
        if not dest_root.is_dir():
            print(f"Error: dest is not a directory: {dest_root}", file=sys.stderr)
            return 1
        total_errors += dedupe_flatten_nikon_z8(dest_root, args.dry_run)

    if args.source:
        source = args.source.resolve()
        if not source.exists():
            print(f"Error: source does not exist: {source}", file=sys.stderr)
            return 1
        if not source.is_dir():
            print(f"Error: source is not a directory: {source}", file=sys.stderr)
            return 1
        if source.resolve() == dest_root.resolve():
            print("Error: --source must not be the same folder as --dest.", file=sys.stderr)
            return 1
        try:
            total_errors += ingest_from_source(source, dest_root, since, exts, args.dry_run)
        except OSError as e:
            print(f"Error walking source: {e}", file=sys.stderr)
            return 1

    if args.no_organize or args.dry_run:
        return 0 if total_errors == 0 else 2

    rc = _run_organize(dest_root)
    return rc if rc != 0 else (0 if total_errors == 0 else 2)


if __name__ == "__main__":
    sys.exit(main())
