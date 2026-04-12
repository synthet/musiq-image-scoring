"""
fix_all_backups.py — Orchestrate complete backup drive cleanup for E:\\Photos and H:\\Photos.

Steps per drive (run in parallel across drives):
  1. Delete macOS ._* junk files
  2. Merge wrongly-named camera folders  (NIKOND90→D90, Z6→Z6ii, Z6II→Z6ii)
  3. Auto-detect and merge decimal lens folders (28.0-105.0mm → 28-105mm, 50.0mm → 50mm)
  4. Run --by-metadata reorganization for each camera folder
  5. Remove empty directories

State is persisted to fix_all_backups_state.json — re-running skips steps already marked "done".

Usage:
  python fix_all_backups.py                    # Dry-run (no files moved)
  python fix_all_backups.py --execute          # Apply all changes
  python fix_all_backups.py --reset            # Clear saved state and re-run all steps
  python fix_all_backups.py --only-drives E    # Only process E:\\ drive
"""

import argparse
import filecmp
import json
import logging
import re
import shutil
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parents[1]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
if str(_script_dir) not in sys.path:
    sys.path.insert(0, str(_script_dir))
from fix_backup_structure import run_fix_by_metadata, _remove_empty_dirs

# ── Configuration ─────────────────────────────────────────────────────────────

DRIVES = {
    "E": Path(r"E:\Photos"),
    "H": Path(r"H:\Photos"),
}

# Camera folder renames: (bad_name, good_name) — applied to each drive root
CAMERA_RENAMES = [
    ("NIKOND90",   "D90"),
    ("NIKON_D90",  "D90"),
    ("NIKOND300",  "D300"),
    ("NIKON_D300", "D300"),
    ("Z6II",       "Z6ii"),   # E:\ uppercase mismatch
    ("Z6",         "Z6ii"),   # Legacy: all Z6 files are actually Z6 II
]

# Camera folders to run by-metadata reorganization on
META_FOLDERS = ["D90", "D300", "Z6ii", "Z6", "Z8", "unknown", "Wedding"]

# Keep state and logs at project root for backward compatibility
STATE_FILE = Path(__file__).resolve().parents[2] / "fix_all_backups_state.json"
LOG_DIR    = Path(__file__).resolve().parents[2] / "logs"

# ── Logging setup ─────────────────────────────────────────────────────────────

LOG_DIR.mkdir(exist_ok=True)
_log_path = LOG_DIR / f"fix_all_backups_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(_log_path, encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ── State helpers ──────────────────────────────────────────────────────────────

_state_lock = threading.Lock()


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_state(state: dict) -> None:
    with _state_lock:
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def step_done(state: dict, key: str) -> bool:
    return state.get(key) == "done"


def mark(state: dict, key: str, status: str) -> None:
    state[key] = status
    save_state(state)


# ── Step implementations ───────────────────────────────────────────────────────

def delete_junk(root: Path, execute: bool) -> int:
    """Delete macOS ._* resource-fork files. Returns count."""
    count = 0
    for f in root.rglob("._*"):
        if not f.is_file():
            continue
        log.info(f"  DEL junk: {f}")
        if execute:
            try:
                f.unlink()
                count += 1
            except Exception as e:
                log.warning(f"  Could not delete {f}: {e}")
        else:
            count += 1
    return count


def _files_identical(a: Path, b: Path) -> bool:
    """True if both paths are regular files with identical size and byte content."""
    try:
        if not a.is_file() or not b.is_file():
            return False
        if a.stat().st_size != b.stat().st_size:
            return False
        return filecmp.cmp(a, b, shallow=False)
    except OSError:
        return False


