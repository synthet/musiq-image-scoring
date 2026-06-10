#!/usr/bin/env python3
"""
merge_numeric_lens_folders.py

Merge duplicate lens folder names on a backup tree (e.g. ``35 35 1.8 1.8`` → ``35mm``)
under ``camera/lens/year/date``. Updates ``manifest.json`` relPath entries when present.

Usage:
    python scripts/maintenance/merge_numeric_lens_folders.py --root "H:\\Photos" --dry-run
    python scripts/maintenance/merge_numeric_lens_folders.py --root "H:\\Photos" --execute --yes

Options:
    --root        Backup root (required)
    --dry-run     Preview only (default)
    --execute     Apply file moves and manifest rewrite
    --update-db   Also rewrite matching ``images.file_path`` rows (opt-in)
    --yes, -y     Skip confirmation prompt when using --execute
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from modules.db import get_db, get_or_create_folder, init_db
from modules.lens_folder_name import (
    UNKNOWN_LENS_FOLDER,
    extract_lens_token_from_model,
    lens_folder_from_exif_model,
)

_IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".nef", ".arw", ".cr2", ".cr3", ".dng", ".heic",
    ".webp", ".tiff", ".tif", ".raw", ".orf", ".rw2",
}
_SIDECAR_EXTENSIONS = (".xmp",)


def _replace_lens_segment(path: str, old_lens: str, new_lens: str) -> str:
    normalized = path.replace("\\", "/")
    old_norm = old_lens.replace("\\", "/")
    new_norm = new_lens.replace("\\", "/")
    pattern = re.compile(r"(?<=/)(" + re.escape(old_norm) + r")(?=/)", re.IGNORECASE)
    result = pattern.sub(new_norm, normalized, count=1)
    if result == normalized:
        result = normalized.replace("/" + old_norm + "/", "/" + new_norm + "/")
    return result.replace("/", "\\") if "\\" in path else result


def _find_sidecars(main_path: Path) -> list[Path]:
    found: list[Path] = []
    for ext in _SIDECAR_EXTENSIONS:
        sidecar = main_path.with_suffix(ext)
        if sidecar.exists() and sidecar != main_path:
            found.append(sidecar)
    return found


def _collect_lens_merges(root: Path) -> dict[tuple[str, str], str]:
    """Map (camera, old_lens_dir) → canonical_lens for folders that need merging."""
    merges: dict[tuple[str, str], str] = {}
    if not root.is_dir():
        return merges

    for camera_dir in sorted(root.iterdir()):
        if not camera_dir.is_dir():
            continue
        if camera_dir.name in ("manifest.json", "manifest.json.bak"):
            continue
        for lens_dir in sorted(camera_dir.iterdir()):
            if not lens_dir.is_dir():
                continue
            old_name = lens_dir.name
            token = extract_lens_token_from_model(old_name)
            if not token:
                continue
            canonical = lens_folder_from_exif_model(old_name)
            if canonical == UNKNOWN_LENS_FOLDER or canonical == old_name:
                continue
            merges[(camera_dir.name, old_name)] = canonical
    return merges


def _iter_image_files(lens_dir: Path):
    for dirpath, _dirnames, filenames in os.walk(lens_dir):
        for name in filenames:
            p = Path(dirpath) / name
            if p.suffix.lower() in _IMAGE_EXTENSIONS:
                yield p


def _merge_lens_tree(
    root: Path,
    camera: str,
    old_lens: str,
    canonical: str,
    dry_run: bool,
) -> dict[str, int]:
    stats = {"moved": 0, "skipped_duplicate": 0, "errors": 0}
    src_root = root / camera / old_lens
    dst_root = root / camera / canonical
    if not src_root.is_dir():
        return stats

    for src_file in _iter_image_files(src_root):
        rel = src_file.relative_to(src_root)
        dst_file = dst_root / rel
        sidecars = _find_sidecars(src_file)

        if dst_file.exists():
            stats["skipped_duplicate"] += 1
            print(f"  [skip duplicate] {src_file} (exists at {dst_file})")
            continue

        if dry_run:
            print(f"  [dry-run] move {src_file} -> {dst_file}")
            stats["moved"] += 1
            for sc in sidecars:
                print(f"  [dry-run] move {sc} -> {dst_file.with_suffix(sc.suffix)}")
            continue

        try:
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src_file), str(dst_file))
            stats["moved"] += 1
            for sc in sidecars:
                dst_sc = dst_file.with_suffix(sc.suffix)
                if not dst_sc.exists():
                    shutil.move(str(sc), str(dst_sc))
        except OSError as exc:
            stats["errors"] += 1
            print(f"  [error] {src_file}: {exc}")

    if not dry_run:
        # Remove empty directories under old lens tree (bottom-up)
        for dirpath, dirnames, filenames in os.walk(src_root, topdown=False):
            p = Path(dirpath)
            if p == src_root:
                continue
            try:
                if not any(p.iterdir()):
                    p.rmdir()
            except OSError:
                pass
        try:
            if src_root.exists() and not any(src_root.iterdir()):
                src_root.rmdir()
        except OSError:
            pass

    return stats


def _rewrite_manifest(root: Path, merges: dict[tuple[str, str], str], dry_run: bool) -> int:
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        return 0

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    images = data.get("images") or []
    rewritten = 0

    prefix_map: dict[str, str] = {}
    for (camera, old_lens), canonical in merges.items():
        old_prefix = f"{camera}/{old_lens}/".replace("\\", "/")
        new_prefix = f"{camera}/{canonical}/".replace("\\", "/")
        prefix_map[old_prefix.lower()] = new_prefix

    for entry in images:
        rel = str(entry.get("relPath") or "").replace("\\", "/")
        if not rel:
            continue
        rel_lower = rel.lower()
        for old_prefix, new_prefix in prefix_map.items():
            if rel_lower.startswith(old_prefix):
                suffix = rel[len(old_prefix) :]
                entry["relPath"] = new_prefix + suffix
                rewritten += 1
                break

    if rewritten == 0:
        return 0

    if dry_run:
        print(f"[dry-run] Would rewrite {rewritten} manifest relPath entries")
        return rewritten

    tmp_path = manifest_path.with_suffix(".json.tmp")
    bak_path = manifest_path.with_suffix(".json.bak")
    payload = json.dumps(data, indent=2)
    tmp_path.write_text(payload, encoding="utf-8")
    shutil.copy2(manifest_path, bak_path)
    tmp_path.replace(manifest_path)
    print(f"Rewrote {rewritten} manifest relPath entries ({manifest_path})")
    return rewritten


def _update_db_paths(root: Path, merges: dict[tuple[str, str], str], dry_run: bool) -> int:
    init_db()
    conn = get_db()
    cur = conn.cursor()
    updated = 0

    for (camera, old_lens), canonical in merges.items():
        patterns = (
            f"%/{camera}/{old_lens}/%",
            f"%\\{camera}\\{old_lens}\\%",
        )
        cur.execute(
            "SELECT id, file_path, folder_id FROM images WHERE file_path LIKE ? OR file_path LIKE ?",
            patterns,
        )
        rows = cur.fetchall()
        for row in rows:
            old_path = str(row["file_path"])
            new_path = _replace_lens_segment(old_path, old_lens, canonical)
            if new_path == old_path:
                continue
            if dry_run:
                print(f"  [dry-run] DB {row['id']}: {old_path} -> {new_path}")
                updated += 1
                continue

            new_folder = str(Path(new_path).parent).replace("\\", "/")
            folder_id = get_or_create_folder(new_folder)
            conn.commit()
            cur.execute(
                "UPDATE images SET file_path = ?, folder_id = ? WHERE id = ?",
                (new_path, folder_id, row["id"]),
            )
            if cur.rowcount:
                updated += 1

    if not dry_run:
        conn.commit()
    conn.close()
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge numeric Nikon lens folders to canonical …mm names")
    parser.add_argument("--root", required=True, help="Backup root (e.g. H:\\Photos)")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Preview only (default)")
    parser.add_argument("--execute", action="store_true", help="Apply file moves and manifest rewrite")
    parser.add_argument("--update-db", action="store_true", help="Rewrite images.file_path for merged lens segments")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation when executing")
    args = parser.parse_args()

    dry_run = not args.execute
    root = Path(args.root)

    if not root.is_dir():
        print(f"Error: root not found: {root}", file=sys.stderr)
        return 1

    merges = _collect_lens_merges(root)
    if not merges:
        print(f"No numeric lens folders to merge under {root}")
        return 0

    print(f"Found {len(merges)} lens folder merge(s) under {root}:")
    for (camera, old_lens), canonical in sorted(merges.items()):
        print(f"  {camera}/{old_lens} -> {camera}/{canonical}")

    if not dry_run and not args.yes:
        answer = input("Proceed with merge? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Aborted.")
            return 0

    totals = defaultdict(int)
    for (camera, old_lens), canonical in sorted(merges.items()):
        print(f"\nMerging {camera}/{old_lens} -> {canonical}:")
        stats = _merge_lens_tree(root, camera, old_lens, canonical, dry_run)
        for k, v in stats.items():
            totals[k] += v

    manifest_n = _rewrite_manifest(root, merges, dry_run)
    totals["manifest_rewritten"] = manifest_n

    if args.update_db:
        db_n = _update_db_paths(root, merges, dry_run)
        totals["db_updated"] = db_n

    print("\nSummary:")
    for k, v in sorted(totals.items()):
        print(f"  {k}: {v}")
    if dry_run:
        print("\nDry-run only. Re-run with --execute --yes to apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
