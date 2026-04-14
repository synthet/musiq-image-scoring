#!/usr/bin/env python3
"""
Per-folder data quality rollup: counts of images missing scores/labels, thumbnails,
bird species keywords, or stack assignment.

Run from repo root with the app environment (see AGENTS.md / python-wsl-webapp-env.mdc).

**See also (narrower tools)**

- Scoring/label only (same predicate as ``db._incomplete_images_where_sql``), optional
  enqueue: ``scripts/maintenance/queue_scoring_incomplete_by_folder.py``
- Phase-level gaps for a chosen library path (non-empty scope): HTTP
  ``POST /api/runs/validation-repair/preview`` with JSON body
  ``{"scope_paths": ["/your/root"], "stages": null}`` — mirrors
  ``db.build_validation_repair_plan``.

**Caveats**

- **Bird species:** Matches ``bird_species`` / ``get_images_with_keyword`` when keywords are
  stored in ``image_keywords`` + ``keywords_dim``. Legacy ``images.keywords`` text alone is
  not counted unless synced to the normalized tables.
- **Stacks:** ``stack_id IS NULL`` includes legitimate singletons and never-clustered
  images. Use ``--stack-after-culling-only`` to count only rows where the culling phase is
  ``done`` in ``image_phase_status`` but ``stack_id`` is still NULL (still not perfect for
  singleton outcomes, but stricter than raw NULL counts).
- **Thumbnails:** "Missing" means both ``thumbnail_path`` and ``thumbnail_path_win`` are
  empty/NULL after trim (same idea as ``modules.thumbnails`` resolving either column).

Examples::

  python scripts/maintenance/folder_data_quality_report.py
  python scripts/maintenance/folder_data_quality_report.py --json
  python scripts/maintenance/folder_data_quality_report.py --root /mnt/d/Photos/2024
  python scripts/maintenance/folder_data_quality_report.py --stack-after-culling-only --csv report.csv

  # Include folders that are currently a run's input_path (default excludes running + queued)
  python scripts/maintenance/folder_data_quality_report.py --no-exclude-active-runs

  # After sorting by total issues, show at most max(0, BUDGET - running_or_queued_jobs)
  # (default BUDGET=10 when the flag is used alone)
  python scripts/maintenance/folder_data_quality_report.py --top-folders-after-active

  # Queue /api/runs/submit fix runs from this report (stages derived from issue columns):
  python scripts/maintenance/schedule_folder_quality_fix_runs.py --dry-run --top-folders-after-active

"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def _active_jobs_snapshot(conn) -> list[dict[str, Any]]:
    """Jobs the UI treats as in-flight: status running or queued, with an input path."""
    rows = conn.query(
        """
        SELECT id, input_path, status
        FROM jobs
        WHERE LOWER(TRIM(CAST(status AS VARCHAR(128)))) IN ('running', 'queued')
          AND input_path IS NOT NULL
          AND TRIM(CAST(input_path AS VARCHAR(4000))) <> ''
        ORDER BY id
        """
    )
    return [dict(r) for r in rows]


def _exclude_active_run_folders_sql(folder_path_expr: str = "f.path") -> str:
    """
    SQL AND-fragment: drop folders that match a running/queued job scope.

    Matches ``jobs.input_path`` exactly or as a parent path (folder is under that job root).
    Uses PostgreSQL ``starts_with`` to avoid LIKE escape issues.
    """
    return f"""
        AND NOT EXISTS (
            SELECT 1 FROM jobs j
            WHERE j.input_path IS NOT NULL
              AND TRIM(CAST(j.input_path AS VARCHAR(4000))) <> ''
              AND LOWER(TRIM(CAST(j.status AS VARCHAR(128)))) IN ('running', 'queued')
              AND (
                  TRIM(CAST({folder_path_expr} AS VARCHAR(4000)))
                      = TRIM(CAST(j.input_path AS VARCHAR(4000)))
                  OR starts_with(
                      TRIM(CAST({folder_path_expr} AS VARCHAR(4000))),
                      TRIM(CAST(j.input_path AS VARCHAR(4000))) || '/'
                  )
              )
        )
    """


def _folder_rollup_query(
    *,
    root_path: str | None,
    stack_after_culling_only: bool,
    exclude_active_runs: bool,
) -> tuple[str, tuple[Any, ...]]:
    from modules import db

    inc = db._incomplete_images_where_sql("i")

    thumb_missing = """(
        COALESCE(TRIM(i.thumbnail_path), '') = ''
        AND COALESCE(TRIM(i.thumbnail_path_win), '') = ''
    )"""

    bird_missing_species = """(
        EXISTS (
            SELECT 1 FROM image_keywords ik
            JOIN keywords_dim kd ON kd.keyword_id = ik.keyword_id
            WHERE ik.image_id = i.id
              AND LOWER(kd.keyword_norm) LIKE '%birds%'
        )
        AND NOT EXISTS (
            SELECT 1 FROM image_keywords ik2
            JOIN keywords_dim kd2 ON kd2.keyword_id = ik2.keyword_id
            WHERE ik2.image_id = i.id
              AND kd2.keyword_norm LIKE 'species:%'
        )
    )"""

    if stack_after_culling_only:
        stack_issue = """(
            EXISTS (
                SELECT 1 FROM image_phase_status ips
                JOIN pipeline_phases pp ON pp.id = ips.phase_id
                WHERE ips.image_id = i.id
                  AND LOWER(TRIM(pp.code)) = 'culling'
                  AND LOWER(TRIM(ips.status)) = 'done'
            )
            AND i.stack_id IS NULL
        )"""
    else:
        stack_issue = "(i.stack_id IS NULL)"

    where_extra = ""
    params: list[Any] = []
    if root_path:
        rp = root_path.rstrip("/\\")
        where_extra = " AND (f.path = ? OR f.path LIKE ? OR f.path LIKE ?)"
        params.extend([rp, rp + "/%", rp + "\\%"])

    exclude_sql = _exclude_active_run_folders_sql("f.path") if exclude_active_runs else ""

    q = f"""
        SELECT
            f.path AS folder_path,
            COUNT(*) AS image_count,
            COUNT(*) FILTER (WHERE {inc}) AS scoring_incomplete,
            COUNT(*) FILTER (WHERE {thumb_missing}) AS thumb_missing,
            COUNT(*) FILTER (WHERE {bird_missing_species}) AS bird_missing_species,
            COUNT(*) FILTER (WHERE {stack_issue}) AS stack_issue
        FROM images i
        JOIN folders f ON f.id = i.folder_id
        WHERE 1=1
        {where_extra}
        {exclude_sql}
        GROUP BY f.path
        HAVING
            COUNT(*) FILTER (WHERE {inc}) > 0
            OR COUNT(*) FILTER (WHERE {thumb_missing}) > 0
            OR COUNT(*) FILTER (WHERE {bird_missing_species}) > 0
            OR COUNT(*) FILTER (WHERE {stack_issue}) > 0
        ORDER BY
            (COUNT(*) FILTER (WHERE {inc})
             + COUNT(*) FILTER (WHERE {thumb_missing})
             + COUNT(*) FILTER (WHERE {bird_missing_species})
             + COUNT(*) FILTER (WHERE {stack_issue})) DESC,
            f.path
    """
    return q, tuple(params)


def _orphan_counts(*, stack_after_culling_only: bool) -> dict[str, int]:
    from modules import db

    inc = db._incomplete_images_where_sql("i")
    conn = db.get_connector()
    thumb_missing = """(
        COALESCE(TRIM(i.thumbnail_path), '') = ''
        AND COALESCE(TRIM(i.thumbnail_path_win), '') = ''
    )"""
    bird_missing_species = """(
        EXISTS (
            SELECT 1 FROM image_keywords ik
            JOIN keywords_dim kd ON kd.keyword_id = ik.keyword_id
            WHERE ik.image_id = i.id
              AND LOWER(kd.keyword_norm) LIKE '%birds%'
        )
        AND NOT EXISTS (
            SELECT 1 FROM image_keywords ik2
            JOIN keywords_dim kd2 ON kd2.keyword_id = ik2.keyword_id
            WHERE ik2.image_id = i.id
              AND kd2.keyword_norm LIKE 'species:%'
        )
    )"""
    if stack_after_culling_only:
        stack_issue = """(
            EXISTS (
                SELECT 1 FROM image_phase_status ips
                JOIN pipeline_phases pp ON pp.id = ips.phase_id
                WHERE ips.image_id = i.id
                  AND LOWER(TRIM(pp.code)) = 'culling'
                  AND LOWER(TRIM(ips.status)) = 'done'
            )
            AND i.stack_id IS NULL
        )"""
    else:
        stack_issue = "(i.stack_id IS NULL)"
    q = f"""
        SELECT
            COUNT(*) FILTER (WHERE i.folder_id IS NULL AND ({inc})) AS scoring_incomplete,
            COUNT(*) FILTER (WHERE i.folder_id IS NULL AND {thumb_missing}) AS thumb_missing,
            COUNT(*) FILTER (WHERE i.folder_id IS NULL AND {bird_missing_species}) AS bird_missing_species,
            COUNT(*) FILTER (WHERE i.folder_id IS NULL AND {stack_issue}) AS stack_issue
        FROM images i
    """
    row = conn.query_one(q)
    return {k: int(row[k] or 0) for k in row} if row else {}


def fetch_folder_quality_rows(
    conn: Any,
    *,
    root_path: str | None = None,
    stack_after_culling_only: bool = False,
    exclude_active_runs: bool = True,
    include_clean_folders: bool = False,
) -> list[dict[str, Any]]:
    """
    Same folder rollup as the CLI (leaf folders with at least one issue, unless
    *include_clean_folders*). Used by other maintenance scripts (e.g. scheduling fix runs).
    """
    from modules import db

    if include_clean_folders:
        inc = db._incomplete_images_where_sql("i")
        thumb_missing = """(
            COALESCE(TRIM(i.thumbnail_path), '') = ''
            AND COALESCE(TRIM(i.thumbnail_path_win), '') = ''
        )"""
        bird_missing_species = """(
            EXISTS (
                SELECT 1 FROM image_keywords ik
                JOIN keywords_dim kd ON kd.keyword_id = ik.keyword_id
                WHERE ik.image_id = i.id
                  AND LOWER(kd.keyword_norm) LIKE '%birds%'
            )
            AND NOT EXISTS (
                SELECT 1 FROM image_keywords ik2
                JOIN keywords_dim kd2 ON kd2.keyword_id = ik2.keyword_id
                WHERE ik2.image_id = i.id
                  AND kd2.keyword_norm LIKE 'species:%'
            )
        )"""
        if stack_after_culling_only:
            stack_issue = """(
                EXISTS (
                    SELECT 1 FROM image_phase_status ips
                    JOIN pipeline_phases pp ON pp.id = ips.phase_id
                    WHERE ips.image_id = i.id
                      AND LOWER(TRIM(pp.code)) = 'culling'
                      AND LOWER(TRIM(ips.status)) = 'done'
                )
                AND i.stack_id IS NULL
            )"""
        else:
            stack_issue = "(i.stack_id IS NULL)"

        where_extra = ""
        params: list[Any] = []
        if root_path:
            rp = root_path.rstrip("/\\")
            where_extra = " AND (f.path = ? OR f.path LIKE ? OR f.path LIKE ?)"
            params.extend([rp, rp + "/%", rp + "\\%"])

        exclude_sql = _exclude_active_run_folders_sql("f.path") if exclude_active_runs else ""

        q = f"""
            SELECT
                f.path AS folder_path,
                COUNT(*) AS image_count,
                COUNT(*) FILTER (WHERE {inc}) AS scoring_incomplete,
                COUNT(*) FILTER (WHERE {thumb_missing}) AS thumb_missing,
                COUNT(*) FILTER (WHERE {bird_missing_species}) AS bird_missing_species,
                COUNT(*) FILTER (WHERE {stack_issue}) AS stack_issue
            FROM images i
            JOIN folders f ON f.id = i.folder_id
            WHERE 1=1
            {where_extra}
            {exclude_sql}
            GROUP BY f.path
            ORDER BY f.path
        """
        return [dict(r) for r in conn.query(q, tuple(params) if params else None)]

    q, params = _folder_rollup_query(
        root_path=root_path,
        stack_after_culling_only=stack_after_culling_only,
        exclude_active_runs=exclude_active_runs,
    )
    return [dict(r) for r in conn.query(q, params)]


def main() -> int:
    from modules import db

    p = argparse.ArgumentParser(
        description="Report per-folder counts for missing scores/labels, thumbs, bird species keywords, stacks.",
    )
    p.add_argument(
        "--root",
        metavar="PATH",
        help="Only include folders under this path (prefix match).",
    )
    p.add_argument(
        "--stack-after-culling-only",
        action="store_true",
        help=(
            "Count stack issues only when culling phase is done but stack_id IS NULL "
            "(instead of all stack_id IS NULL)."
        ),
    )
    p.add_argument("--json", action="store_true", help="Print full report as JSON.")
    p.add_argument(
        "--csv",
        metavar="FILE",
        help="Write folder rows to CSV.",
    )
    p.add_argument(
        "--include-clean-folders",
        action="store_true",
        help=(
            "Include all folders (not only those with at least one issue). "
            "Slower on large DBs; uses alternate query without HAVING."
        ),
    )
    p.add_argument(
        "--exclude-active-runs",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Exclude leaf folders that match a job with status running or queued "
            "(same paths as Runs / Active in the Web UI). Default: exclude."
        ),
    )
    p.add_argument(
        "--top-folders-after-active",
        type=int,
        nargs="?",
        const=10,
        default=None,
        metavar="BUDGET",
        help=(
            "After sorting (by combined issue counts), keep at most "
            "max(0, BUDGET - number_of_running_or_queued_jobs) folder rows. "
            "Use the flag alone for BUDGET=10. Omit for no limit."
        ),
    )
    args = p.parse_args()

    db.init_db()
    conn = db.get_connector()

    rows = fetch_folder_quality_rows(
        conn,
        root_path=args.root,
        stack_after_culling_only=args.stack_after_culling_only,
        exclude_active_runs=args.exclude_active_runs,
        include_clean_folders=args.include_clean_folders,
    )

    orphans = _orphan_counts(stack_after_culling_only=args.stack_after_culling_only)

    active_jobs = _active_jobs_snapshot(conn)

    top_budget = args.top_folders_after_active
    folders_shown_cap: int | None = None
    if top_budget is not None:
        folders_shown_cap = max(0, int(top_budget) - len(active_jobs))
        rows = rows[:folders_shown_cap]

    report: dict[str, Any] = {
        "folders": rows,
        "orphans_folder_id_null": orphans,
        "active_jobs_running_or_queued": active_jobs,
        "options": {
            "root": args.root,
            "stack_after_culling_only": args.stack_after_culling_only,
            "include_clean_folders": args.include_clean_folders,
            "exclude_active_runs": args.exclude_active_runs,
            "top_folders_after_active_budget": top_budget,
            "top_folders_after_active_cap": folders_shown_cap,
        },
    }

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        total_f = len(rows)
        sum_sc = sum(int(r.get("scoring_incomplete") or 0) for r in rows)
        sum_th = sum(int(r.get("thumb_missing") or 0) for r in rows)
        sum_br = sum(int(r.get("bird_missing_species") or 0) for r in rows)
        sum_st = sum(int(r.get("stack_issue") or 0) for r in rows)
        print(
            f"Folders with at least one issue: {total_f} "
            f"(scoring_incomplete={sum_sc}, thumb_missing={sum_th}, "
            f"bird_missing_species={sum_br}, stack_issue={sum_st})"
        )
        if top_budget is not None:
            print(
                f"Showing up to {folders_shown_cap} folder row(s) "
                f"(budget={top_budget} minus {len(active_jobs)} active/queued job(s))."
            )
        if args.exclude_active_runs and active_jobs:
            paths = ", ".join(
                f"#{int(j['id'])} {j.get('input_path')!s} ({j.get('status')})" for j in active_jobs
            )
            print(f"Excluded folders under active/queued runs: {paths}")
        elif not args.exclude_active_runs and active_jobs:
            print(
                f"Note: {len(active_jobs)} job(s) running or queued (--no-exclude-active-runs); "
                "those folders may still appear below."
            )
        if any(orphans.values()):
            print(f"Images with folder_id NULL (orphans): {orphans}")
        print()
        for r in rows:
            print(
                f"{r.get('scoring_incomplete', 0)}\t{r.get('thumb_missing', 0)}\t"
                f"{r.get('bird_missing_species', 0)}\t{r.get('stack_issue', 0)}\t"
                f"{r.get('image_count', 0)}\t{r.get('folder_path')}"
            )

    if args.csv:
        out = Path(args.csv)
        fieldnames = [
            "folder_path",
            "image_count",
            "scoring_incomplete",
            "thumb_missing",
            "bird_missing_species",
            "stack_issue",
        ]
        with out.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k) for k in fieldnames})
        logger.info("Wrote %s folder row(s) to %s", len(rows), out)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
