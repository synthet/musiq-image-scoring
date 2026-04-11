#!/usr/bin/env python3
"""
Report images with missing scores, UUID, thumbnail paths, capture date, or pending pipeline phases,
and optionally repair thumbnails locally or queue a full pipeline run on the WebUI.

Run from repo root in WSL with the app venv (see AGENTS.md). Examples:

  # Summary counts (PostgreSQL)
  python scripts/maintenance/report_and_heal_data_gaps.py --summarize

  # List up to 100 rows with gap flags
  python scripts/maintenance/report_and_heal_data_gaps.py --limit 100

  # JSON for scripting
  python scripts/maintenance/report_and_heal_data_gaps.py --limit 50 --json

  # Regenerate missing thumbnails (no GPU; uses modules.thumbnails)
  python scripts/maintenance/report_and_heal_data_gaps.py --fix-thumbnails --thumb-limit 300

  # Queue indexing→metadata→scoring→culling→keywords on the backend (WebUI must be running)
  python scripts/maintenance/report_and_heal_data_gaps.py --queue-pipeline --scope /mnt/d/Photos
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def _post_json(url: str, body: dict[str, Any], timeout: float = 60.0) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8")
    req = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def main() -> int:
    from modules import db

    p = argparse.ArgumentParser(
        description="Find incomplete image records and optionally heal thumbnails or queue pipeline jobs.",
    )
    p.add_argument("--folder", help="Limit report/summary to this folder tree (WSL or Windows path).")
    p.add_argument("--limit", type=int, default=200, help="Max rows for listing (default 200).")
    p.add_argument("--summarize", action="store_true", help="Print aggregate gap counts only.")
    p.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    p.add_argument(
        "--fix-thumbnails",
        action="store_true",
        help="Run thumbnail path repair + missing thumbnail regeneration (local filesystem).",
    )
    p.add_argument(
        "--thumb-limit",
        type=int,
        default=500,
        help="Max thumbnails to regenerate when using --fix-thumbnails (default 500).",
    )
    p.add_argument(
        "--queue-pipeline",
        action="store_true",
        help="POST /api/runs/submit for a multi-phase run (requires running WebUI).",
    )
    p.add_argument(
        "--scope",
        action="append",
        dest="scopes",
        metavar="PATH",
        help="Folder path(s) passed as scope_paths (repeatable). Required with --queue-pipeline.",
    )
    p.add_argument(
        "--api-url",
        default=os.environ.get("IMAGE_SCORING_API", "http://127.0.0.1:7860"),
        help="Base URL for the backend (default http://127.0.0.1:7860 or IMAGE_SCORING_API).",
    )
    p.add_argument(
        "--no-skip-done",
        action="store_false",
        dest="skip_done",
        default=True,
        help="Queue run with skip_done=false (default: skip_done=true).",
    )
    args = p.parse_args()

    db.init_db()

    if args.summarize:
        stats = db.summarize_data_gaps(folder_path=args.folder)
        if args.json:
            print(json.dumps(stats, indent=2))
        else:
            for k, v in sorted(stats.items()):
                print(f"{k}: {v}")
        return 0

    if args.fix_thumbnails:
        from modules import thumbnail_maintenance

        repair = thumbnail_maintenance.repair_thumbnail_paths_batch(args.thumb_limit, repair_all_pairs=False)
        regen = thumbnail_maintenance.regenerate_missing_thumbnails_batch(args.thumb_limit)
        out = {"repair": repair, "regenerate": regen}
        if args.json:
            print(json.dumps(out, indent=2, default=str))
        else:
            print("Thumbnail repair:", repair)
            print("Thumbnail regenerate:", regen)
        return 0

    if args.queue_pipeline:
        scopes = args.scopes or []
        if not scopes:
            p.error("--queue-pipeline requires at least one --scope PATH")
        base = args.api_url.rstrip("/")
        body = {
            "scope_type": "folder_recursive",
            "scope_paths": scopes,
            "stages": ["indexing", "metadata", "scoring", "culling", "keywords"],
            "skip_done": bool(args.skip_done),
            "force_rerun": False,
            "fix_incomplete_stages": True,
        }
        url = f"{base}/api/runs/submit"
        try:
            result = _post_json(url, body, timeout=120.0)
        except HTTPError as e:
            logger.error("HTTP %s: %s", e.code, e.read().decode("utf-8", errors="replace"))
            return 1
        except URLError as e:
            logger.error("Could not reach %s: %s", url, e)
            return 1
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(json.dumps(result, indent=2))
        return 0 if result.get("success") else 1

    rows = db.list_images_with_data_gaps(limit=args.limit, folder_path=args.folder)
    if args.json:
        print(json.dumps(rows, indent=2, default=str))
        return 0

    for r in rows:
        rid = r.get("id")
        fp = r.get("file_path")
        reasons = ",".join(r.get("reasons") or [])
        fold = r.get("folder_path") or ""
        print(f"id={rid}\t{reasons}\t{fold}\t{fp}")
    print(f"Listed {len(rows)} row(s) (limit {args.limit}). Use --summarize for counts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
