"""One-off audit: folders created calendar-today vs jobs (incl. heal) touching them.

Run from repo root: python scripts/debug/audit_runs_new_folders_today.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

# repo root on path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.chdir(ROOT)

from modules import db  # noqa: E402


def _norm_path(s: str) -> str:
    return (s or "").strip().replace("/", "\\").lower().rstrip("\\")


def path_touches_folder(job_path: str, folder_path: str) -> bool:
    jp = _norm_path(job_path)
    fp = _norm_path(folder_path)
    if not jp or not fp:
        return False
    if jp == fp:
        return True
    return jp.startswith(fp + "\\")


def job_touches_any_folder(job: dict[str, Any], folder_paths: list[str]) -> bool:
    candidates: list[str] = []
    ip = job.get("input_path")
    if isinstance(ip, str) and ip.strip():
        candidates.append(ip)
    sp = job.get("scope_paths")
    if isinstance(sp, list):
        candidates.extend(str(x) for x in sp if x)
    elif isinstance(sp, str) and sp.strip():
        try:
            parsed = json.loads(sp)
            if isinstance(parsed, list):
                candidates.extend(str(x) for x in parsed)
        except (json.JSONDecodeError, TypeError):
            pass
    for folder in folder_paths:
        for c in candidates:
            if path_touches_folder(c, folder) or path_touches_folder(folder, c):
                return True
    return False


def parse_queue_payload(job: dict[str, Any]) -> dict[str, Any]:
    qp = job.get("queue_payload")
    if isinstance(qp, dict):
        return qp
    if isinstance(qp, str) and qp.strip():
        try:
            out = json.loads(qp)
            if isinstance(out, str):
                out = json.loads(out)
            return out if isinstance(out, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


def is_heal_job(job: dict[str, Any]) -> bool:
    qp = parse_queue_payload(job)
    tid = str(qp.get("tool_id") or "")
    if tid.startswith("heal_workflow_"):
        return True
    desc = str(job.get("description") or "")
    return "Automated workflow healing for phase:" in desc


def main() -> None:
    conn = db.get_connector()
    today = date.today()
    print(f"Calendar today (local): {today}")
    print(f"DB engine: {db._get_db_engine()}")

    # Bind Python local date so Postgres CURRENT_DATE / session TZ cannot skew "today".
    folder_rows = list(
        conn.query(
            "SELECT id, path, created_at FROM folders WHERE created_at::date = %s ORDER BY created_at",
            (today,),
        )
    )

    if not folder_rows:
        # fallback: rolling 24h for operational "today"
        folder_rows = list(
            conn.query(
                """
                SELECT id, path, created_at FROM folders
                WHERE created_at >= (CURRENT_TIMESTAMP - INTERVAL '24 hours')
                ORDER BY created_at
                """,
                (),
            )
        )
        print("No folders on calendar date %s; using rolling 24h window for 'new' folders." % today)
    else:
        print("Folders with created_at::date == local calendar today (%s):" % today)

    folder_paths = [str(r["path"]) for r in folder_rows if r.get("path")]
    print(f"New folder count: {len(folder_paths)}")
    for r in folder_rows[:50]:
        print(f"  id={r['id']} created_at={r['created_at']} path={r['path']}")
    if len(folder_rows) > 50:
        print(f"  ... and {len(folder_rows) - 50} more")

    if not folder_paths:
        print("\nNo folders in scope — still listing today's jobs with heal_workflow_* for context.")
        folder_paths = []

    # Jobs created today (wide status)
    job_sql = """
        SELECT * FROM jobs
        WHERE created_at::date = %s
        ORDER BY created_at DESC
    """
    try:
        jobs_today = [dict(r) for r in conn.query(job_sql, (today,))]
    except Exception as e:
        print("Failed jobs query:", e)
        jobs_today = []

    touching = [j for j in jobs_today if folder_paths and job_touches_any_folder(j, folder_paths)]
    heal_today = [j for j in jobs_today if is_heal_job(j)]

    print(f"\nJobs with created_at::date = today: {len(jobs_today)}")
    print(f"Jobs touching new-folder paths (subset): {len(touching)}")
    print(f"Heal-spawned jobs today (any path): {len(heal_today)}")

    print("\n=== Audit: jobs touching new folders ===")
    for j in touching:
        qp = parse_queue_payload(j)
        print(
            f"id={j.get('id')} status={j.get('status')} job_type={j.get('job_type')} "
            f"heal={is_heal_job(j)} tool_id={qp.get('tool_id')!r} "
            f"run_mode={qp.get('run_mode')!r}\n"
            f"  input_path={j.get('input_path')}\n"
            f"  description={(str(j.get('description') or '')[:120])!r}"
        )

    print("\n=== All heal-spawned jobs today (tool_id heal_workflow_*) ===")
    for j in heal_today:
        qp = parse_queue_payload(j)
        if str(qp.get("tool_id", "")).startswith("heal_workflow_") or is_heal_job(j):
            print(
                f"id={j.get('id')} status={j.get('status')} tool_id={qp.get('tool_id')!r} "
                f"input_path={j.get('input_path')}"
            )

    # Folder-centric rollup
    print("\n=== Folder -> job ids ===")
    for fp in folder_paths[:100]:
        hits = [j for j in jobs_today if job_touches_any_folder(j, [fp])]
        if not hits:
            print(f"{fp}\n  (no jobs created today with this scope)")
            continue
        parts = []
        for j in hits:
            qp = parse_queue_payload(j)
            parts.append(
                f"id={j['id']} {j.get('status')} heal={is_heal_job(j)} tool_id={qp.get('tool_id')}"
            )
        print(f"{fp}\n  " + "\n  ".join(parts))


if __name__ == "__main__":
    main()
