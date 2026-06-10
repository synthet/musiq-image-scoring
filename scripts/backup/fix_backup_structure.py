"""
fix_backup_structure.py — Reorganize backup drive to match source or EXIF metadata

=============================================================================
OVERVIEW
=============================================================================
Fixes mismatched folder structures on a backup drive (e.g. E:\\Photos) when
files are in wrong locations. Two modes: mirror the source structure, or
reorganize by EXIF metadata (camera, lens, year, date). Dry-run by default;
use --execute to apply changes.

=============================================================================
MODE 1: MIRROR SOURCE (default)
=============================================================================
Makes the backup folder structure match the source (e.g. D:\\Photos).

How it works:
  - Scans source and backup for image files
  - Matches files by (filename, size); uses SHA256 hash when multiple candidates
  - Moves misplaced backup files to paths mirroring source
  - Fuzzy size matching (1% or 100KB tolerance) handles Exif edits that change size

Example:
  Source:  D:\\Photos\\Z8\\180-600mm\\2025\\2025-11-16\\DSC_001.NEF
  Backup:  E:\\Photos\\Z8\\2025\\DSC_001.NEF  (wrong: year as sibling of lens)
  Result:  E:\\Photos\\Z8\\180-600mm\\2025\\2025-11-16\\DSC_001.NEF

Requires: --source and --backup (defaults: D:\\Photos, E:\\Photos)

=============================================================================
MODE 2: BY METADATA (--by-metadata)
=============================================================================
Reorganizes backup using EXIF metadata. No source needed. Each file is moved
to {camera}/{lens}/{year}/{date}/filename based on its embedded metadata.

How it works:
  - Scans backup only
  - Reads Model, LensModel, DateTimeOriginal (or CreateDate) via exiftool
  - Derives folder names: camera (e.g. Z8, Z6ii, R5), lens (e.g. 180-600mm)
  - Builds target path and moves if different from current path

Example:
  File:    E:\\Photos\\Z8\\2025\\DSC_001.NEF
  EXIF:    Model=Nikon Z 8, LensModel=Nikon Z 180-600mm, DateTime=2025:11:16
  Result:  E:\\Photos\\Z8\\180-600mm\\2025\\2025-11-16\\DSC_001.NEF

Requires: exiftool (https://exiftool.org/). Works even when Exif was edited
(no size/hash matching).

=============================================================================
COMMON BEHAVIOR (both modes)
=============================================================================
- XMP sidecars (.xmp) are moved with their images
- Empty directories are removed after moves
- Log file written: fix_structure_*.log or fix_metadata_*.log
- Confirmation prompt before --execute

Supported image formats: NEF, NRW, CR2, CR3, ARW, DNG, ORF, RW2, JPG, PNG,
TIFF, HEIC, WebP

=============================================================================
USAGE
=============================================================================
  python fix_backup_structure.py                    # Dry-run, mirror source
  python fix_backup_structure.py --execute          # Apply mirror changes
  python fix_backup_structure.py --by-metadata     # Dry-run, reorganize by EXIF
  python fix_backup_structure.py --by-metadata --execute

  python fix_backup_structure.py --source D:\Photos --backup E:\Photos
  python fix_backup_structure.py --by-metadata --backup F:\MyBackup

  python fix_backup_structure.py --by-metadata --metadata-samples-per-folder 2
  python fix_backup_structure.py --by-metadata --metadata-samples-per-folder 0   # legacy: full EXIF per file

  python fix_backup_structure.py --no-fuzzy         # Require exact size match
  python fix_backup_structure.py --no-hash         # Skip hash for ambiguous matches
  python fix_backup_structure.py --verbose          # Show per-file skip reasons
  python fix_backup_structure.py --folder Wedding   # Only process E:\Photos\Wedding
  python fix_backup_structure.py --with-orphans     # Also reorganize orphan backup files by EXIF

=============================================================================
ARGUMENTS
=============================================================================
  --execute       Actually move files (default: dry-run only)
  --by-metadata   Use EXIF to build structure instead of mirroring source
  --source PATH   Source folder for mirror mode (default: D:\\Photos)
  --backup PATH   Backup folder (default: E:\\Photos)
  --no-fuzzy      Disable size tolerance (mirror mode); require exact size
  --no-hash       Skip SHA256 verification when multiple filename+size matches
  --verbose       Print per-file skip/match decisions for debugging
  --folder NAME   Only process a specific subfolder of backup (e.g. Wedding, Z8\\2025)
  --metadata-samples-per-folder N  By-metadata: sample N images per directory for camera/lens (default 3); 0=full read per file
  --with-orphans  After mirror mode, also reorganize by EXIF files with no source match
"""
import argparse
import atexit
import json
import os
import re
import subprocess
import sys
import shutil
import threading
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Add project root to path (script is in scripts/backup/)
_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import modules.utils as utils
from modules.camera_folder_name import camera_folder_from_exif_model
from modules.lens_folder_name import UNKNOWN_LENS_FOLDER, lens_folder_from_exif_model

