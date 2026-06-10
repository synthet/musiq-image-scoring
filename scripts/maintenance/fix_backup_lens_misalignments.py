#!/usr/bin/env python3
"""
fix_backup_lens_misalignments.py

Fix lens misalignments in a backup (e.g. H:\\Photos) that may not be in the DB.
Works in two modes:

1. **Lens folders** (path contains lens like 180-600mm): Move images to correct lens
   folder when EXIF lens does not match path. Same logic as move_misplaced_by_lens
   but without DB updates.

2. **Flat structure** (path has no lens, e.g. H:\\Photos\\2026-01-19): Organize into
   camera/lens/year/date from EXIF, then optionally run lens check.

Usage:
    python scripts/maintenance/fix_backup_lens_misalignments.py --source "H:\\Photos" [--dry-run] [--yes]

Run in WSL with venv (exiftool required).
"""
import argparse
import os
import re
import shutil
import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from modules.exif_extractor import extract_exif
from modules.lens_folder_name import (
    extract_lens_token_from_model,
    extract_lens_token_from_path_segment,
)

_SIDECAR_EXTENSIONS = (".xmp",)
_IMAGE_EXTENSIONS = (".nef", ".arw", ".cr2", ".cr3", ".dng", ".orf", ".rw2")


def _extract_lens_from_model(lens_model: str | None) -> str | None:
    return extract_lens_token_from_model(lens_model)


def _extract_lens_from_path(path: str) -> str | None:
    if not path:
        return None
    normalized = path.replace("\\", "/")
    parts = [p for p in normalized.split("/") if p]
    for p in parts:
        token = extract_lens_token_from_path_segment(p)
        if token:
            return token
    return None


def _replace_lens_in_path(path: str, old_lens: str, new_lens: str) -> str:
    if not path or not old_lens or not new_lens:
        return path
    normalized = path.replace("\\", "/")
    old_norm = old_lens.replace("\\", "/")
    new_norm = new_lens.replace("\\", "/")
    pattern = re.compile(r"(?<=/)(" + re.escape(old_norm) + r")(?=/)", re.IGNORECASE)
    result = pattern.sub(new_norm, normalized, count=1)
    if result == normalized:
        result = normalized.replace("/" + old_norm + "/", "/" + new_norm + "/")
        if result == normalized:
            result = normalized.replace(old_norm, new_norm, 1)
    return result.replace("/", "\\") if "\\" in path else result


def _model_to_camera(model: str | None) -> str:
    """Map EXIF Model to folder name (Z8, Z6ii, D90, etc.)."""
    if not model:
        return "Unknown"
    m = str(model).strip().upper()
    if "Z 8" in m or "Z8" in m:
        return "Z8"
    if "Z 6" in m or "Z6 II" in m or "Z6II" in m:
        return "Z6ii"
    if "D300" in m:
        return "D300"
    if "D90" in m:
        return "D90"
    return "Unknown"


def _find_sidecars(main_path: str) -> list[str]:
    base = Path(main_path)
    stem = base.stem
    parent = base.parent
    found = []
    for ext in _SIDECAR_EXTENSIONS:
        sidecar = parent / (stem + ext)
        if sidecar.exists() and sidecar != base:
            found.append(str(sidecar))
    return found


def _resolve_path(path: str) -> str:
    """Return path suitable for current env (WSL vs Windows)."""
    p = path.replace("\\", "/")
    if p.startswith("/mnt/"):
        if os.name == "nt":
            parts = p.split("/")
            if len(parts) >= 4:
                drive = parts[2].upper()
                rest = "\\".join(parts[3:])
                return f"{drive}:\\{rest}"
        return p
    if re.match(r"^[a-zA-Z]:", p):
        if os.name != "nt" and os.path.exists("/mnt"):
            m = re.match(r"^([a-zA-Z]):[/\\]?(.*)", p)
            if m:
                return f"/mnt/{m.group(1).lower()}/{m.group(2).replace(chr(92), '/')}"
        return p.replace("/", "\\") if os.name == "nt" else p
    return p.replace("/", "\\") if os.name == "nt" else p


def _to_native(path: str, root: str) -> str:
    """Convert path to native format for root (H: vs /mnt/h/)."""
    p = path.replace("\\", "/")
    if root.startswith("/mnt/") and ":" in p:
        # Windows path under WSL root
        m = re.match(r"^([a-zA-Z]):[/\\](.*)", p)
        if m:
            return f"/mnt/{m.group(1).lower()}/{m.group(2).replace(chr(92), '/')}"
    if p.startswith("/mnt/") and os.name == "nt":
        parts = p.split("/")
        if len(parts) >= 4:
            return f"{parts[2].upper()}:\\" + "\\".join(parts[3:])
    return p


def find_misplaced_files(source_root: str) -> list[dict]:
    """Scan filesystem for images with path lens != EXIF lens. No DB."""
    source_native = _resolve_path(source_root)
    misplaced = []
    path_lens = _extract_lens_from_path(source_native)
    if not path_lens:
        return []  # Flat structure - handled separately

    for root, _dirs, files in os.walk(source_native, topdown=True):
        for f in files:
            if Path(f).suffix.lower() not in _IMAGE_EXTENSIONS:
                continue
            full_path = os.path.join(root, f)
            exif = extract_exif(full_path, image_id=None)
            if not exif:
                continue
            lens_model = exif.get("lens_model") or exif.get("focal_length")
            exif_lens = _extract_lens_from_model(str(lens_model) if lens_model else "")
            if not exif_lens:
                continue
            p_lens = _extract_lens_from_path(full_path)
            if not p_lens or p_lens == exif_lens:
                continue
            new_path = _replace_lens_in_path(full_path, p_lens, exif_lens)
            if new_path == full_path:
                continue
            misplaced.append({
                "file_path": full_path,
                "file_name": f,
                "path_lens": p_lens,
                "exif_lens": exif_lens,
                "lens_model": str(lens_model or "")[:50],
                "new_path": new_path,
            })
    return misplaced


