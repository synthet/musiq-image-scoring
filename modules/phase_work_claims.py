"""DB-backed per-image phase work claims to prevent duplicate processing across runs."""

from __future__ import annotations

import logging
from typing import Any

from modules import db

logger = logging.getLogger(__name__)


def claim_image_phases(
    job_id: int,
    phase_code: str,
    image_ids: list[int],
) -> dict[str, Any]:
    """Claim ``image_ids`` for ``phase_code`` on ``job_id``. Skip IDs already claimed elsewhere."""
    phase = (phase_code or "").strip().lower()
    claimed: list[int] = []
    skipped: list[int] = []
    if not phase or not image_ids:
        return {"claimed": claimed, "skipped_already_claimed": skipped}

    unique_ids: list[int] = []
    seen: set[int] = set()
    for raw in image_ids:
        try:
            iid = int(raw)
        except (TypeError, ValueError):
            continue
        if iid in seen:
            continue
        seen.add(iid)
        unique_ids.append(iid)

    if not unique_ids:
        return {"claimed": claimed, "skipped_already_claimed": skipped}

    conn = db.get_connector()
    placeholders = ",".join("?" * len(unique_ids))
    rows = conn.query(
        f"""
        SELECT image_id, job_id
        FROM image_phase_work_claims
        WHERE phase_code = ?
          AND status IN ('queued', 'running')
          AND image_id IN ({placeholders})
        """,
        tuple([phase] + unique_ids),
    )
    blocked: dict[int, int] = {}
    for r in rows or []:
        try:
            blocked[int(r["image_id"])] = int(r["job_id"])
        except (TypeError, ValueError, KeyError):
            continue

    for iid in unique_ids:
        owner = blocked.get(iid)
        if owner is not None and owner != int(job_id):
            skipped.append(iid)
            continue
        existing = conn.query_one(
            """
            SELECT job_id FROM image_phase_work_claims
            WHERE image_id = ? AND phase_code = ? AND status IN ('queued', 'running')
            """,
            (iid, phase),
        )
        if existing:
            if int(existing["job_id"]) == int(job_id):
                claimed.append(iid)
            else:
                skipped.append(iid)
            continue
        try:
            conn.execute(
                """
                INSERT INTO image_phase_work_claims (job_id, image_id, phase_code, status)
                VALUES (?, ?, ?, 'queued')
                """,
                (int(job_id), iid, phase),
            )
            claimed.append(iid)
        except Exception:
            logger.debug(
                "claim_image_phases failed job_id=%s image_id=%s phase=%s",
                job_id,
                iid,
                phase,
                exc_info=True,
            )
            skipped.append(iid)

    return {"claimed": claimed, "skipped_already_claimed": skipped}


def mark_claims_running(job_id: int, phase_code: str, image_ids: list[int] | None = None) -> None:
    phase = (phase_code or "").strip().lower()
    if not phase:
        return
    params: list = [int(job_id), phase]
    extra = ""
    if image_ids:
        placeholders = ",".join("?" * len(image_ids))
        extra = f" AND image_id IN ({placeholders})"
        params.extend(int(i) for i in image_ids)
    db.get_connector().execute(
        f"""
        UPDATE image_phase_work_claims
        SET status = 'running'
        WHERE job_id = ? AND phase_code = ? AND status = 'queued'{extra}
        """,
        tuple(params),
    )


_TERMINAL_JOB_STATUSES = (
    "interrupted",
    "failed",
    "completed",
    "canceled",
    "cancelled",
)


