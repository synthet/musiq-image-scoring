#!/usr/bin/env python3
"""Move lowest-ranked export JPGs to a _culled subfolder (keeps N best)."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from modules import paths as pathutil

_DEFAULT_CSV = _REPO / "output" / "A23_export_scores.csv"
_DEFAULT_REVIEWS = _REPO / "data" / "editorial" / "a32_anhinga_reviews.json"


def _editorial_for_stem(stem: str, editorial: dict) -> dict:
    return (editorial.get("images") or {}).get(stem) or {}


def _rank_score(row: dict, editorial: dict) -> float:
    sg = float(row.get("score_general") or row.get("score") or 0)
    stem = Path(str(row.get("export_disk_path") or row.get("file_name") or "")).stem
    ed = _editorial_for_stem(stem, editorial)
    bonus = 0.0
    if ed.get("carousel_slide"):
        bonus += 0.35
    r = ed.get("top_pick_rank")
    if r:
        bonus += max(0, (6 - int(r)) * 0.08)
    return sg + bonus


def _must_keep(stem: str, editorial: dict) -> bool:
    ed = _editorial_for_stem(stem, editorial)
    return bool(ed.get("carousel_slide") or ed.get("top_pick_rank"))


def _apply_keep_only_stems(
    folder_local: str, culled_dir: str, keep_stems: list[str], dry_run: bool
) -> None:
    """Move every JPG in folder except keep_stems to _culled."""
    keep_names = {f"{s}.jpg" for s in keep_stems}
    print(f"Keeping {len(keep_names)} files: {', '.join(keep_stems)}")
    if dry_run:
        for name in sorted(os.listdir(folder_local)):
            if not name.lower().endswith(".jpg"):
                continue
            action = "KEEP" if name in keep_names else "CULL"
            print(f"  [{action}] {name}")
        print("(dry-run: no files moved)")
        return

    os.makedirs(culled_dir, exist_ok=True)
    for name in sorted(os.listdir(folder_local)):
        if not name.lower().endswith(".jpg"):
            continue
        if name in keep_names:
            continue
        src = os.path.join(folder_local, name)
        dest = os.path.join(culled_dir, name)
        if os.path.isfile(dest):
            os.remove(dest)
        shutil.move(src, dest)
        print(f"Moved -> {dest}")


def _apply_explicit_cull_plan(folder_local: str, culled_dir: str, editorial: dict, dry_run: bool) -> bool:
    """Use reviews.cull_to_twenty when present (exact reject/restore lists)."""
    plan = editorial.get("cull_to_twenty")
    if not plan:
        return False

    reject = [f"{s}.jpg" for s in plan.get("reject_stems", [])]
    restore = [f"{s}.jpg" for s in plan.get("restore_from_culled_stems", [])]

    print("Using explicit cull_to_twenty plan from reviews JSON")
    print(f"  Reject ({len(reject)}): {', '.join(plan.get('reject_stems', []))}")
    print(f"  Restore ({len(restore)}): {', '.join(plan.get('restore_from_culled_stems', []))}")

    if dry_run:
        print("(dry-run: no files moved)")
        return True

    os.makedirs(culled_dir, exist_ok=True)
    for name in reject:
        src = os.path.join(folder_local, name)
        if os.path.isfile(src):
            dest = os.path.join(culled_dir, name)
            shutil.move(src, dest)
            print(f"Moved -> {dest}")
    for name in restore:
        src = os.path.join(culled_dir, name)
        if os.path.isfile(src):
            dest = os.path.join(folder_local, name)
            shutil.move(src, dest)
            print(f"Restored -> {dest}")
    return True


def main() -> int:
    p = argparse.ArgumentParser(description="Cull export folder to top N JPGs by score + editorial")
    p.add_argument("--folder", default=r"D:\Photos\Export\2026\A23")
    p.add_argument("--csv", default=str(_DEFAULT_CSV))
    p.add_argument("--reviews", default=str(_DEFAULT_REVIEWS))
    p.add_argument("--keep", type=int, default=20, help="Target count when using score-based cull")
    p.add_argument(
        "--keep-top",
        type=int,
        default=None,
        metavar="N",
        help="Keep only N carousel/top files (overrides --keep; uses --keep-stems or reviews keep_top_carousel)",
    )
    p.add_argument(
        "--keep-stems",
        nargs="*",
        default=None,
        help="DSC stems to keep in folder (e.g. DSC_0772 DSC_0698)",
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--explicit-plan",
        action="store_true",
        default=True,
        help="Prefer cull_to_twenty from reviews JSON when defined (default: on)",
    )
    p.add_argument("--no-explicit-plan", action="store_false", dest="explicit_plan")
    args = p.parse_args()

    folder_local = pathutil.to_wsl(args.folder) if os.name != "nt" else (pathutil.to_windows(args.folder) or args.folder)
    culled_dir = os.path.join(folder_local, "_culled")

    editorial = {}
    if args.reviews and Path(args.reviews).is_file():
        with open(args.reviews, encoding="utf-8") as f:
            editorial = json.load(f)

    if args.keep_top is not None or args.keep_stems:
        carousel = editorial.get("keep_top_carousel") or {}
        stems = list(args.keep_stems or carousel.get("keep_stems") or [])
        if args.keep_top is not None:
            stems = stems[: args.keep_top]
        if not stems:
            raise SystemExit("No stems to keep: pass --keep-stems or define keep_top_carousel in reviews JSON")
        _apply_keep_only_stems(folder_local, culled_dir, stems, args.dry_run)
        return 0

    if args.explicit_plan and editorial.get("cull_to_twenty"):
        return 0 if _apply_explicit_cull_plan(folder_local, culled_dir, editorial, args.dry_run) else 1

    with open(args.csv, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    ranked: list[tuple[float, str, dict]] = []
    for row in rows:
        export_path = row.get("export_disk_path") or ""
        if not export_path:
            stem = Path(row.get("file_name", "")).stem
            export_path = os.path.join(folder_local, stem + ".jpg")
        ranked.append((_rank_score(row, editorial), export_path, row))

    keep_n = max(1, args.keep)
    by_score = sorted(ranked, key=lambda x: float(x[2].get("score_general") or x[2].get("score") or 0), reverse=True)
    must = [e for e in ranked if _must_keep(Path(e[1]).stem, editorial)]
    keepers: list[tuple] = []
    seen_paths: set[str] = set()
    for e in must:
        p = os.path.normpath(e[1])
        if p not in seen_paths:
            keepers.append(e)
            seen_paths.add(p)
    for e in by_score:
        if len(keepers) >= keep_n:
            break
        p = os.path.normpath(e[1])
        if p not in seen_paths:
            keepers.append(e)
            seen_paths.add(p)

    keep_paths = seen_paths
    cull = [r for r in ranked if os.path.normpath(r[1]) not in keep_paths]
    reject_n = sum(1 for r in keepers if _editorial_for_stem(Path(r[1]).stem, editorial).get("reject_priority"))

    print(f"Folder: {folder_local}")
    print(f"Keeping {len(keep_paths)} / {len(ranked)} (editorial must-keep: {len(must)}, reject-flagged in keep set: {reject_n})")
    print("--- KEEP ---")
    for score, path, row in sorted(
        [r for r in ranked if os.path.normpath(r[1]) in keep_paths],
        key=lambda x: x[0],
        reverse=True,
    ):
        stem = Path(path).stem
        print(f"  {score:.4f}  {stem}")
    print("--- CULL ---")
    for score, path, row in cull:
        stem = Path(path).stem
        print(f"  {score:.4f}  {stem}")

    if args.dry_run:
        print("(dry-run: no files moved)")
        return 0

    os.makedirs(culled_dir, exist_ok=True)
    for _score, path, _row in cull:
        if not os.path.isfile(path):
            alt = pathutil.to_windows(path) if pathutil.is_wsl_path(path) else pathutil.to_wsl(path)
            if alt and os.path.isfile(alt):
                path = alt
            else:
                print(f"WARN missing: {path}")
                continue
        dest = os.path.join(culled_dir, os.path.basename(path))
        shutil.move(path, dest)
        print(f"Moved -> {dest}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
