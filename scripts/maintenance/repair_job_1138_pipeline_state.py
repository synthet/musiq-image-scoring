#!/usr/bin/env python3
"""One-off transactional repair for pipeline job state drift (job id 1138).

Repair goals:
- Verify target row is a multi-phase pipeline run.
- Correct jobs.job_type to ``pipeline`` if needed.
- Derive metadata phase truth from IMAGE_PHASE_STATUS for this run.
- Deterministically set metadata/scoring job_phases states.
- Recompute jobs.current_phase + jobs.next_phase_index from job_phases.
- Commit only if invariants pass; otherwise rollback with diagnostics.

Rerun-safe: if already corrected, updates are no-ops.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from modules import db  # noqa: E402

TARGET_JOB_ID = 1138
TERMINAL_PHASE_STATES = {"completed", "failed", "skipped", "canceled"}


class RepairError(RuntimeError):
    """Raised when a repair invariant fails and the transaction must rollback."""


@dataclass(frozen=True)
class PhaseTargets:
    metadata_state: str
    scoring_state: str
    metadata_counts: dict[str, int]


def _as_iso(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _norm_state(value: Any, default: str = "pending") -> str:
    s = str(value or "").strip().lower()
    return s or default


def _snapshot(tx, job_id: int) -> dict[str, Any]:
    job = tx.query_one(
        """
        SELECT id, status, job_type, current_phase, next_phase_index, runner_state,
               created_at, started_at, finished_at, completed_at
        FROM jobs
        WHERE id = ?
        """,
        (job_id,),
    )
    phases = tx.query(
        """
        SELECT id, phase_order, phase_code, state, started_at, completed_at, error_message
        FROM job_phases
        WHERE job_id = ?
        ORDER BY phase_order
        """,
        (job_id,),
    )
    meta_agg = tx.query_one(
        """
        SELECT
          COUNT(*) AS total,
          SUM(CASE WHEN LOWER(TRIM(ips.status)) = 'done' THEN 1 ELSE 0 END) AS done_count,
          SUM(CASE WHEN LOWER(TRIM(ips.status)) = 'skipped' THEN 1 ELSE 0 END) AS skipped_count,
          SUM(CASE WHEN LOWER(TRIM(ips.status)) = 'running' THEN 1 ELSE 0 END) AS running_count,
          SUM(CASE WHEN LOWER(TRIM(ips.status)) IN ('not_started', 'queued', 'pending') THEN 1 ELSE 0 END) AS pending_like_count,
          SUM(CASE WHEN LOWER(TRIM(ips.status)) = 'failed' THEN 1 ELSE 0 END) AS failed_count
        FROM image_phase_status ips
        JOIN pipeline_phases pp ON pp.id = ips.phase_id
        WHERE ips.job_id = ?
          AND LOWER(TRIM(pp.code)) = 'metadata'
        """,
        (job_id,),
    ) or {}

    return {
        "job": {k: _as_iso(v) for k, v in (dict(job or {})).items()},
        "job_phases": [{k: _as_iso(v) for k, v in dict(row).items()} for row in phases],
        "metadata_ips": {k: int(meta_agg.get(k) or 0) for k in (
            "total",
            "done_count",
            "skipped_count",
            "running_count",
            "pending_like_count",
            "failed_count",
        )},
    }


def _compute_phase_targets(tx, job_id: int) -> PhaseTargets:
    counts = tx.query_one(
        """
        SELECT
          COUNT(*) AS total,
          SUM(CASE WHEN LOWER(TRIM(ips.status)) = 'done' THEN 1 ELSE 0 END) AS done_count,
          SUM(CASE WHEN LOWER(TRIM(ips.status)) = 'skipped' THEN 1 ELSE 0 END) AS skipped_count,
          SUM(CASE WHEN LOWER(TRIM(ips.status)) = 'running' THEN 1 ELSE 0 END) AS running_count
        FROM image_phase_status ips
        JOIN pipeline_phases pp ON pp.id = ips.phase_id
        WHERE ips.job_id = ?
          AND LOWER(TRIM(pp.code)) = 'metadata'
        """,
        (job_id,),
    ) or {}

    total = int(counts.get("total") or 0)
    done_count = int(counts.get("done_count") or 0)
    skipped_count = int(counts.get("skipped_count") or 0)
    running_count = int(counts.get("running_count") or 0)
    terminal_count = done_count + skipped_count

    # Deterministic truth table for metadata phase.
    if total > 0 and terminal_count == total:
        metadata_state = "completed"
    elif running_count > 0:
        metadata_state = "running"
    else:
        metadata_state = "pending"

    # Orchestrator handoff: scoring should only run after metadata is completed.
    scoring_state = "running" if metadata_state == "completed" else "pending"

    return PhaseTargets(
        metadata_state=metadata_state,
        scoring_state=scoring_state,
        metadata_counts={
            "total": total,
            "done_count": done_count,
            "skipped_count": skipped_count,
            "running_count": running_count,
            "terminal_count": terminal_count,
        },
    )


def _assert_intended_multiphase(tx, job_id: int) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    job = tx.query_one("SELECT id, job_type, status FROM jobs WHERE id = ?", (job_id,))
    if not job:
        raise RepairError(f"jobs.id={job_id} does not exist")

    rows = tx.query(
        """
        SELECT id, phase_order, phase_code, state
        FROM job_phases
        WHERE job_id = ?
          AND LOWER(TRIM(phase_code)) IN ('metadata', 'scoring')
        ORDER BY phase_order
        """,
        (job_id,),
    )
    by_code = {str(r["phase_code"]).strip().lower(): dict(r) for r in rows}

    meta = by_code.get("metadata")
    scoring = by_code.get("scoring")
    if not meta or not scoring:
        raise RepairError(
            f"jobs.id={job_id} is not the expected metadata->scoring multi-phase run "
            f"(found phases={sorted(by_code.keys())})"
        )
    if int(scoring["phase_order"]) <= int(meta["phase_order"]):
        raise RepairError(
            f"jobs.id={job_id} phase ordering invalid: metadata.order={meta['phase_order']} "
            f"scoring.order={scoring['phase_order']}"
        )

    return dict(job), meta, scoring


def _sync_job_cursor(tx, job_id: int) -> None:
    phases = tx.query(
        """
        SELECT phase_order, phase_code, state
        FROM job_phases
        WHERE job_id = ?
        ORDER BY phase_order
        """,
        (job_id,),
    )
    if not phases:
        raise RepairError(f"jobs.id={job_id} has no job_phases rows")

    running = next((p for p in phases if _norm_state(p.get("state")) == "running"), None)
    if running:
        current_phase = running["phase_code"]
        next_idx = int(running["phase_order"])
    else:
        pending_like = next(
            (
                p
                for p in phases
                if _norm_state(p.get("state"))
                in {"pending", "queued", "paused", "restarting", "cancel_requested", "interrupted"}
            ),
            None,
        )
        if pending_like:
            current_phase = pending_like["phase_code"]
            next_idx = int(pending_like["phase_order"])
        else:
            current_phase = None
            next_idx = len(phases)

    tx.execute(
        "UPDATE jobs SET current_phase = ?, next_phase_index = ? WHERE id = ?",
        (current_phase, next_idx, job_id),
    )


def run_repair(job_id: int, dry_run: bool = False) -> dict[str, Any]:
    def _tx(tx):
        diagnostics: list[str] = []

        before = _snapshot(tx, job_id)
        job_row, meta_row, scoring_row = _assert_intended_multiphase(tx, job_id)
        targets = _compute_phase_targets(tx, job_id)

        # 1) jobs.job_type should be pipeline for orchestrator resume/dispatch.
        current_job_type = str(job_row.get("job_type") or "").strip().lower()
        if current_job_type != "pipeline":
            tx.execute("UPDATE jobs SET job_type = 'pipeline' WHERE id = ?", (job_id,))
            diagnostics.append(f"job_type repaired: {job_row.get('job_type')!r} -> 'pipeline'")
        else:
            diagnostics.append("job_type already correct ('pipeline')")

        # 2) Deterministic phase state repair.
        if _norm_state(meta_row.get("state")) != targets.metadata_state:
            tx.execute(
                "UPDATE job_phases SET state = ? WHERE id = ?",
                (targets.metadata_state, meta_row["id"]),
            )
            diagnostics.append(
                f"metadata state repaired: {_norm_state(meta_row.get('state'))} -> {targets.metadata_state}"
            )

        scoring_state = _norm_state(scoring_row.get("state"))
        if scoring_state in TERMINAL_PHASE_STATES and scoring_state != targets.scoring_state:
            raise RepairError(
                "scoring phase is terminal; refusing to force non-terminal handoff state "
                f"(current={scoring_state}, target={targets.scoring_state})"
            )
        if scoring_state != targets.scoring_state:
            tx.execute(
                "UPDATE job_phases SET state = ? WHERE id = ?",
                (targets.scoring_state, scoring_row["id"]),
            )
            diagnostics.append(f"scoring state repaired: {scoring_state} -> {targets.scoring_state}")

        _sync_job_cursor(tx, job_id)

        after = _snapshot(tx, job_id)

        # Post-update invariants.
        meta_after = next(
            (p for p in after["job_phases"] if _norm_state(p.get("phase_code"), default="") == "metadata"),
            None,
        )
        scoring_after = next(
            (p for p in after["job_phases"] if _norm_state(p.get("phase_code"), default="") == "scoring"),
            None,
        )
        if not meta_after or not scoring_after:
            raise RepairError("post-update invariant failed: metadata/scoring job_phases rows missing")

        meta_state_after = _norm_state(meta_after.get("state"))
        scoring_state_after = _norm_state(scoring_after.get("state"))
        if meta_state_after != targets.metadata_state:
            raise RepairError(
                f"post-update invariant failed: metadata state={meta_state_after}, expected={targets.metadata_state}"
            )
        if scoring_state_after != targets.scoring_state:
            raise RepairError(
                f"post-update invariant failed: scoring state={scoring_state_after}, expected={targets.scoring_state}"
            )

        job_after = after["job"]
        if str(job_after.get("job_type") or "").strip().lower() != "pipeline":
            raise RepairError(
                f"post-update invariant failed: jobs.job_type={job_after.get('job_type')!r} (expected 'pipeline')"
            )

        current_phase = _norm_state(job_after.get("current_phase"), default="")
        next_phase_index = int(job_after.get("next_phase_index") or 0)
        if scoring_state_after == "running":
            if current_phase != "scoring":
                raise RepairError(
                    f"post-update invariant failed: current_phase={job_after.get('current_phase')!r} "
                    "while scoring is running"
                )
        elif meta_state_after in {"running", "pending"}:
            if current_phase != "metadata":
                raise RepairError(
                    f"post-update invariant failed: current_phase={job_after.get('current_phase')!r} "
                    f"while metadata is {meta_state_after}"
                )
        if next_phase_index < 0:
            raise RepairError(f"post-update invariant failed: next_phase_index={next_phase_index} < 0")

        report = {
            "job_id": job_id,
            "dry_run": dry_run,
            "metadata_truth": targets.metadata_counts,
            "diagnostics": diagnostics,
            "before": before,
            "after": after,
        }
        print(json.dumps(report, indent=2, sort_keys=True), flush=True)

        if dry_run:
            raise RepairError("dry-run requested: rolling back transactional changes")

        return report

    return db.get_connector().run_transaction(_tx)


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair pipeline/job phase state drift for a single job")
    parser.add_argument("--job-id", type=int, default=TARGET_JOB_ID, help="Target jobs.id (default: 1138)")
    parser.add_argument("--dry-run", action="store_true", help="Compute/report only; force rollback")
    args = parser.parse_args()

    db.init_db()

    try:
        run_repair(job_id=args.job_id, dry_run=args.dry_run)
    except RepairError as e:
        print(f"[repair] rollback: {e}", file=sys.stderr)
        return 2 if args.dry_run else 1
    except Exception as e:  # pragma: no cover - safety for runtime one-off.
        print(f"[repair] rollback: unexpected error: {e}", file=sys.stderr)
        return 1

    print("[repair] commit: all invariants passed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