def reconcile_orphan_work_claims(*, limit_jobs: int = 500) -> dict:
    """Release open claims owned by jobs already in a terminal status.

    Closes the gap when ``recover_running_jobs`` or other paths mark jobs
    interrupted without calling ``release_claims_for_job`` (e.g. crash recovery
    before the release hook existed). Idempotent: only touches queued/running
    claims on terminal jobs.

    Returns ``{"released_rows": int, "job_ids": list[int]}``.
    """
    try:
        lim = max(1, int(limit_jobs))
    except (TypeError, ValueError):
        lim = 500
    placeholders = ",".join("?" * len(_TERMINAL_JOB_STATUSES))
    try:
        rows = db.get_connector().query(
            f"""
            SELECT DISTINCT c.job_id AS job_id
            FROM image_phase_work_claims c
            JOIN jobs j ON j.id = c.job_id
            WHERE c.status IN ('queued', 'running')
              AND j.status IN ({placeholders})
            ORDER BY c.job_id DESC
            FETCH FIRST ? ROWS ONLY
            """,
            tuple(_TERMINAL_JOB_STATUSES) + (lim,),
        )
    except Exception:
        logger.exception("reconcile_orphan_work_claims: scan failed")
        return {"released_rows": 0, "job_ids": []}

    job_ids = [int(r["job_id"]) for r in rows or [] if r and r.get("job_id") is not None]
    released_total = 0
    for jid in job_ids:
        try:
            released_total += int(release_claims_for_job(jid) or 0)
        except Exception:
            logger.debug(
                "reconcile_orphan_work_claims: release failed for job_id=%s",
                jid,
                exc_info=True,
            )
    if released_total:
        logger.info(
            "reconcile_orphan_work_claims: released %s claim row(s) across %s job(s)",
            released_total,
            len(job_ids),
        )
    return {"released_rows": released_total, "job_ids": job_ids}


def reconcile_orphan_work_claims_all(
    *,
    limit_jobs: int = 500,
    max_passes: int = 20,
) -> dict:
    """Run ``reconcile_orphan_work_claims`` until no rows are released or ``max_passes``.

    Handles installations with more than ``limit_jobs`` distinct terminal jobs holding
    open claims (each single pass is capped). Returns accumulated
    ``released_rows``, ``job_ids``, and ``passes``.
    """
    try:
        max_p = max(1, int(max_passes))
    except (TypeError, ValueError):
        max_p = 20
    total_released = 0
    all_job_ids: list[int] = []
    passes = 0
    for _ in range(max_p):
        passes += 1
        summary = reconcile_orphan_work_claims(limit_jobs=limit_jobs)
        released = int(summary.get("released_rows") or 0)
        total_released += released
        all_job_ids.extend(summary.get("job_ids") or [])
        if released == 0:
            break
    if passes > 1 and total_released:
        logger.info(
            "reconcile_orphan_work_claims_all: %s pass(es), %s claim row(s) released",
            passes,
            total_released,
        )
    return {"released_rows": total_released, "job_ids": all_job_ids, "passes": passes}


def release_claims_for_job(job_id: int) -> int:
    """Release open claims for a job. Returns number of rows updated."""
    row = db.get_connector().query_one(
        """
        SELECT COUNT(*) AS cnt FROM image_phase_work_claims
        WHERE job_id = ? AND status IN ('queued', 'running')
        """,
        (int(job_id),),
    )
    count = int((row or {}).get("cnt") or 0)
    if count:
        db.get_connector().execute(
            """
            UPDATE image_phase_work_claims
            SET status = 'released', released_at = CURRENT_TIMESTAMP
            WHERE job_id = ? AND status IN ('queued', 'running')
            """,
            (int(job_id),),
        )
    return count


def count_claimed_by_other(job_id: int, phase_code: str, image_ids: list[int]) -> int:
    phase = (phase_code or "").strip().lower()
    if not phase or not image_ids:
        return 0
    placeholders = ",".join("?" * len(image_ids))
    row = db.get_connector().query_one(
        f"""
        SELECT COUNT(*) AS cnt FROM image_phase_work_claims
        WHERE phase_code = ?
          AND status IN ('queued', 'running')
          AND job_id != ?
          AND image_id IN ({placeholders})
        """,
        tuple([phase, int(job_id)] + [int(i) for i in image_ids]),
    )
    return int((row or {}).get("cnt") or 0)