_EXIFTOOL_PATH = shutil.which("exiftool") or shutil.which("C:\\Program Files\\XnViewMP\\AddOn\\exiftool.exe")

# Image extensions to process (XMP sidecars moved with their images)
IMAGE_EXTS = {
    ".jpg", ".jpeg", ".png", ".nef", ".nrw", ".dng", ".cr2", ".cr3",
    ".arw", ".orf", ".rw2", ".tiff", ".tif", ".heic", ".webp",
}

# By-metadata: read full EXIF on up to this many files per directory for camera/lens consensus;
# shoot dates are read in batches for all files in that directory. Set to 0 to use one full read per file (legacy).
METADATA_FOLDER_SAMPLES_DEFAULT = 3
_DATETIME_BATCH_CHUNK = 150

# ── Persistent EXIF cache ─────────────────────────────────────────────────────
# Key: "<abs_path>|<mtime_ns>|<size>"  →  {Model, LensModel, DateTimeOriginal}
# Survives re-runs; auto-invalidates when a file moves (path changes).
_EXIF_CACHE_PATH = Path(__file__).parent / "logs" / "exif_cache.json"
_exif_cache: dict = {}
_exif_cache_lock = threading.Lock()
_exif_cache_dirty = 0
_EXIF_CACHE_FLUSH_EVERY = 200  # flush to disk after this many new entries