def organize_flat_by_exif(source_root: str, limit: int | None = None) -> list[dict]:
    """For flat structure: build target path from EXIF (camera/lens/year/date)."""
    source_native = _resolve_path(source_root)
    to_move = []
    count = 0
    for root, _dirs, files in os.walk(source_native, topdown=True):
        if limit and count >= limit:
            break
        for f in files:
            if Path(f).suffix.lower() not in _IMAGE_EXTENSIONS:
                continue
            full_path = os.path.join(root, f)
            try:
                exif = extract_exif(full_path, image_id=None)
            except Exception:
                exif = None
            if not exif:
                continue
            lens_model = exif.get("lens_model") or exif.get("focal_length")
            exif_lens = _extract_lens_from_model(str(lens_model) if lens_model else "")
            if not exif_lens:
                continue
            model = exif.get("model")
            camera = _model_to_camera(model)
            dt = exif.get("date_time_original") or exif.get("create_date") or ""
            year = "Unknown"
            date = "Unknown"
            if dt:
                m = re.search(r"(\d{4}):(\d{2}):(\d{2})", str(dt))
                if m:
                    year = m.group(1)
                    date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
            rel = f"{camera}/{exif_lens}/{year}/{date}/{f}"
            new_path = os.path.join(source_native, rel)
            if os.path.normpath(full_path) != os.path.normpath(new_path):
                to_move.append({
                    "file_path": full_path,
                    "file_name": f,
                    "new_path": new_path,
                    "camera": camera,
                    "exif_lens": exif_lens,
                    "date": date,
                })
                count += 1
                if limit and count >= limit:
                    break
    return to_move


def move_files(items: list[dict], dry_run: bool) -> dict:
    """Move files and sidecars. No DB updates."""
    updated = 0
    failed = []
    for item in items:
        old_path = item["file_path"]
        new_path = item["new_path"]
        try:
            old_native = _resolve_path(old_path)
            new_native = _resolve_path(new_path)
            if dry_run:
                print(f"  [DRY-RUN] {old_path} -> {new_path}")
                updated += 1
                continue
            if os.path.exists(new_native):
                continue  # Skip if target exists
            if not os.path.exists(old_native):
                failed.append((old_path, "Source not found"))
                continue
            os.makedirs(os.path.dirname(new_native), exist_ok=True)
            shutil.move(old_native, new_native)
            for sidecar in _find_sidecars(old_native):
                if os.path.exists(sidecar):
                    sc_new = os.path.join(os.path.dirname(new_native), os.path.basename(sidecar))
                    if not os.path.exists(sc_new):
                        shutil.move(sidecar, sc_new)
            updated += 1
        except Exception as e:
            failed.append((old_path, str(e)))
    return {"updated": updated, "failed": failed}


def main() -> None:
    parser = argparse.ArgumentParser(description="Fix lens misalignments in backup (no DB)")
    parser.add_argument("--source", required=True, help="Root folder (e.g. H:\\Photos)")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation")
    parser.add_argument("--flat-only", action="store_true", help="Only organize flat structure (ignore lens folders)")
    parser.add_argument("--limit", type=int, default=None, help="Max files to process (for testing)")
    args = parser.parse_args()

    source = args.source.strip()
    if not source:
        print("[ERROR] --source is required.")
        sys.exit(1)

    source_resolved = _resolve_path(source)
    if not os.path.isdir(source_resolved):
        print(f"[ERROR] Source not found: {source_resolved}")
        sys.exit(1)

    has_lens_in_path = _extract_lens_from_path(source_resolved) is not None
    if has_lens_in_path and not args.flat_only:
        print(f"Scanning for misplaced images (lens folders) in: {source}")
        items = find_misplaced_files(source)
        mode = "lens"
    else:
        print(f"Organizing flat structure by EXIF in: {source}")
        items = organize_flat_by_exif(source, limit=args.limit)
        mode = "flat"

    print(f"Found {len(items)} to process.")

    if not items:
        print("Nothing to do.")
        return

    for item in items[:5]:
        if mode == "lens":
            print(f"  {item['file_name']}: {item['path_lens']} -> {item['exif_lens']}")
        else:
            rel = os.path.relpath(item["new_path"], _resolve_path(source))
            print(f"  {item['file_name']} -> {rel}")
    if len(items) > 5:
        print(f"  ... and {len(items) - 5} more")

    if not args.dry_run and not args.yes:
        resp = input(f"\nProceed with {len(items)} move(s)? [y/N]: ").strip().lower()
        if resp not in ("y", "yes"):
            print("Aborted.")
            return

    result = move_files(items, dry_run=args.dry_run)
    print(f"\nResults: Updated={result['updated']}, Failed={len(result['failed'])}")
    for p, e in result["failed"][:5]:
        print(f"  {p}: {e}")
    if args.dry_run:
        print("\n[DRY-RUN] No changes made. Remove --dry-run to execute.")
    else:
        print("Done.")


if __name__ == "__main__":
    main()
