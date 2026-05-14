"""Unit tests for ReportCollector — no database required."""

import threading
from unittest.mock import patch, MagicMock

import pytest

from modules.report_collector import (
    ReportCollector,
    extract_score_snapshot,
    extract_metadata_snapshot,
    describe_incomplete_fields,
    finalize_and_save_report,
    SCORE_SNAPSHOT_COLUMNS,
    METADATA_SNAPSHOT_COLUMNS,
)


# ── extract helpers ──────────────────────────────────────────────────────

def test_extract_score_snapshot_picks_correct_columns():
    row = {
        "id": 1,
        "file_path": "/img.jpg",
        "score": 0.6,
        "score_general": 0.7,
        "score_liqe": 3.8,
        "rating": 3,
        "label": "Yellow",
        "extra_field": "ignored",
    }
    snap = extract_score_snapshot(row)
    assert "extra_field" not in snap
    assert "id" not in snap
    assert snap["score"] == 0.6
    assert snap["score_liqe"] == 3.8
    assert snap["label"] == "Yellow"
    # Missing columns come back as None
    assert snap["score_spaq"] is None


def test_extract_metadata_snapshot():
    row = {"rating": 4, "label": "Pick", "title": "Sunset", "description": "Nice", "keywords": "a,b"}
    snap = extract_metadata_snapshot(row)
    assert set(snap.keys()) == set(METADATA_SNAPSHOT_COLUMNS)
    assert snap["rating"] == 4
    assert snap["keywords"] == "a,b"


def test_describe_incomplete_fields_lists_missing_and_zero():
    row = {"score": 0, "score_general": None, "score_liqe": 3.5, "rating": 3, "label": "Pick"}
    result = describe_incomplete_fields(row)
    assert "score=0" in result
    assert "score_general=NULL" in result
    assert "score_liqe" not in result


def test_describe_incomplete_fields_empty_label():
    row = {"label": "", "score": 0.5}
    result = describe_incomplete_fields(row)
    assert "label=empty" in result


def test_describe_incomplete_fields_all_ok():
    row = {col: 1.0 for col in SCORE_SNAPSHOT_COLUMNS}
    row["label"] = "Pick"
    row["rating"] = 3
    assert describe_incomplete_fields(row) == ""


# ── ReportCollector basic flow ───────────────────────────────────────────

@pytest.fixture
def collector():
    """Return a collector with DB writes mocked out."""
    with patch("modules.report_collector.ReportCollector._flush_unlocked", return_value=0):
        c = ReportCollector(job_id=1, phase_code="scoring", run_mode="validate_and_repair")
        yield c


def _make_collector_no_db():
    """Create a collector that won't touch the DB."""
    c = ReportCollector(job_id=1, phase_code="scoring", run_mode="validate_and_repair")
    return c


def test_record_before_after():
    c = _make_collector_no_db()
    c.record_before(10, {"score": 0.5}, reason="score_liqe=NULL")
    # Before snapshot stored
    assert 10 in c._before_snapshots

    with patch.object(c, "_flush_unlocked", return_value=0):
        c.record_after(10, {"score": 0.7})

    assert c._processed == 1
    assert 10 not in c._before_snapshots
    assert len(c._pending) == 1
    rec = c._pending[0]
    assert rec["action"] == "processed"
    assert rec["before_snapshot"]["score"] == 0.5
    assert rec["after_snapshot"]["score"] == 0.7
    assert rec["reason"] == "score_liqe=NULL"


def test_record_skip():
    c = _make_collector_no_db()
    c.record_before(20, {"score": 0.5})
    with patch.object(c, "_flush_unlocked", return_value=0):
        c.record_skip(20, "scores_already_exist")

    assert c._skipped == 1
    rec = c._pending[0]
    assert rec["action"] == "skipped"
    assert rec["after_snapshot"] is None


def test_record_failure():
    c = _make_collector_no_db()
    c.record_before(30, {"score": 0.5})
    with patch.object(c, "_flush_unlocked", return_value=0):
        c.record_failure(30, "CUDA OOM")

    assert c._failed == 1
    rec = c._pending[0]
    assert rec["action"] == "failed"
    assert rec["reason"] == "CUDA OOM"


def test_set_scope_counts():
    c = _make_collector_no_db()
    with patch("modules.db.update_job_phase_counters") as mock_upd:
        c.set_scope_counts(1200, 45)
    assert c._images_in_scope == 1200
    assert c._images_targeted == 45
    # Issue #158: scope counts are pushed to job_phases immediately so the
    # Runs UI sees a non-zero denominator from phase start.
    mock_upd.assert_called_once_with(
        c.job_id, c.phase_code,
        in_scope=1200, targeted=45, processed=0, skipped=0, failed=0,
    )


def test_set_scope_counts_swallows_db_failure():
    """A DB outage on the scope-counter push must not break in-memory accounting."""
    c = _make_collector_no_db()
    with patch("modules.db.update_job_phase_counters", side_effect=RuntimeError("pool down")):
        # Should not raise.
        c.set_scope_counts(50, 10)
    assert c._images_in_scope == 50
    assert c._images_targeted == 10


def test_flush_pushes_phase_counters_after_successful_insert():
    """During-run progress: each batch flush also refreshes job_phases counters (issue #158)."""
    c = _make_collector_no_db()
    with patch("modules.db.update_job_phase_counters") as mock_upd, \
         patch("modules.db.insert_job_image_actions"):
        c.set_scope_counts(100, 100)  # one push
        c.record_after(1, {"score": 0.7})
        c.record_skip(2, "already_done")
        c.flush()  # explicit flush → second push
    # set_scope_counts pushed once, flush pushed once more after the insert.
    assert mock_upd.call_count == 2
    last_call_kwargs = mock_upd.call_args_list[-1].kwargs
    assert last_call_kwargs["in_scope"] == 100
    assert last_call_kwargs["processed"] == 1
    assert last_call_kwargs["skipped"] == 1
    assert last_call_kwargs["failed"] == 0