def _load_exif_cache() -> None:
    global _exif_cache
    try:
        _EXIF_CACHE_PATH.parent.mkdir(exist_ok=True)
        if _EXIF_CACHE_PATH.exists():
            _exif_cache = json.loads(_EXIF_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        _exif_cache = {}


def _flush_exif_cache() -> None:
    try:
        _EXIF_CACHE_PATH.write_text(
            json.dumps(_exif_cache, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass


def _cache_key(path: Path) -> str | None:
    """Return cache lookup key for path, or None if stat fails."""
    try:
        st = path.stat()
        return f"{path}|{st.st_mtime_ns}|{st.st_size}"
    except OSError:
        return None


_load_exif_cache()
atexit.register(_flush_exif_cache)


def _normalize_root(p: str) -> Path:
    """Normalize drive (E:, E:\\) or folder (E:\\Photos) path to Path."""
    p = p.strip().rstrip("\\/")
    if len(p) == 2 and p[1] == ":":
        return Path(p + "\\")
    return Path(p)


def format_size(size_bytes: int) -> str:
    """Human-readable file size."""
    val = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB"]:
        if abs(val) < 1024.0:
            return f"{val:.1f} {unit}"
        val /= 1024.0
    return f"{val:.1f} TB"


def scan_directory(root: Path, exts: set[str]) -> dict[str, tuple[Path, int]]:
    """Scan directory for files with given extensions. Returns rel_path -> (full_path, size)."""
    result = {}
    root = root.resolve()
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in exts:
            try:
                rel = path.relative_to(root)
                result[str(rel).replace("\\", "/")] = (path, path.stat().st_size)
            except ValueError:
                pass
    return result


def build_backup_index(
    backup_root: Path, exts: set[str]
) -> tuple[dict[tuple[str, int], list[Path]], dict[str, list[tuple[Path, int]]]]:
    """Build (filename,size)->[paths] and filename->[(path,size)] for backup files."""
    by_key = defaultdict(list)
    by_name = defaultdict(list)
    for path in backup_root.rglob("*"):
        if path.is_file() and path.suffix.lower() in exts:
            try:
                path.relative_to(backup_root)
                size = path.stat().st_size
                by_key[(path.name, size)].append(path)
                by_name[path.name].append((path, size))
            except (ValueError, OSError):
                pass
    return dict(by_key), dict(by_name)


def _sanitize_fs(s: str) -> str:
    """Sanitize string for filesystem: remove unsafe chars, collapse spaces."""
    s = re.sub(r'[<>:"/\\|?*]', "", str(s).strip())
    return re.sub(r"\s+", "", s) or "unknown"


def _lens_folder(lens: str) -> str:
    """Extract focal range for folder (parity with gallery ``normalizeLensFolderName``)."""
    if not lens or lens.lower() == "unknown":
        return "unknown"
    result = lens_folder_from_exif_model(lens)
    if result == UNKNOWN_LENS_FOLDER:
        return "unknown"
    return result


def _get_metadata(path: Path) -> dict:
    """Get Model, LensModel, DateTimeOriginal via exiftool (with persistent cache)."""
    global _exif_cache_dirty
    out = {"Model": "unknown", "LensModel": "unknown", "DateTimeOriginal": None}
    if not _EXIFTOOL_PATH or not path.exists():
        return out

    # Cache lookup
    key = _cache_key(path)
    if key:
        with _exif_cache_lock:
            cached = _exif_cache.get(key)
        if cached is not None:
            return cached

    try:
        # Fetch multiple lens tags as fallbacks (LensModel, Lens, LensID, LensType)
        cmd = [
            _EXIFTOOL_PATH,
            "-T",
            "-Model",
            "-LensModel",
            "-Lens",
            "-LensID",
            "-LensType",
            "-DateTimeOriginal",
            "-CreateDate",
            str(path),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return out
        parts = [p.strip() for p in r.stdout.strip().split("\t")]
        if len(parts) >= 1 and parts[0] and parts[0] != "-":
            out["Model"] = parts[0]

        # Lens fallback logic: LensModel > Lens > LensID > LensType
        lens_candidates = parts[1:5]
        for val in lens_candidates:
            if val and val != "-":
                out["LensModel"] = val
                break

        # Date logic
        for i in range(5, len(parts)):
            if parts[i] and parts[i] != "-":
                out["DateTimeOriginal"] = parts[i]
                break
    except Exception:
        pass

    # Store in cache
    if key:
        with _exif_cache_lock:
            _exif_cache[key] = out
            _exif_cache_dirty += 1
            if _exif_cache_dirty >= _EXIF_CACHE_FLUSH_EVERY:
                _flush_exif_cache()
                _exif_cache_dirty = 0

    return out


def _get_datetimes_batch(paths: list[Path]) -> dict[Path, str | None]:
    """One or more exiftool runs: DateTimeOriginal / CreateDate for many paths. Order matches input chunks."""
    out: dict[Path, str | None] = {p: None for p in paths}
    if not paths or not _EXIFTOOL_PATH:
        return out
    for i in range(0, len(paths), _DATETIME_BATCH_CHUNK):
        chunk = paths[i : i + _DATETIME_BATCH_CHUNK]
        cmd = [_EXIFTOOL_PATH, "-T", "-DateTimeOriginal", "-CreateDate"] + [str(p) for p in chunk]
        try:
            r = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                encoding="utf-8",
                errors="replace",
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if r.returncode != 0 or not (r.stdout or "").strip():
            continue
        # exiftool emits one line per file, same order as arguments
        raw_lines = r.stdout.splitlines()
        if len(raw_lines) != len(chunk):
            for p in chunk:
                m = _get_metadata(p)
                out[p] = m.get("DateTimeOriginal")
            continue
        for j, line in enumerate(raw_lines):
            if j >= len(chunk):
                break
            parts = [x.strip() for x in line.split("\t")]
            dt_val = None
            for val in parts:
                if val and val != "-":
                    dt_val = val
                    break
            out[chunk[j]] = dt_val
    return out


def _metadata_target_path(backup_root: Path, path: Path, meta: dict) -> Path:
    """Build target path: {backup}/{camera}/{lens}/{year}/{date}/filename."""
    camera = camera_folder_from_exif_model(meta.get("Model", ""))
    lens = _lens_folder(meta.get("LensModel", ""))
    dt_str = (meta.get("DateTimeOriginal") or "").strip()
    year, date = "unknown", "unknown"
    if dt_str:
        for fmt, n in (("%Y:%m:%d %H:%M:%S", 19), ("%Y:%m:%d", 10), ("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d", 10)):
            try:
                dt = datetime.strptime(dt_str[:n], fmt)
                year = str(dt.year)
                date = dt.strftime("%Y-%m-%d")
                break
            except ValueError:
                continue
    return backup_root / camera / lens / year / date / path.name


def _do_move(src: Path, dest: Path, log, execute: bool, label: str = "") -> bool:
    """Move src -> dest (and XMP sidecar). Returns True on success or dry-run."""
    if execute:
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                dest.unlink()
            shutil.move(str(src), str(dest))
            log.write(f"  -> MOVED{' ' + label if label else ''}\n")

            xmp_src = src.with_suffix(".xmp")
            if not xmp_src.exists():
                xmp_src = src.with_suffix(".XMP")
            if xmp_src.exists():
                xmp_dest = dest.with_suffix(xmp_src.suffix)
                xmp_dest.parent.mkdir(parents=True, exist_ok=True)
                if xmp_dest.exists():
                    xmp_dest.unlink()
                shutil.move(str(xmp_src), str(xmp_dest))
                log.write(f"  -> MOVED sidecar: {xmp_src.name}\n")
            return True
        except Exception as e:
            log.write(f"  -> FAILED: {e}\n")
            return False
    else:
        log.write("  -> Would move\n")
        return True


def _remove_empty_dirs(roots: set[Path], backup_root: Path) -> int:
    """Remove empty parent dirs up to (but not including) backup_root. Returns count."""
    count = 0
    for parent in sorted(roots, key=lambda x: len(x.parts), reverse=True):
        try:
            while parent != backup_root and parent.exists() and not any(parent.iterdir()):
                parent.rmdir()
                count += 1
                parent = parent.parent
        except Exception:
            pass
    return count


def run_fix_by_metadata(
    execute: bool = False,
    backup: str = "E:\\Photos",
    folder: str = "",
    verbose: bool = False,
    metadata_samples_per_folder: int = METADATA_FOLDER_SAMPLES_DEFAULT,
) -> set:
    """Reorganize backup by EXIF: camera > lens > year > date. Returns set of moved source paths.

    When metadata_samples_per_folder > 0, group files by parent directory; read full EXIF on up to
    that many sample files per directory for camera/lens; batch-read dates for all files in the
    directory. When samples disagree on camera/lens, fall back to a full per-file read for that
    directory. Use 0 for legacy behavior (full exiftool read on every file).
    """
    backup_root = _normalize_root(backup)
    scan_root = backup_root / folder if folder else backup_root

    print("=" * 70)
    print(f"  FIX BACKUP BY METADATA - {'EXECUTE MODE' if execute else 'DRY RUN'}")
    print(f"  Backup: {backup_root}")
    if folder:
        print(f"  Folder filter: {folder}  (scanning {scan_root})")
    print(f"  Structure: {{camera}}/{{lens}}/{{year}}/{{date}}/filename")
    if not _EXIFTOOL_PATH:
        print("\n[ERROR] exiftool not found. Install from https://exiftool.org/")
        return set()
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    sys.stdout.flush()

    if not scan_root.exists():
        print(f"\n[ERROR] {scan_root} does not exist.")
        return set()

    print("\n[1/3] Scanning backup...")
    image_files = [
        p for p in scan_root.rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    ]
    print(f"   Found {len(image_files)} image files")

    print("\n[2/3] Reading metadata and computing target paths...")
    if metadata_samples_per_folder > 0:
        print(
            f"   Using up to {metadata_samples_per_folder} sample(s) per folder for camera/lens; "
            "batching date reads per folder."
        )
        sys.stdout.flush()

    moves: list[tuple[Path, Path, int]] = []

    def _cam_lens_key(meta: dict) -> tuple[str, str]:
        return (
            camera_folder_from_exif_model(meta.get("Model", "")),
            _lens_folder(meta.get("LensModel", "")),
        )

    def _append_move_if_needed(path: Path, meta: dict) -> None:
        if not path.exists():
            return
        target = _metadata_target_path(backup_root, path, meta)
        if target.resolve() != path.resolve():
            moves.append((path, target, path.stat().st_size))
            if verbose:
                print(f"   MOVE: {path.relative_to(backup_root)}")
                print(f"      -> {target.relative_to(backup_root)}")
        elif verbose:
            print(f"   OK  : {path.relative_to(backup_root)} (already correct)")

    if metadata_samples_per_folder <= 0:
        for i, path in enumerate(image_files):
            if (i + 1) % 500 == 0 or i == 0:
                print(f"   Processing {i + 1}/{len(image_files)}...")
                sys.stdout.flush()
            if not path.exists():
                continue
            meta = _get_metadata(path)
            _append_move_if_needed(path, meta)
    else:
        by_parent: defaultdict[Path, list[Path]] = defaultdict(list)
        for p in image_files:
            by_parent[p.parent].append(p)

        processed = 0
        total = len(image_files)
        for parent in sorted(by_parent.keys(), key=lambda x: str(x).lower()):
            paths_sorted = sorted(by_parent[parent], key=lambda x: x.name)
            k = min(metadata_samples_per_folder, len(paths_sorted))
            samples = paths_sorted[:k]
            sample_metas = [_get_metadata(p) for p in samples]
            cl_keys = [_cam_lens_key(m) for m in sample_metas]
            use_consensus = k > 0 and len(set(cl_keys)) == 1

            if use_consensus:
                tmpl = sample_metas[0]
                dates_by_path = _get_datetimes_batch(paths_sorted)
                for path in paths_sorted:
                    processed += 1
                    if processed % 500 == 0 or processed == 1:
                        print(f"   Processing {processed}/{total}...")
                        sys.stdout.flush()
                    if not path.exists():
                        continue
                    dts = dates_by_path.get(path)
                    meta = {
                        "Model": tmpl["Model"],
                        "LensModel": tmpl["LensModel"],
                        "DateTimeOriginal": dts,
                    }
                    if not meta["DateTimeOriginal"]:
                        meta = _get_metadata(path)
                    _append_move_if_needed(path, meta)
            else:
                for path in paths_sorted:
                    processed += 1
                    if processed % 500 == 0 or processed == 1:
                        print(f"   Processing {processed}/{total}...")
                        sys.stdout.flush()
                    if not path.exists():
                        continue
                    meta = _get_metadata(path)
                    _append_move_if_needed(path, meta)

    print(f"   Found {len(moves)} files to relocate")

    if not moves:
        print("\n[DONE] All files already in metadata-based structure.")
        return set()

    total_size = sum(m[2] for m in moves)
    print(f"\n[3/3] {'Moving files' if execute else 'Dry-run report'}...")
    print(f"   Total size: {format_size(total_size)}")
    sys.stdout.flush()

    log_name = f"fix_metadata_{'execute' if execute else 'dryrun'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / log_name

    moved_count = 0
    failed = []

    with open(log_path, "w", encoding="utf-8") as log:
        log.write(f"Fix Backup by Metadata - {'EXECUTE' if execute else 'DRY RUN'}\n")
        log.write(f"Date: {datetime.now().isoformat()}\n")
        log.write(f"Backup: {backup_root}\n")
        log.write(f"Files to move: {len(moves)}\n")
        log.write("=" * 80 + "\n\n")

        for i, (src, dest, size) in enumerate(moves, 1):
            if i % 100 == 0:
                print(f"   Processing {i}/{len(moves)}...")
                sys.stdout.flush()

            log.write(f"[{i}/{len(moves)}] {src.name}\n")
            log.write(f"  From: {src}\n")
            log.write(f"  To:   {dest}\n")
            log.write(f"  Size: {format_size(size)}\n")

            if not src.exists():
                log.write(f"  -> SKIPPED (not found): {src.name}\n")
                continue
            ok = _do_move(src, dest, log, execute)
            if execute:
                if ok:
                    moved_count += 1
                else:
                    failed.append((src, "see log"))
            log.write("\n")

        log.write("=" * 80 + "\n")
        log.write("SUMMARY\n")
        if execute:
            log.write(f"  Moved: {moved_count} files\n")
            log.write(f"  Failed: {len(failed)} files\n")
        else:
            log.write(f"  Would move: {len(moves)} files\n")

    moved_paths = {src for src, _, _ in moves}
    if execute and moved_count > 0:
        print("   Cleaning up empty directories...")
        src_parents = {src.parent for src, _, _ in moves}
        print(f"   Removed {_remove_empty_dirs(src_parents, backup_root)} empty directories")

    print(f"\n{'=' * 70}")
    if execute:
        print(f"  MOVED {moved_count} files")
        if failed:
            print(f"  FAILED {len(failed)} files (see log)")
    else:
        print(f"  DRY RUN: Would move {len(moves)} files")
        print(f"\n  Run with --execute to actually move files")
    
    if log_path:
        print(f"\n  Full log: {log_path}")
    print("=" * 70)
    sys.stdout.flush()
    return moved_paths


def run_fix(
    execute: bool = False,
    source: str = "D:\\Photos",
    backup: str = "E:\\Photos",
    use_hash: bool = True,
    fuzzy_size: bool = True,
    folder: str = "",
    verbose: bool = False,
    with_orphans: bool = False,
    metadata_samples_per_folder: int = METADATA_FOLDER_SAMPLES_DEFAULT,
):
    """Mirror source structure onto backup, with optional orphan metadata pass."""
    source_root = _normalize_root(source)
    backup_root = _normalize_root(backup)
    scan_root = backup_root / folder if folder else backup_root

    print("=" * 70)
    print(f"  FIX BACKUP STRUCTURE - {'EXECUTE MODE' if execute else 'DRY RUN'}")
    print(f"  Source: {source_root}")
    print(f"  Backup: {backup_root}")
    if folder:
        print(f"  Folder filter: {folder}  (scanning {scan_root})")
    if with_orphans:
        print(f"  Orphan mode: ON (unmatched backup files will be reorganized by EXIF)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    sys.stdout.flush()

    if not source_root.exists():
        print(f"\n[ERROR] Source {source_root} does not exist.")
        return
    if not scan_root.exists():
        print(f"\n[ERROR] Backup path {scan_root} does not exist. Is the drive connected?")
        return

    print("\n[1/4] Scanning source directory...")
    sys.stdout.flush()
    source_files = scan_directory(source_root, IMAGE_EXTS)
    print(f"   Found {len(source_files)} files in source")

    print("\n[2/4] Scanning backup directory...")
    sys.stdout.flush()
    backup_index, backup_by_name = build_backup_index(scan_root, IMAGE_EXTS)
    backup_paths = set()
    for paths in backup_index.values():
        backup_paths.update(paths)
    print(f"   Found {len(backup_paths)} files in backup{'/' + folder if folder else ''}")

    # Size tolerance for fuzzy match (Exif edits often change size slightly)
    SIZE_TOLERANCE_PCT = 0.01  # 1%
    SIZE_TOLERANCE_BYTES = 100 * 1024  # 100 KB

    print("\n[3/4] Finding misplaced files...")
    sys.stdout.flush()
    moves = []
    seen_backup = set()

    def size_close(src_size: int, cand_size: int) -> bool:
        if src_size == cand_size:
            return True
        if not fuzzy_size:
            return False
        diff = abs(src_size - cand_size)
        return diff <= SIZE_TOLERANCE_BYTES or diff <= src_size * SIZE_TOLERANCE_PCT

    for rel_path, (src_path, size) in source_files.items():
        expected_backup = backup_root / rel_path.replace("/", "\\")
        if expected_backup.exists() and size_close(size, expected_backup.stat().st_size):
            if verbose:
                print(f"   OK  : {rel_path} (already in place)")
            continue

        key = (src_path.name, size)
        # Exact key (filename + size) lookup
        candidates = [p for p in backup_index.get(key, []) if p not in seen_backup]
        src_hash = None  # lazily computed, cached per source file

        # Fallback: Exif edits change file size; try filename-only fuzzy match
        if not candidates and fuzzy_size:
            name_cands = [
                (p, s) for p, s in backup_by_name.get(src_path.name, [])
                if size_close(size, s) and p not in seen_backup
            ]
            if len(name_cands) == 1:
                candidates = [name_cands[0][0]]
                if verbose:
                    print(f"   FUZZY match: {src_path.name} (size diff ok)")
            elif len(name_cands) > 1 and use_hash:
                src_hash = utils.compute_file_hash(str(src_path))
                if src_hash:
                    for p, _ in name_cands:
                        if utils.compute_file_hash(str(p)) == src_hash:
                            candidates = [p]
                            if verbose:
                                print(f"   HASH match: {src_path.name}")
                            break
            elif len(name_cands) > 1:
                if verbose:
                    print(f"   SKIP: {src_path.name} ({len(name_cands)} fuzzy candidates, hash disabled)")

        if not candidates:
            if verbose:
                print(f"   MISS: {rel_path} (not found in backup)")
            continue

        chosen = None
        if len(candidates) == 1:
            chosen = candidates[0]
        elif use_hash and len(candidates) > 1:
            if src_hash is None:
                src_hash = utils.compute_file_hash(str(src_path))
            if not src_hash:
                if verbose:
                    print(f"   SKIP: {src_path.name} (hash failed)")
                continue
            for c in candidates:
                ch = utils.compute_file_hash(str(c))
                if ch == src_hash:
                    chosen = c
                    break
        else:
            chosen = candidates[0]

        if chosen and chosen != expected_backup:
            if verbose:
                print(f"   MOVE: {chosen.name}")
                print(f"      from: {chosen.parent}")
                print(f"        to: {expected_backup.parent}")
            moves.append((chosen, expected_backup, size))
            seen_backup.add(chosen)
        elif chosen and verbose:
            print(f"   OK  : {src_path.name} (chosen == expected)")

    print(f"   Found {len(moves)} files to relocate")

    if not moves and not with_orphans:
        print("\n[DONE] Backup structure already matches source. Nothing to fix.")
        return

    total_size = sum(m[2] for m in moves)
    if moves:
        print(f"\n[4/4] {'Moving files' if execute else 'Dry-run report'}...")
        print(f"   Total size: {format_size(total_size)}")
        sys.stdout.flush()

    if moves:
        log_name = f"fix_structure_{'execute' if execute else 'dryrun'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        log_dir = Path(__file__).parent / "logs"
        log_dir.mkdir(exist_ok=True)
        log_path = log_dir / log_name

        moved_count = 0
        failed = []

        with open(log_path, "w", encoding="utf-8") as log:
            log.write(f"Fix Backup Structure - {'EXECUTE' if execute else 'DRY RUN'}\n")
            log.write(f"Date: {datetime.now().isoformat()}\n")
            log.write(f"Source: {source_root}\n")
            log.write(f"Backup: {backup_root}\n")
            if folder:
                log.write(f"Folder filter: {folder}\n")
            log.write(f"Files to move: {len(moves)}\n")
            log.write("=" * 80 + "\n\n")

            for i, (src, dest, size) in enumerate(moves, 1):
                if i % 100 == 0:
                    print(f"   Processing {i}/{len(moves)}...")
                    sys.stdout.flush()

                log.write(f"[{i}/{len(moves)}] {src.name}\n")
                log.write(f"  From: {src}\n")
                log.write(f"  To:   {dest}\n")
                log.write(f"  Size: {format_size(size)}\n")

                ok = _do_move(src, dest, log, execute)
                if execute:
                    if ok:
                        moved_count += 1
                    else:
                        failed.append((src, "see log"))
                log.write("\n")

            log.write("=" * 80 + "\n")
            log.write("SUMMARY\n")
            if execute:
                log.write(f"  Moved: {moved_count} files\n")
                log.write(f"  Failed: {len(failed)} files\n")
            else:
                log.write(f"  Would move: {len(moves)} files\n")

        if execute and moved_count > 0:
            print("   Cleaning up empty directories...")
            sys.stdout.flush()
            src_parents = {src.parent for src, _, _ in moves}
            print(f"   Removed {_remove_empty_dirs(src_parents, backup_root)} empty directories")
    else:
        moved_count = 0
        failed = []
        log_path = None

    # --- Orphan report: backup files matched to no source entry ---
    matched_backup = seen_backup  # set of backup paths consumed by mirror logic
    orphan_files = [
        p for p in backup_paths if p not in matched_backup
    ]
    if orphan_files:
        print(f"\n  ORPHANS: {len(orphan_files)} backup files have no source counterpart")
        # Group by top-level subfolder for a concise report
        by_folder: dict[str, int] = defaultdict(int)
        for p in orphan_files:
            try:
                rel = p.relative_to(backup_root)
                top = rel.parts[0] if rel.parts else "(root)"
            except ValueError:
                top = "(root)"
            by_folder[top] += 1
        for top, cnt in sorted(by_folder.items()):
            print(f"    {top}/  - {cnt} orphan file(s)")
        if with_orphans:
            print(f"\n  Running metadata pass on {len(orphan_files)} orphan files...")
            # Write orphan list to a temp file so run_fix_by_metadata can process a virtual root
            # Instead, we call a targeted metadata pass per orphan top-level folder
            for top in sorted(by_folder.keys()):
                orphan_top = backup_root / top
                if orphan_top.exists():
                    print(f"\n  --- Metadata pass: {top}/ ---")
                    run_fix_by_metadata(
                        execute=execute,
                        backup=str(backup_root),
                        folder=top,
                        verbose=verbose,
                        metadata_samples_per_folder=metadata_samples_per_folder,
                    )
        else:
            print(f"  Tip: re-run with --with-orphans to reorganize them by EXIF metadata")
            print(f"       or: --folder Wedding --by-metadata  to target a single folder")

    print(f"\n{'=' * 70}")
    if execute:
        print(f"  MOVED {moved_count} files")
        if failed:
            print(f"  FAILED {len(failed)} files (see log)")
    else:
        print(f"  DRY RUN: Would move {len(moves)} files")
        print(f"\n  Run with --execute to actually move files")
    print(f"\n  Full log: {log_path}")
    print("=" * 70)
    sys.stdout.flush()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fix backup folder structure (mirror source or reorganize by EXIF)"
    )
    parser.add_argument("--execute", action="store_true", help="Actually move files (default: dry-run)")
    parser.add_argument("--by-metadata", action="store_true", help="Use EXIF (camera/lens/year/date) instead of mirroring source")
    parser.add_argument("--verbose", action="store_true", help="Print per-file skip/match decisions")
    parser.add_argument("--folder", default="", help="Only process this subfolder of backup (e.g. Wedding, Z8\\2025)")
    parser.add_argument(
        "--metadata-samples-per-folder",
        type=int,
        default=METADATA_FOLDER_SAMPLES_DEFAULT,
        metavar="N",
        help=(
            "By-metadata: read full EXIF on up to N files per parent folder for camera/lens; "
            "dates batched for all files in that folder. Use 0 for one full exiftool read per file."
        ),
    )
    parser.add_argument("--with-orphans", action="store_true", help="After mirror mode, reorganize files with no source match by EXIF")
    parser.add_argument("--source", default="D:\\Photos", help="Source folder for mirror mode (default: D:\\Photos)")
    parser.add_argument("--backup", default="E:\\Photos", help="Backup folder (default: E:\\Photos)")
    parser.add_argument("--no-hash", action="store_true", help="Skip hash verification for ambiguous matches")
    parser.add_argument("--no-fuzzy", action="store_true", help="Require exact size match (disable Exif-tolerant matching)")
    args = parser.parse_args()

    if args.execute:
        msg = f"This will MOVE files on {args.backup}"
        if args.folder:
            msg += f" (folder: {args.folder})"
        msg += " by EXIF metadata!" if args.by_metadata else f" to match {args.source} structure!"
        if getattr(args, 'with_orphans', False) and not args.by_metadata:
            msg += " Orphan files will also be reorganized by EXIF."
        print(f"\n  WARNING: {msg}")
        confirm = input("  Type 'yes' to confirm: ")
        if confirm.strip().lower() != "yes":
            print("  Aborted.")
            sys.exit(0)

    if args.by_metadata:
        run_fix_by_metadata(
            execute=args.execute,
            backup=args.backup,
            folder=args.folder,
            verbose=args.verbose,
            metadata_samples_per_folder=args.metadata_samples_per_folder,
        )
    else:
        run_fix(
            execute=args.execute,
            source=args.source,
            backup=args.backup,
            use_hash=not args.no_hash,
            fuzzy_size=not args.no_fuzzy,
            folder=args.folder,
            verbose=args.verbose,
            with_orphans=getattr(args, 'with_orphans', False),
            metadata_samples_per_folder=args.metadata_samples_per_folder,
        )
