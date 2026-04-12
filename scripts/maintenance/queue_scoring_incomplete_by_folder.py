#!/usr/bin/env python3
"""
List incomplete images (same criteria as db.get_incomplete_records / _incomplete_images_where_sql),
grouped by registered leaf folder (images.folder_id -> folders.path), and optionally enqueue
one POST /api/scoring/start job per distinct folder with skip_existing=true, force_rescore=false.

Run from repo root with the app environment (see AGENTS.md / python-wsl-webapp-env.mdc).

Examples:

  # Table: folder_path -> incomplete image count (+ orphans with null folder_id)
  python scripts/maintenance/queue_scoring_incomplete_by_folder.py

  # CSV of every incomplete row (id, file_path, folder_path)
  python scripts/maintenance/queue_scoring_incomplete_by_folder.py --csv incomplete.csv

  # Enqueue up to 10 scoring jobs (folders with the most incomplete images first; override with --max-folders)
  python scripts/maintenance/queue_scoring_incomplete_by_folder.py --enqueue --fetch-status

  # Dry-run enqueue (print POST bodies only)
  python scripts/maintenance/queue_scoring_incomplete_by_folder.py --enqueue --dry-run

  # Queue every folder (no cap)
  python scripts/maintenance/queue_scoring_incomplete_by_folder.py --enqueue --max-folders 0

  # Monitor current scoring job (no DB)
  python scripts/maintenance/queue_scoring_incomplete_by_folder.py --status-only
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def _get_json(url: str, timeout: float = 30.0) -> dict[str, Any]:
    with urlopen(url, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def _post_json(url: str, body: dict[str, Any], timeout: float = 120.0) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8")
    req = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def _folder_aggregates(conn) -> tuple[list[dict[str, Any]], int]:
    """Return (rows per folder_path with incomplete_count), orphan_count (folder_id IS NULL)."""
    from modules import db

    inc = db._incomplete_images_where_sql("i")
    q_groups = f"""
        SELECT f.path AS folder_path, COUNT(*) AS incomplete_count
        FROM images i
        JOIN folders f ON f.id = i.folder_id
        WHERE {inc}
        GROUP BY f.path
        ORDER BY COUNT(*) DESC, f.path
    """
    rows = [dict(r) for r in conn.query(q_groups)]

    q_orphans = f"""
        SELECT COUNT(*) AS c FROM images i WHERE i.folder_id IS NULL AND {inc}
    """
    one = conn.query_one(q_orphans)
    orphan_count = int(one["c"]) if one and one.get("c") is not None else 0
    return rows, orphan_count


def _list_images(conn, limit: int | None) -> list[dict[str, Any]]:
    from modules import db

    inc = db._incomplete_images_where_sql("i")
    lim = f"FETCH FIRST {int(limit)} ROWS ONLY" if limit and limit > 0 else ""
    q = f"""
        SELECT i.id, i.file_path, f.path AS folder_path
        FROM images i
        JOIN folders f ON f.id = i.folder_id
        WHERE {inc}
        ORDER BY f.path, i.id
        {lim}
    """
    return [dict(r) for r in conn.query(q)]


def main() -> int:
    from modules import db

    p = argparse.ArgumentParser(
        description="List incomplete images by leaf folder and optionally queue per-folder scoring via POST /api/scoring/start.",
    )
    p.add_argument(
        "--csv",
        metavar="FILE",
        help="Write per-image incomplete rows (id, file_path, folder_path) to CSV.",
    )
    p.add_argument(
        "--csv-limit",
        type=int,
        default=None,
        help="Max rows for --csv (default: all matching rows).",
    )
    p.add_argument(
        "--enqueue",
        action="store_true",
        help="POST /api/scoring/start for each distinct folder_path with incomplete images.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="With --enqueue, print actions only (no HTTP POST).",
    )
    p.add_argument(
        "--max-folders",
        type=int,
        default=None,
        metavar="N",
        help=(
            "With --enqueue: max scoring jobs to queue (folders with most incomplete images first). "
            "Default when omitted: 10. Use 0 for no limit (all folders)."
        ),
    )
    p.add_argument(
        "--delay-seconds",
        type=float,
        default=0.0,
        help="Sleep between enqueue POSTs (default 0).",
    )
    p.add_argument(
        "--base-url",
        default=os.environ.get("IMAGE_SCORING_API", "http://127.0.0.1:7860"),
        help="Backend base URL (default IMAGE_SCORING_API or http://127.0.0.1:7860).",
    )
    p.add_argument(
        "--fetch-status",
        action="store_true",
        help="After --enqueue, GET /api/scoring/status once (monitoring hook).",
    )
    p.add_argument("--json", action="store_true", help="Print folder aggregates as JSON.")
    p.add_argument(
        "--status-only",
        action="store_true",
        help="GET /api/scoring/status from --base-url and exit (no DB; for quick monitoring).",
    )
    args = p.parse_args()

    if args.status_only:
        base = args.base_url.rstrip("/")
        try:
            st = _get_json(f"{base}/api/scoring/status", timeout=15.0)
            print(json.dumps(st, indent=2, default=str))
        except (HTTPError, URLError, OSError) as e:
            logger.error("%s", e)
            return 1
        return 0

    db.init_db()
    conn = db.get_connector()

    folder_rows, orphan_count = _folder_aggregates(conn)

    if args.json:
        print(
            json.dumps(
                {"folders": folder_rows, "incomplete_without_folder_id": orphan_count},
                indent=2,
            )
        )
    else:
        total_inc = sum(int(r.get("incomplete_count") or 0) for r in folder_rows)
        print(f"Incomplete images (joined to folders): {total_inc} across {len(folder_rows)} folder(s).")
        if orphan_count:
            print(f"Incomplete rows with folder_id NULL (not enqueued by folder): {orphan_count}")
        print()
        for r in folder_rows:
            print(f"  {r['incomplete_count']}\t{r['folder_path']}")

    if args.csv:
        rows = _list_images(conn, args.csv_limit)
        path = Path(args.csv)
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["id", "file_path", "folder_path"])
            w.writeheader()
            for row in rows:
                w.writerow(
                    {
                        "id": row.get("id"),
                        "file_path": row.get("file_path"),
                        "folder_path": row.get("folder_path"),
                    }
                )
        logger.info("Wrote %s row(s) to %s", len(rows), path)

    if not args.enqueue:
        return 0

    # Folders are already ORDER BY incomplete_count DESC from SQL; tie-break by path.
    to_submit = list(folder_rows)
    if args.max_folders == 0:
        effective_cap: int | None = None
    elif args.max_folders is not None:
        effective_cap = max(0, args.max_folders)
    else:
        effective_cap = 10
    if effective_cap is not None:
        to_submit = to_submit[:effective_cap]

    base = args.base_url.rstrip("/")
    start_url = f"{base}/api/scoring/start"
    payload_template = {"skip_existing": True, "force_rescore": False}

    ok = 0
    missing_on_host: list[str] = []
    for i, row in enumerate(to_submit):
        folder_path = row.get("folder_path")
        if not folder_path:
            logger.warning("Skipping row with empty folder_path")
            continue
        body = {**payload_template, "input_path": str(folder_path)}
        if not os.path.exists(str(folder_path)):
            missing_on_host.append(str(folder_path))

        if args.dry_run:
            print(f"[dry-run] POST {start_url} {json.dumps(body)}")
            ok += 1
            continue

        try:
            result = _post_json(start_url, body, timeout=120.0)
        except HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            logger.error("HTTP %s for %s: %s", e.code, folder_path, err_body)
            continue
        except URLError as e:
            logger.error("Request failed for %s: %s", folder_path, e)
            continue

        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        job_id = data.get("job_id")
        qpos = data.get("queue_position")
        if result.get("success"):
            ok += 1
            print(f"  [{ok}] queued job_id={job_id} queue={qpos}  {folder_path}")
        else:
            logger.error("Enqueue failed for %s: %s", folder_path, result)

        if args.delay_seconds > 0 and i < len(to_submit) - 1:
            time.sleep(args.delay_seconds)

    print(f"\nEnqueued {ok}/{len(to_submit)} folder scoring job(s).")
    if missing_on_host:
        print(
            "\nNote: these paths are not visible on the machine running this script; "
            "the WebUI host must still be able to resolve them:",
            file=sys.stderr,
        )
        for mp in missing_on_host:
            print(f"  {mp}", file=sys.stderr)

    if args.fetch_status and not args.dry_run:
        try:
            st = _get_json(f"{base}/api/scoring/status", timeout=15.0)
            print("\nGET /api/scoring/status:")
            print(json.dumps(st, indent=2, default=str))
        except (HTTPError, URLError, OSError) as e:
            logger.warning("Could not fetch scoring status: %s", e)

    if args.dry_run:
        return 0
    return 0 if ok == len(to_submit) else 1


if __name__ == "__main__":
    raise SystemExit(main())
