"""DB-backed per-image phase work claims to prevent duplicate processing across runs."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from modules import db

logger = logging.getLogger(__name__)


def claim_image_phases(
    job_id: int,
    phase_code: str,
    image_ids: List[int],
) -> Dict[str, Any]:
    """Claim ``image_ids`` for ``phase_code`` on ``job_id``. Skip IDs already claimed elsewhere."""
    phase = (phase_code or "").strip().lower()
    claimed: List[int] = []
    skipped: List[int] = []
    if not phase or not image_ids:
        return {"claimed": claimed, "skipped_already_claimed": skipped}

    unique_ids: List[int] = []
    seen: Set[int] = set()
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
    blocked: Dict[int, int] = {}
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


def mark_claims_running(job_id: int, phase_code: str, image_ids: Optional[List[int]] = None) -> None:
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


def count_claimed_by_other(job_id: int, phase_code: str, image_ids: List[int]) -> int:
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