def _merge_folder(src: Path, dst: Path, execute: bool) -> tuple[int, int]:
    """Merge src into dst (rename if dst absent, move files if dst exists).
    If a destination file already exists, identical copies are deduplicated (source removed);
    different content is left unchanged and counted as an error.
    Returns (files_moved, errors)."""
    if not src.exists():
        return 0, 0
    moved, errors = 0, 0
    if not dst.exists():
        log.info(f"  RENAME {src.name} -> {dst.name}")
        if execute:
            try:
                src.rename(dst)
                moved += 1
            except Exception as e:
                log.error(f"  Rename failed: {e}")
                errors += 1
        else:
            moved += 1
    else:
        # Merge: move all files from src into dst preserving sub-structure
        for f in list(src.rglob("*")):
            if not f.is_file():
                continue
            rel  = f.relative_to(src)
            dest = dst / rel
            if execute:
                try:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    if dest.exists():
                        if _files_identical(f, dest):
                            log.info(f"  DEDUP {rel} (identical to existing, remove source)")
                            f.unlink()
                            moved += 1
                        else:
                            log.warning(
                                f"  CONFLICT {rel}: destination exists with different content; skipping"
                            )
                            errors += 1
                    else:
                        log.info(f"  MERGE {rel}")
                        shutil.move(str(f), str(dest))
                        moved += 1
                except Exception as e:
                    log.error(f"  Move failed {f}: {e}")
                    errors += 1
            else:
                if dest.exists():
                    if _files_identical(f, dest):
                        log.info(f"  DEDUP {rel} (would remove duplicate source)")
                        moved += 1
                    else:
                        log.warning(
                            f"  CONFLICT {rel}: destination exists with different content (would skip)"
                        )
                        errors += 1
                else:
                    log.info(f"  MERGE {rel}")
                    moved += 1
        if execute:
            # Clean up empty dirs in src
            for d in sorted(src.rglob("*"), key=lambda x: len(x.parts), reverse=True):
                if d.is_dir():
                    try: d.rmdir()
                    except: pass
            try: src.rmdir()
            except: pass
    return moved, errors


def merge_camera_folders(root: Path, execute: bool) -> tuple[int, int]:
    total_moved, total_errors = 0, 0
    for bad_name, good_name in CAMERA_RENAMES:
        src = root / bad_name
        dst = root / good_name
        if src == dst or not src.exists():
            continue
        log.info(f"[camera-merge] {src} -> {dst}")
        m, e = _merge_folder(src, dst, execute)
        total_moved += m
        total_errors += e
    return total_moved, total_errors


def _fmt_focal(s: str) -> str:
    """28.0 → 28, 35.5 → 35.5"""
    try:
        f = float(s)
        return str(int(f)) if f == int(f) else s
    except ValueError:
        return s


def _clean_lens_name(name: str) -> str:
    """Return cleaned lens folder name, or same name if already clean."""
    # zoom range: 28.0-105.0mm
    m = re.match(r"^(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)mm(.*)$", name)
    if m:
        return f"{_fmt_focal(m.group(1))}-{_fmt_focal(m.group(2))}mm{m.group(3)}"
    # prime: 50.0mm
    m = re.match(r"^(\d+(?:\.\d+)?)mm(.*)$", name)
    if m:
        return f"{_fmt_focal(m.group(1))}mm{m.group(2)}"
    return name


def merge_lens_folders(root: Path, execute: bool) -> tuple[int, int]:
    """Auto-detect decimal lens folders anywhere under root and merge to clean names."""
    total_moved, total_errors = 0, 0
    # Collect candidate folders two levels deep (camera/lens/)
    for cam_dir in root.iterdir():
        if not cam_dir.is_dir():
            continue
        for lens_dir in cam_dir.iterdir():
            if not lens_dir.is_dir():
                continue
            clean = _clean_lens_name(lens_dir.name)
            if clean == lens_dir.name:
                continue
            target = cam_dir / clean
            log.info(f"[lens-merge] {lens_dir.name} -> {clean}  (under {cam_dir.name})")
            m, e = _merge_folder(lens_dir, target, execute)
            total_moved += m
            total_errors += e
    return total_moved, total_errors


def run_meta(root: Path, folder: str, execute: bool) -> set:
    """Run by-metadata reorganization on root/folder. Returns set of moved paths."""
    target = root / folder
    if not target.exists():
        log.info(f"[by-meta] Skipping {target} (not found)")
        return set()
    log.info(f"[by-meta] {target}  execute={execute}")
    try:
        return run_fix_by_metadata(
            execute=execute,
            backup=str(root),
            folder=folder,
            verbose=False,
        )
    except Exception as e:
        log.error(f"[by-meta] {target}: {e}")
        raise


def remove_empty(root: Path, execute: bool) -> int:
    """Remove empty directories under root."""
    count = 0
    hidden = {"desktop.ini", "thumbs.db", ".ds_store"}
    for d in sorted(root.rglob("*"), key=lambda x: len(x.parts), reverse=True):
        if d == root or not d.is_dir():
            continue
        # Remove hidden-only content first
        items = list(d.iterdir())
        for f in items:
            if f.is_file() and f.name.lower() in hidden:
                try:
                    if execute:
                        f.unlink()
                except Exception:
                    pass
        try:
            if not any(d.iterdir()):
                log.info(f"  RMDIR {d}")
                if execute:
                    d.rmdir()
                count += 1
        except Exception:
            pass
    return count