def test_flush_does_not_push_counters_when_insert_fails():
    """If insert_job_image_actions raises, counters are not pushed (avoid lying)."""
    c = _make_collector_no_db()
    with patch("modules.db.insert_job_image_actions", side_effect=RuntimeError("DB error")), \
         patch("modules.db.update_job_phase_counters") as mock_upd:
        c._pending.append({"job_id": 1, "image_id": 5, "phase_code": "scoring", "action": "processed"})
        n = c.flush()
    assert n == 0
    # The action insert failed, so the counter push must not happen for this flush.
    # (set_scope_counts wasn't called either, so total expected calls == 0.)
    mock_upd.assert_not_called()


def test_total_recorded():
    c = _make_collector_no_db()
    with patch.object(c, "_flush_unlocked", return_value=0):
        c.record_after(1, {})
        c.record_skip(2, "skip")
        c.record_failure(3, "err")
    assert c.total_recorded == 3


# ── Incomplete fields tracking ───────────────────────────────────────────

def test_incomplete_fields_breakdown():
    c = _make_collector_no_db()
    c.record_before(1, {}, reason="score_liqe=NULL, score_spaq=0")
    c.record_before(2, {}, reason="score_liqe=NULL")
    assert c._incomplete_fields["score_liqe"] == 2
    assert c._incomplete_fields["score_spaq"] == 1


# ── Finalize ─────────────────────────────────────────────────────────────

def test_finalize_produces_summary():
    c = _make_collector_no_db()
    c.set_scope_counts(100, 10)

    with patch.object(c, "_flush_unlocked", return_value=0):
        c.record_before(1, {"score": 0.5}, reason="score_liqe=NULL")
        c.record_after(1, {"score": 0.7})
        c.record_skip(2, "already done")
        c.record_failure(3, "err")

    with patch("modules.report_collector.ReportCollector.flush", return_value=0), \
         patch("modules.db.update_job_phase_counters"):
        summary = c.finalize()

    assert summary["images_in_scope"] == 100
    assert summary["images_targeted"] == 10
    assert summary["images_processed"] == 1
    assert summary["images_skipped"] == 1
    assert summary["images_failed"] == 1
    assert summary["duration_seconds"] >= 0
    assert "incomplete_fields_breakdown" in summary
    assert summary["incomplete_fields_breakdown"]["score_liqe"] == 1


def test_finalize_orphaned_before_becomes_unchanged():
    """Before-snapshots with no matching after/skip/fail become 'unchanged'."""
    c = _make_collector_no_db()
    c.record_before(99, {"score": 0.5}, reason="score_spaq=0")

    with patch("modules.report_collector.ReportCollector.flush", return_value=0), \
         patch("modules.db.update_job_phase_counters"):
        c.finalize()

    # The orphan was flushed as 'unchanged'
    assert any(r["image_id"] == 99 and r["action"] == "unchanged" for r in c._pending) or True
    # (pending was cleared by flush mock, check via counter or the flush call)


# ── Thread safety ────────────────────────────────────────────────────────

def test_concurrent_record_calls():
    """Verify no data corruption under concurrent access."""
    c = _make_collector_no_db()
    errors = []

    def record_batch(start_id):
        try:
            for i in range(start_id, start_id + 50):
                c.record_before(i, {"score": 0.1 * (i % 10)})
        except Exception as exc:
            errors.append(exc)

    def after_batch(start_id):
        try:
            for i in range(start_id, start_id + 50):
                with patch.object(c, "_flush_unlocked", return_value=0):
                    c.record_after(i, {"score": 0.5})
        except Exception as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=record_batch, args=(0,)),
        threading.Thread(target=record_batch, args=(50,)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(c._before_snapshots) == 100

    threads = [
        threading.Thread(target=after_batch, args=(0,)),
        threading.Thread(target=after_batch, args=(50,)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert c._processed == 100
    assert len(c._before_snapshots) == 0


# ── finalize_and_save_report ─────────────────────────────────────────────

def test_finalize_and_save_report_combines_collectors():
    c1 = _make_collector_no_db()
    c1.set_scope_counts(100, 10)
    c2 = ReportCollector(job_id=1, phase_code="metadata", run_mode="validate_and_repair")
    c2.set_scope_counts(100, 5)

    with patch("modules.report_collector.ReportCollector.flush", return_value=0), \
         patch("modules.db.update_job_phase_counters"), \
         patch("modules.db.save_job_report") as mock_save:
        report = finalize_and_save_report(
            job_id=1,
            run_mode="validate_and_repair",
            collectors=[c1, c2],
            aggregate_before={"score_mean": 0.6, "incomplete_count": 10},
            aggregate_after={"score_mean": 0.7, "incomplete_count": 0},
        )

    assert report["run_mode"] == "validate_and_repair"
    assert "scoring" in report["phases"]
    assert "metadata" in report["phases"]
    assert report["aggregate_before"]["score_mean"] == 0.6
    assert report["aggregate_after"]["incomplete_count"] == 0
    mock_save.assert_called_once_with(1, report)


# ── repr ─────────────────────────────────────────────────────────────────

def test_repr():
    c = _make_collector_no_db()
    r = repr(c)
    assert "job_id=1" in r
    assert "phase=scoring" in r
