#!/usr/bin/env python3
"""
Remove stale log files from the project.
Targets: logs/ directory, project root *.log, .cursor/debug.log, Firebird logs.

Run from project root. Does not require WSL or database.
"""

import argparse
import glob
import os
import sys
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))

# Log locations relative to project root
LOG_LOCATIONS = [
    ("logs", "*.log"),           # project root logs (fix_all_backups)
    ("scripts/backup/logs", "*.log"),  # fix_backup_structure logs
    ("logs", "*.txt"),           # console logs
    (".", "debug.log"),         # root debug.log (fallback)
    (".", "webui.log"),
    (".", "webui.log.*"),       # RotatingFileHandler backups (webui.log.1, …)
    (".", "process_missing_stacks.log"),
    ("Firebird", "firebird.log"),
    ("FirebirdLinux", "**/firebird.log"),  # nested under Firebird-5.x/
]

# .cursor/debug.log uses config; we add it explicitly
CURSOR_DEBUG = os.path.join(".cursor", "debug.log")


def get_log_paths() -> list[tuple[str, float]]:
    """Return list of (path, mtime) for all candidate log files."""
    os.chdir(PROJECT_ROOT)
    results = []
    seen = set()

    for base, pattern in LOG_LOCATIONS:
        base_path = os.path.join(PROJECT_ROOT, base)
        if "*" in pattern:
            if not os.path.isdir(base_path):
                continue
            full_pattern = os.path.join(base_path, pattern)
        else:
            full_pattern = os.path.join(base_path, pattern) if base != "." else os.path.join(PROJECT_ROOT, pattern)

        for path in glob.glob(full_pattern, recursive="**" in full_pattern):
            if os.path.isfile(path) and path not in seen:
                seen.add(path)
                try:
                    mtime = os.path.getmtime(path)
                    results.append((path, mtime))
                except OSError:
                    pass

    # .cursor/debug.log (single file, no glob)
    cursor_path = os.path.join(PROJECT_ROOT, CURSOR_DEBUG)
    if os.path.isfile(cursor_path) and cursor_path not in seen:
        try:
            results.append((cursor_path, os.path.getmtime(cursor_path)))
        except OSError:
            pass

    return results


def format_size(path: str) -> str:
    try:
        n = os.path.getsize(path)
        if n >= 1024 * 1024:
            return f"{n / (1024 * 1024):.1f} MB"
        if n >= 1024:
            return f"{n / 1024:.1f} KB"
        return f"{n} B"
    except OSError:
        return "?"


def cleanup_job_image_actions(days: int, dry_run: bool = False) -> int:
    """Remove old job_image_actions rows older than *days*.

    Returns the number of rows deleted (or that would be deleted in dry-run mode).
    Uses the config value ``processing.job_action_log_retention_days`` as override
    when *days* is not explicitly provided by the caller.
    """
    try:
        sys.path.insert(0, PROJECT_ROOT)
        from modules.config import get_config_value
        from modules.db_connector import get_connector

        retention = get_config_value("processing.job_action_log_retention_days", default=days)
        conn = get_connector()

        # Count rows to be removed
        count_sql = (
            "SELECT COUNT(*) FROM job_image_actions "
            "WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '? days'"
        )
        # Postgres requires proper interval syntax; use parameterised query
        count_sql = "SELECT COUNT(*) FROM job_image_actions WHERE created_at < CURRENT_TIMESTAMP - make_interval(days => ?)"
        rows = conn.execute(count_sql, [retention])
        total = rows[0][0] if rows else 0

        if total == 0:
            print(f"No job_image_actions rows older than {retention} days.")
            return 0

        label = "Would remove" if dry_run else "Removing"
        print(f"\n{label} {total} job_image_actions row(s) older than {retention} days.")

        if not dry_run:
            delete_sql = "DELETE FROM job_image_actions WHERE created_at < CURRENT_TIMESTAMP - make_interval(days => ?)"
            conn.execute(delete_sql, [retention])
            print(f"  Deleted {total} row(s) from job_image_actions.")

        return total
    except ImportError:
        print("  Skipping DB cleanup (modules not available).")
        return 0
    except Exception as exc:
        print(f"  DB cleanup error: {exc}", file=sys.stderr)
        return 0


def main():
    parser = argparse.ArgumentParser(
        description="Remove stale log files. By default removes logs older than 7 days."
    )
    parser.add_argument(
        "-n", "--dry-run",
        action="store_true",
        help="Show what would be removed without deleting",
    )
    parser.add_argument(
        "-d", "--days",
        type=int,
        default=7,
        metavar="N",
        help="Remove logs older than N days (default: 7)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Remove all logs regardless of age",
    )
    args = parser.parse_args()

    cutoff = datetime.now() - timedelta(days=args.days) if not args.all else datetime.min
    cutoff_ts = cutoff.timestamp()

    paths = get_log_paths()
    to_remove = [(p, mt) for p, mt in paths if mt < cutoff_ts]

    if not to_remove:
        print("No stale logs found.")
        return 0

    total_size = 0
    for path, mtime in to_remove:
        try:
            total_size += os.path.getsize(path)
        except OSError:
            pass

    label = "Would remove" if args.dry_run else "Removing"
    print(f"{label} {len(to_remove)} log(s) (~{total_size / 1024:.1f} KB):\n")
    for path, mtime in sorted(to_remove):
        rel = os.path.relpath(path, PROJECT_ROOT)
        age = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        size = format_size(path)
        print(f"  {rel}  ({age}, {size})")

    if not args.dry_run:
        print()
        for path, _ in to_remove:
            try:
                os.remove(path)
                print(f"  Removed: {os.path.relpath(path, PROJECT_ROOT)}")
            except OSError as e:
                print(f"  Error removing {path}: {e}", file=sys.stderr)
                sys.exit(1)
        print(f"\nCleaned {len(to_remove)} log(s).")
    else:
        print("\nDry run - no files removed. Run without -n to apply.")

    # DB cleanup: prune old job_image_actions rows
    cleanup_job_image_actions(days=args.days, dry_run=args.dry_run)

    return 0


if __name__ == "__main__":
    sys.exit(main())