# ── Drive orchestration ────────────────────────────────────────────────────────

def run_drive(drive_letter: str, root: Path, state: dict, execute: bool, results: dict) -> None:
    """Run all fix steps for one drive. Called in a thread."""
    d = drive_letter
    drive_results = {}

    def run_step(key: str, description: str, fn):
        full_key = f"{d}_{key}"
        if step_done(state, full_key):
            log.info(f"[{d}] SKIP (already done): {description}")
            drive_results[key] = "skipped"
            return
        log.info(f"[{d}] START: {description}")
        t0 = time.time()
        try:
            result = fn()
            elapsed = time.time() - t0
            log.info(f"[{d}] DONE ({elapsed:.1f}s): {description} -> {result}")
            mark(state, full_key, "done")
            drive_results[key] = ("done", result)
        except Exception as e:
            elapsed = time.time() - t0
            log.error(f"[{d}] FAILED ({elapsed:.1f}s): {description}: {e}", exc_info=True)
            mark(state, full_key, "failed")
            drive_results[key] = ("failed", str(e))

    if not root.exists():
        log.warning(f"[{d}] Drive not found: {root}. Skipping all steps.")
        results[d] = {"_error": f"{root} not found"}
        return

    run_step("junk",      f"Delete ._* junk files",           lambda: delete_junk(root, execute))
    run_step("cam_merge", f"Merge camera folder names",        lambda: merge_camera_folders(root, execute))
    run_step("lens_merge",f"Merge decimal lens folder names",  lambda: merge_lens_folders(root, execute))
    for folder in META_FOLDERS:
        run_step(f"meta_{folder.lower()}", f"By-metadata: {folder}",
                 lambda f=folder: run_meta(root, f, execute))
    run_step("empty_dirs",f"Remove empty directories",         lambda: remove_empty(root, execute))

    results[d] = drive_results


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fix all backup folder structures on E:\\ and H:\\")
    parser.add_argument("--execute",     action="store_true", help="Apply changes (default: dry-run)")
    parser.add_argument("--reset",       action="store_true", help="Clear saved state before running")
    parser.add_argument("--only-drives", default="",          help="Comma-separated drive letters, e.g. E  or  E,H")
    args = parser.parse_args()

    if args.reset and STATE_FILE.exists():
        STATE_FILE.unlink()
        log.info("State file cleared.")

    state   = load_state()
    results = {}

    drives_to_run = (
        {k: v for k, v in DRIVES.items() if k in args.only_drives.upper().split(",")}
        if args.only_drives else DRIVES
    )

    mode = "EXECUTE" if args.execute else "DRY-RUN"
    log.info("=" * 70)
    log.info(f"  fix_all_backups  --  {mode}")
    log.info(f"  Drives: {', '.join(f'{k}:{v}' for k, v in drives_to_run.items())}")
    log.info(f"  Log: {_log_path}")
    log.info("=" * 70)

    if args.execute:
        confirm = input("\n  WARNING: This will move/delete files on backup drives.\n  Type 'yes' to confirm: ")
        if confirm.strip().lower() != "yes":
            print("  Aborted.")
            sys.exit(0)

    threads = []
    for letter, root in drives_to_run.items():
        t = threading.Thread(
            target=run_drive,
            args=(letter, root, state, args.execute, results),
            name=f"Drive-{letter}",
            daemon=True,
        )
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # ── Summary report ──────────────────────────────────────────────────────
    log.info("\n" + "=" * 70)
    log.info(f"  SUMMARY  ({mode})")
    log.info("=" * 70)
    all_ok = True
    for letter, drive_res in results.items():
        log.info(f"\n  Drive {letter}:\\")
        for step, outcome in drive_res.items():
            if isinstance(outcome, tuple):
                status, detail = outcome
                icon = "[ok]" if status == "done" else "[fail]"
                log.info(f"    {icon} {step}: {status}  ({detail})")
                if status == "failed":
                    all_ok = False
            else:
                log.info(f"    - {step}: {outcome}")

    log.info("\n" + "=" * 70)
    if all_ok:
        log.info(f"  All steps completed.  Log: {_log_path}")
    else:
        log.info(f"  Some steps FAILED — re-run to retry.  Log: {_log_path}")
    log.info("=" * 70)


if __name__ == "__main__":
    main()
