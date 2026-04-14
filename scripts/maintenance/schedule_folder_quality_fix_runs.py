#!/usr/bin/env python3
"""
Schedule POST /api/runs/submit jobs for folders with data-quality issues, using stages
inferred from folder_data_quality_report metrics (same SQL as fetch_folder_quality_rows).

Phase mapping (pipeline order):
  - scoring_incomplete or thumb_missing → indexing, metadata, scoring
  - stack_issue → culling (prerequisites above included)
  - bird_missing_species → keywords, bird_species (prerequisites through scoring included)

Uses run_mode ``validate_and_repair`` so the backend applies fix-incomplete style processing.

Requires: backend reachable (default http://127.0.0.1:7860). Uses stdlib urllib (no requests).

Examples::

  python scripts/maintenance/schedule_folder_quality_fix_runs.py --dry-run
  python scripts/maintenance/schedule_folder_quality_fix_runs.py --top-folders-after-active
  python scripts/maintenance/schedule_folder_quality_fix_runs.py --heal-thumbnails-global

"""
from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_FQR_PATH = Path(__file__).resolve().parent / "folder_data_quality_report.py"
_spec = importlib.util.spec_from_file_location("folder_data_quality_report", _FQR_PATH)
assert _spec and _spec.loader
fqr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fqr)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

PHASE_ORDER = ["indexing", "metadata", "scoring", "culling", "keywords", "bird_species"]


def stages_for_quality_row(row: dict[str, Any]) -> list[str]:
    """Ordered pipeline stages needed to address non-zero issue columns."""
    si = int(row.get("scoring_incomplete") or 0)
    tm = int(row.get("thumb_missing") or 0)
    br = int(row.get("bird_missing_species") or 0)
    st = int(row.get("stack_issue") or 0)

    need: set[str] = set()
    if si > 0 or tm > 0 or st > 0:
        need.update(["indexing", "metadata", "scoring"])
    if st > 0:
        need.add("culling")
    if br > 0:
        need.update(["keywords", "bird_species"])

    return [p for p in PHASE_ORDER if p in need]


def _post_json(url: str, body: dict[str, Any], timeout: float = 120.0) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8")
    req = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def submit_run(
    base_url: str,
    folder_path: str,
    stages: list[str],
    *,
    run_mode: str = "validate_and_repair",
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/runs/submit"
    payload: dict[str, Any] = {
        "scope_type": "folder_recursive",
        "scope_paths": [folder_path],
        "stages": stages,
        "run_mode": run_mode,
    }
    return _post_json(url, payload, timeout=120.0)


def post_heal_thumbnails_global(base_url: str) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/maintenance/regenerate-thumbnails"
    req = Request(url, method="POST")
    with urlopen(req, timeout=60.0) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def main() -> int:
    from modules import db

    p = argparse.ArgumentParser(
        description="Submit /api/runs/submit fix runs for folders with quality issues (stages from issue columns).",
    )
    p.add_argument(
        "--base-url",
        default="http://127.0.0.1:7860",
        help="Backend base URL.",
    )
    p.add_argument(
        "--root",
        metavar="PATH",
        help="Only folders under this path (passed to folder quality query).",
    )
    p.add_argument(
        "--stack-after-culling-only",
        action="store_true",
        help="Same as folder_data_quality_report (stack signal).",
    )
    p.add_argument(
        "--exclude-active-runs",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Exclude folders with running/queued jobs (default: on).",
    )
    p.add_argument(
        "--top-folders-after-active",
        type=int,
        nargs="?",
        const=10,
        default=None,
        metavar="BUDGET",
        help="Cap folders to max(0, BUDGET - active_jobs); flag alone => BUDGET=10.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned submissions only.",
    )
    p.add_argument(
        "--delay-seconds",
        type=float,
        default=0.5,
        help="Sleep between POST /api/runs/submit calls (default 0.5).",
    )
    p.add_argument(
        "--heal-thumbnails-global",
        action="store_true",
        help=(
            "If any selected folder has thumb_missing>0, POST "
            "/api/maintenance/regenerate-thumbnails once before per-folder runs."
        ),
    )
    p.add_argument(
        "--run-mode",
        default="validate_and_repair",
        choices=["validate_and_repair", "process_unprocessed_or_empty", "process_all_overwrite"],
        help="Run mode for /api/runs/submit (default: validate_and_repair).",
    )
    args = p.parse_args()

    db.init_db()
    conn = db.get_connector()

    rows = fqr.fetch_folder_quality_rows(
        conn,
        root_path=args.root,
        stack_after_culling_only=args.stack_after_culling_only,
        exclude_active_runs=args.exclude_active_runs,
        include_clean_folders=False,
    )
    active_jobs = fqr._active_jobs_snapshot(conn)

    top_budget = args.top_folders_after_active
    if top_budget is not None:
        cap = max(0, int(top_budget) - len(active_jobs))
        rows = rows[:cap]

    if not rows:
        print("No folders to schedule (empty selection).")
        return 0

    any_thumb = any(int(r.get("thumb_missing") or 0) > 0 for r in rows)

    if args.heal_thumbnails_global and any_thumb:
        if args.dry_run:
            print("[dry-run] POST /api/maintenance/regenerate-thumbnails (global batch)")
        else:
            try:
                r = post_heal_thumbnails_global(args.base_url)
                logger.info("regenerate-thumbnails: %s", r.get("message", r))
            except (HTTPError, URLError, OSError) as e:
                logger.error("regenerate-thumbnails failed: %s", e)

    ok = 0
    for i, row in enumerate(rows):
        path = str(row.get("folder_path") or "").strip()
        if not path:
            continue
        stages = stages_for_quality_row(row)
        if not stages:
            logger.warning("No stages derived for %s — skipping", path)
            continue

        if args.dry_run:
            print(f"[dry-run] {path}")
            print(f"          stages={stages} run_mode={args.run_mode}")
            ok += 1
            continue

        try:
            result = submit_run(
                args.base_url,
                path,
                stages,
                run_mode=args.run_mode,
            )
            rid = result.get("run_id", "?")
            pos = result.get("queue_position", "?")
            print(f"  run_id={rid} queue={pos}  {path}")
            print(f"           stages={' '.join(stages)}")
            ok += 1
        except HTTPError as e:
            err = e.read().decode("utf-8", errors="replace")
            logger.error("HTTP %s for %s: %s", e.code, path, err)
        except (URLError, OSError) as e:
            logger.error("Request failed for %s: %s", path, e)

        if args.delay_seconds > 0 and i < len(rows) - 1:
            time.sleep(args.delay_seconds)

    if args.dry_run:
        print(f"\nWould schedule {ok}/{len(rows)} folder run(s) (selection had {len(rows)} row(s)).")
        return 0
    print(f"\nScheduled {ok}/{len(rows)} folder run(s) (selection had {len(rows)} row(s)).")
    return 0 if ok == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
