"""
Per-image execution trail collector for job runs.

Accumulates before/after score snapshots and action decisions during
phase execution, then flushes them to ``job_image_actions`` in batches.
Produces a structured summary dict for ``jobs.report_json``.

Thread-safe: the scoring pipeline uses PrepWorker / ScoringWorker / ResultWorker
threads that may call ``record_*`` concurrently.
"""
from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)

# Score columns captured in before/after snapshots (scoring phase). Per-model
# values (spaq/ava/liqe/koniq/paq2piq) live in ``image_model_scores`` and are
# overlaid into the row dict by ``modules.job_dispatcher`` before snapshot
# extraction, so they appear here even though ``images`` no longer carries
# typed ``score_<name>`` columns (backend migration 0016 → drop migration).
SCORE_SNAPSHOT_COLUMNS = (
    "score",
    "score_general",
    "score_technical",
    "score_aesthetic",
    "score_spaq",
    "score_ava",
    "score_liqe",
    "rating",
    "label",
)

# Metadata columns captured for metadata phase snapshots.
METADATA_SNAPSHOT_COLUMNS = (
    "rating",
    "label",
    "title",
    "description",
    "keywords",
)

# Default flush threshold (number of pending records).
_FLUSH_THRESHOLD = 200


def extract_score_snapshot(row: dict) -> dict:
    """Extract score-related fields from an image row dict."""
    return {col: row.get(col) for col in SCORE_SNAPSHOT_COLUMNS}


def extract_metadata_snapshot(row: dict) -> dict:
    """Extract metadata-related fields from an image row dict."""
    return {col: row.get(col) for col in METADATA_SNAPSHOT_COLUMNS}


def describe_incomplete_fields(row: dict) -> str:
    """Build a human-readable reason string listing which score fields are missing/zero."""
    parts = []
    for col in SCORE_SNAPSHOT_COLUMNS:
        val = row.get(col)
        # Skip legacy columns if they happen to be in the list but are NULL
        if col in ("score_koniq", "score_paq2piq"):
            continue
        if col == "label":
            if val is None or (isinstance(val, str) and not val.strip()):
                parts.append(f"{col}=empty")
        elif val is None:
            parts.append(f"{col}=NULL")
        elif isinstance(val, (int, float)) and val < 0:
            parts.append(f"{col}={val}")
        elif isinstance(val, (int, float)) and val == 0:
            # Zero can be a valid normalized score; only flag when policy treats zero as empty.
            if col in ("score", "score_general"):
                parts.append(f"{col}=0")
    return ", ".join(parts) if parts else ""


