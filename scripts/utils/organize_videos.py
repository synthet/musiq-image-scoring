#!/usr/bin/env python3
"""
Analyze metadata of video/media files and organize into folder structure.
Uses filename patterns and file dates (no exiftool required).
Usage: python organize_videos.py [path]
  path: Root folder (default: D:\Videos)
"""
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass
import re
from datetime import datetime
from collections import defaultdict

def _get_root() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(r"D:\Videos")
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".webm", ".m4v", ".flv", ".3gp", ".mpeg", ".mpg", ".ogv"}
IMAGE_EXTS = {".jpg", ".jpeg"}  # DJI sometimes saves JPGs alongside videos

# Patterns: (regex, source_name, date_group or None for file_mtime)
PATTERNS = [
    # DJI drone: DJI_20251123153554_0043_D.MP4
    (re.compile(r"^DJI_(\d{8})\d{6}_.*\.(mp4|MP4|jpg|JPG)$", re.I), "DJI", lambda m: m.group(1)),
    # Date-prefix (action cam, etc): 20250505_0959.MOV or 20250613_102.MOV
    (re.compile(r"^(\d{8})_\d+\.(mov|MOV|mp4|MP4)$", re.I), "ActionCam", lambda m: m.group(1)),
    # Pixel: PXL_20240330_151858411_compressed.mp4
    (re.compile(r"^PXL_(\d{8})_.*\.(mp4|MP4)$", re.I), "Pixel", lambda m: m.group(1)),
    # Nikon DSC: DSC_0632.MOV or collision rename DSC_0632_a1b2c3d4.MOV (use file mtime)
    (re.compile(r"^DSC_\d+(?:_[a-f0-9]{8})?\.(mov|MOV|mp4|MP4)$", re.I), "Nikon", None),
    # Edited/exported
    (re.compile(r"^(output|Timeline\s+\d+)\.(mp4|MP4)$", re.I), "Edited", None),
]


def parse_date(s: str) -> tuple[int, int] | None:
    """Parse YYYYMMDD to (year, month)."""
    try:
        dt = datetime.strptime(s, "%Y%m%d")
        return dt.year, dt.month
    except ValueError:
        return None


def get_file_date(path: Path) -> tuple[int, int]:
    """Get (year, month) from file mtime."""
    mtime = path.stat().st_mtime
    dt = datetime.fromtimestamp(mtime)
    return dt.year, dt.month


def classify(path: Path, root: Path) -> tuple[str, tuple[int, int]] | None:
    """Return (source, (year, month)) or None if skip."""
    name = path.name
    ext = path.suffix.lower()
    if ext not in VIDEO_EXTS and ext not in IMAGE_EXTS:
        return None

    # Only organize files at root level (leave subfolders as-is)
    if path.parent != root:
        return None

    for pattern, source, date_extractor in PATTERNS:
        m = pattern.match(name)
        if m:
            if date_extractor:
                date_str = date_extractor(m)
                parsed = parse_date(date_str)
                if parsed:
                    return source, parsed
            return source, get_file_date(path)

    # Fallback: use filename date or mtime
    m = re.match(r"^(\d{8})", name)
    if m:
        parsed = parse_date(m.group(1))
        if parsed:
            return "Other", parsed
    return "Other", get_file_date(path)


def main():
    root = _get_root()
    if not root.exists():
        print(f"Error: {root} does not exist.")
        sys.exit(1)
    print(f"Organizing: {root}\n")

    files = list(root.rglob("*"))
    media = [f for f in files if f.is_file() and f.suffix.lower() in VIDEO_EXTS | IMAGE_EXTS]

    # Analyze
    by_source = defaultdict(list)
    for path in media:
        result = classify(path, root)
        if result:
            source, (year, month) = result
            by_source[source].append((path, year, month))

    # Report
    print("=== Metadata analysis ===\n")
    for source in sorted(by_source):
        items = by_source[source]
        print(f"{source}: {len(items)} files")
        by_date = defaultdict(int)
        for _, y, m in items:
            by_date[(y, m)] += 1
        for (y, m), count in sorted(by_date.items()):
            print(f"  {y}-{m:02d}: {count}")

    # Create structure and move
    # Structure: {Source}/{Year}/{Year-Month}/filename
    print("\n=== Organizing ===\n")
    moved = 0
    for source in sorted(by_source):
        for path, year, month in by_source[source]:
            dest_dir = root / source / str(year) / f"{year}-{month:02d}"
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / path.name
            if dest == path:
                continue
            if dest.exists():
                print(f"SKIP (exists): {path.relative_to(root)}")
                continue
            path.rename(dest)
            try:
                print(f"MOVED: {path.name} -> {source}/{year}/{year}-{month:02d}/")
            except UnicodeEncodeError:
                print(f"MOVED: {path.name!r} -> {source}/{year}/{year}-{month:02d}/")
            moved += 1

    print(f"\nDone. Moved {moved} files.")


if __name__ == "__main__":
    main()