class ReportCollector:
    """Collects per-image execution actions for a single job phase.

    Usage::

        collector = ReportCollector(job_id=42, phase_code="scoring", run_mode="validate_and_repair")
        collector.record_before(image_id=1, snapshot={"score": 0.5, ...}, reason="score_liqe=NULL")
        # ... runner processes image ...
        collector.record_after(image_id=1, snapshot={"score": 0.7, ...})
        # at end of phase:
        summary = collector.finalize()
    """

    def __init__(self, job_id: int, phase_code: str, run_mode: str = ""):
        self.job_id = job_id
        self.phase_code = phase_code
        self.run_mode = run_mode

        self._lock = threading.Lock()
        # Pending records to flush: list of dicts ready for DB insert.
        self._pending: list[dict] = []
        # In-flight before-snapshots awaiting after/skip/fail (keyed by image_id).
        self._before_snapshots: dict[int, dict] = {}
        self._before_reasons: dict[int, str] = {}

        # Counters for the summary.
        self._images_in_scope = 0
        self._images_targeted = 0
        self._processed = 0
        self._skipped = 0
        self._failed = 0

        # Track incomplete field counts for validate_and_repair breakdown.
        self._incomplete_fields: dict[str, int] = {}

        self._start_time: float = time.monotonic()

    # ------------------------------------------------------------------
    # Recording API (called from runners / pipeline workers)
    # ------------------------------------------------------------------

    def set_scope_counts(self, in_scope: int, targeted: int) -> None:
        """Set the total image counts for this phase and push them to ``job_phases``.

        The push makes the denominator visible in the Runs UI from the moment the
        runner knows scope, instead of waiting for ``finalize()`` (see issue #158).
        """
        with self._lock:
            self._images_in_scope = in_scope
            self._images_targeted = targeted
            self._push_phase_counters_unlocked()

    def record_before(
        self,
        image_id: int,
        snapshot: dict,
        reason: str = "",
    ) -> None:
        """Record the before-state of an image selected for processing."""
        with self._lock:
            self._before_snapshots[image_id] = snapshot
            if reason:
                self._before_reasons[image_id] = reason
                # Count individual incomplete fields.
                for part in reason.split(", "):
                    field = part.split("=")[0] if "=" in part else part
                    if field:
                        self._incomplete_fields[field] = self._incomplete_fields.get(field, 0) + 1

    def record_after(
        self,
        image_id: int,
        snapshot: dict,
        action: str = "processed",
    ) -> None:
        """Record the after-state of a successfully processed image."""
        with self._lock:
            before = self._before_snapshots.pop(image_id, None)
            reason = self._before_reasons.pop(image_id, None)
            self._processed += 1
            self._pending.append({
                "job_id": self.job_id,
                "image_id": image_id,
                "phase_code": self.phase_code,
                "action": action,
                "reason": reason,
                "before_snapshot": before,
                "after_snapshot": snapshot,
            })
            if len(self._pending) >= _FLUSH_THRESHOLD:
                self._flush_unlocked()

    def record_skip(self, image_id: int, reason: str) -> None:
        """Record that an image was skipped (not processed)."""
        with self._lock:
            before = self._before_snapshots.pop(image_id, None)
            self._before_reasons.pop(image_id, None)
            self._skipped += 1
            self._pending.append({
                "job_id": self.job_id,
                "image_id": image_id,
                "phase_code": self.phase_code,
                "action": "skipped",
                "reason": reason,
                "before_snapshot": before,
                "after_snapshot": None,
            })
            if len(self._pending) >= _FLUSH_THRESHOLD:
                self._flush_unlocked()

    def record_failure(self, image_id: int, error: str) -> None:
        """Record that processing failed for an image."""
        with self._lock:
            before = self._before_snapshots.pop(image_id, None)
            self._before_reasons.pop(image_id, None)
            self._failed += 1
            self._pending.append({
                "job_id": self.job_id,
                "image_id": image_id,
                "phase_code": self.phase_code,
                "action": "failed",
                "reason": error,
                "before_snapshot": before,
                "after_snapshot": None,
            })
            if len(self._pending) >= _FLUSH_THRESHOLD:
                self._flush_unlocked()

    # ------------------------------------------------------------------
    # Flush & Finalize
    # ------------------------------------------------------------------

    def flush(self) -> int:
        """Flush pending records to DB. Returns number of rows written."""
        with self._lock:
            return self._flush_unlocked()

    def _flush_unlocked(self) -> int:
        """Flush without acquiring the lock (caller must hold it)."""
        if not self._pending:
            return 0
        batch = list(self._pending)
        try:
            from modules import db
            db.insert_job_image_actions(batch)
            # Only clear after successful write so rows aren't lost on failure.
            self._pending.clear()
        except Exception:
            logger.exception(
                "ReportCollector: failed to flush %d action rows for job %s phase %s — "
                "rows kept in pending for next flush attempt",
                len(batch), self.job_id, self.phase_code,
            )
            return 0
        # Piggyback on the flush cadence to push counters to job_phases so the
        # Runs UI moves during the run (see issue #158).
        self._push_phase_counters_unlocked()
        return len(batch)

    def _push_phase_counters_unlocked(self) -> bool:
        """Push the current counter snapshot to ``job_phases``.

        Best-effort: any failure is logged and not propagated so the in-memory
        accounting (and the per-row ``image_phase_status`` writes) are unaffected.
        Caller must hold ``self._lock`` so the snapshot is consistent.
        """
        try:
            from modules import db
            db.update_job_phase_counters(
                self.job_id,
                self.phase_code,
                in_scope=self._images_in_scope,
                targeted=self._images_targeted,
                processed=self._processed,
                skipped=self._skipped,
                failed=self._failed,
            )
            return True
        except Exception:
            logger.exception(
                "ReportCollector: failed to push job_phases counters for job %s phase %s "
                "(in_scope=%d processed=%d skipped=%d failed=%d)",
                self.job_id, self.phase_code,
                self._images_in_scope, self._processed, self._skipped, self._failed,
            )
            return False

    def get_pending_records(self) -> list:
        """Return a shallow copy of pending (unflushed) records for aggregation purposes.

        Thread-safe; holds lock during copy.
        """
        with self._lock:
            return list(self._pending)

    def finalize(self) -> dict:
        """Flush remaining records and return the phase summary dict.

        Also writes counters to ``job_phases`` if a matching row exists.
        """
        # Flush any remaining before-snapshots that never got an after/skip/fail
        # (shouldn't happen in normal flow, but be defensive).
        with self._lock:
            for image_id in list(self._before_snapshots):
                before = self._before_snapshots.pop(image_id)
                reason = self._before_reasons.pop(image_id, None)
                self._pending.append({
                    "job_id": self.job_id,
                    "image_id": image_id,
                    "phase_code": self.phase_code,
                    "action": "unchanged",
                    "reason": reason or "no_outcome_recorded",
                    "before_snapshot": before,
                    "after_snapshot": None,
                })

        self.flush()

        duration = time.monotonic() - self._start_time

        summary = {
            "images_in_scope": self._images_in_scope,
            "images_targeted": self._images_targeted,
            "images_processed": self._processed,
            "images_skipped": self._skipped,
            "images_failed": self._failed,
            "duration_seconds": round(duration, 2),
        }
        if self._incomplete_fields:
            summary["incomplete_fields_breakdown"] = dict(self._incomplete_fields)

        # Persist counters to job_phases row.
        try:
            from modules import db
            db.update_job_phase_counters(
                self.job_id,
                self.phase_code,
                in_scope=self._images_in_scope,
                targeted=self._images_targeted,
                processed=self._processed,
                skipped=self._skipped,
                failed=self._failed,
            )
        except Exception:
            logger.exception(
                "ReportCollector: failed to update job_phases counters for job %s phase %s",
                self.job_id, self.phase_code,
            )

        return summary

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    @property
    def total_recorded(self) -> int:
        """Total images recorded (processed + skipped + failed)."""
        return self._processed + self._skipped + self._failed

    def __repr__(self) -> str:
        return (
            f"ReportCollector(job_id={self.job_id}, phase={self.phase_code}, "
            f"processed={self._processed}, skipped={self._skipped}, failed={self._failed})"
        )


def finalize_and_save_report(
    job_id: int,
    run_mode: str,
    collectors: list[ReportCollector],
    *,
    aggregate_before: dict | None = None,
    aggregate_after: dict | None = None,
) -> dict:
    """Finalize all collectors for a job and persist the combined report.

    Call this before ``update_job_status()`` so the report is available
    when the post-run quality audit runs.

    Returns the full report dict.
    """
    phases = {}
    for c in collectors:
        phases[c.phase_code] = c.finalize()

    report: dict = {
        "run_mode": run_mode,
        "phases": phases,
    }
    if aggregate_before is not None:
        report["aggregate_before"] = aggregate_before
    if aggregate_after is not None:
        report["aggregate_after"] = aggregate_after

    try:
        from modules import db
        db.save_job_report(job_id, report)
    except Exception:
        logger.exception("finalize_and_save_report: failed to save report for job %s", job_id)

    return report
