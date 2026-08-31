"""Tests for run_phase_planner reason bucketing."""

from unittest.mock import patch

from modules.phases import PhaseCode, PhaseExecutor, PhaseRegistry, SCORING_EXECUTOR_VERSION
from modules import phases_policy
from modules.run_phase_planner import _reason_bucket, plan_scope, to_legacy_repair_plan


def test_reason_bucket_mapping():
    assert _reason_bucket("missing_phase_status") == "missing_row"
    assert _reason_bucket("status_not_started") == "not_started"
    assert _reason_bucket("status_failed") == "failed"
    assert _reason_bucket("executor_version_changed") == "stale_executor"
    assert _reason_bucket("already_running") == "stale_running"
    assert _reason_bucket("missing_scoring_data") == "missing_data"


@patch("modules.run_phase_planner._images_in_scope", return_value=[1, 2])
@patch("modules.run_phase_planner._needs_work_for_phase")
def test_plan_scope_dry_run_shape(mock_needs, _mock_scope):
    mock_needs.side_effect = [
        (True, "missing_phase_status"),
        (False, "already_done_current_executor"),
        (True, "executor_version_changed"),
    ]
    plan = plan_scope(["/tmp"], ["indexing"], dry_run=True)
    legacy = to_legacy_repair_plan(plan)
    assert legacy["dry_run"] is True
    assert "stage_queues" in legacy
    assert "issue_counts_by_reason" in plan
    assert plan["stage_queues"]["indexing"] == [1]


@patch("modules.run_phase_planner._images_in_scope", return_value=[1, 2])
@patch("modules.run_phase_planner._needs_work_for_phase")
def test_plan_scope_can_ignore_stale_executor(mock_needs, _mock_scope):
    mock_needs.side_effect = [
        (True, "executor_version_changed"),
        (True, "missing_scoring_data"),
    ]

    plan = plan_scope(
        ["/tmp"],
        ["scoring"],
        dry_run=True,
        include_stale_executor=False,
    )

    assert plan["stage_queues"]["scoring"] == [2]
    assert plan["issue_counts_by_reason"] == {"missing_data": 1}
    assert plan["ignored_counts_by_reason"] == {"stale_executor": 1}


@patch("modules.run_phase_planner._images_in_scope", return_value=[1, 2])
def test_plan_scope_empty_queues_legacy_null_metadata_and_canonical_scoring(_mock_scope, monkeypatch):
    """Legacy done rows with NULL executor_version must not inflate stage_queues."""
    PhaseRegistry._executors.clear()
    PhaseRegistry.register(PhaseExecutor(code=PhaseCode.METADATA, executor_version="1.0.0"))
    PhaseRegistry.register(
        PhaseExecutor(code=PhaseCode.SCORING, executor_version=SCORING_EXECUTOR_VERSION),
    )

    def _statuses(image_id):
        return {
            "metadata": {"status": "done", "executor_version": None},
            "scoring": {"status": "done", "executor_version": SCORING_EXECUTOR_VERSION},
        }

    monkeypatch.setattr(phases_policy.db, "get_image_phase_statuses", _statuses)
    monkeypatch.setattr(
        phases_policy.db,
        "get_image_phase_statuses_bulk",
        lambda image_ids: {iid: _statuses(iid) for iid in image_ids},
    )
    monkeypatch.setattr(phases_policy.db, "is_image_metadata_complete", lambda _i: True)
    monkeypatch.setattr(phases_policy.db, "get_image_metadata_asset_gap_reason", lambda _i: None)
    monkeypatch.setattr(phases_policy.db, "is_image_scoring_complete", lambda _i: True)

    plan = plan_scope(["/tmp/folder"], ["metadata", "scoring"], dry_run=True)

    PhaseRegistry._executors.clear()
    assert plan["stage_queues"]["metadata"] == []
    assert plan["stage_queues"]["scoring"] == []


@patch("modules.run_phase_planner._images_in_scope", return_value=[1, 2, 3])
def test_plan_scope_prefetches_statuses_in_bulk(_mock_scope, monkeypatch):
    """The bulk prefetch must satisfy the planner without per-image status calls."""
    PhaseRegistry._executors.clear()
    PhaseRegistry.register(PhaseExecutor(code=PhaseCode.SCORING, executor_version="1.0.0"))

    bulk_calls = []

    def _bulk(image_ids):
        bulk_calls.append(list(image_ids))
        # All three images need scoring (no status row -> not_started).
        return {iid: {"scoring": {"status": "not_started"}} for iid in image_ids}

    def _per_image(_image_id):
        raise AssertionError("per-image get_image_phase_statuses must not be called")

    monkeypatch.setattr(phases_policy.db, "get_image_phase_statuses_bulk", _bulk)
    monkeypatch.setattr(phases_policy.db, "get_image_phase_statuses", _per_image)
    monkeypatch.setattr(phases_policy.db, "is_image_scoring_complete", lambda _i: False)

    plan = plan_scope(["/tmp/folder"], ["scoring"], dry_run=True)

    PhaseRegistry._executors.clear()
    assert bulk_calls == [[1, 2, 3]]  # exactly one bulk fetch for the whole scope
    assert plan["stage_queues"]["scoring"] == [1, 2, 3]


@patch("modules.run_phase_planner._images_in_scope", return_value=[1])
def test_plan_scope_kill_switch_uses_per_image_path(_mock_scope, monkeypatch):
    """auto_drive.bulk_phase_status=False restores the per-image lookup path."""
    PhaseRegistry._executors.clear()
    PhaseRegistry.register(PhaseExecutor(code=PhaseCode.SCORING, executor_version="1.0.0"))

    monkeypatch.setattr(
        "modules.run_phase_planner._bulk_phase_status_enabled", lambda: False
    )

    def _bulk(_image_ids):
        raise AssertionError("bulk fetch must not run when the kill switch is off")

    monkeypatch.setattr(phases_policy.db, "get_image_phase_statuses_bulk", _bulk)
    monkeypatch.setattr(
        phases_policy.db,
        "get_image_phase_statuses",
        lambda _i: {"scoring": {"status": "not_started"}},
    )
    monkeypatch.setattr(phases_policy.db, "is_image_scoring_complete", lambda _i: False)

    plan = plan_scope(["/tmp/folder"], ["scoring"], dry_run=True)

    PhaseRegistry._executors.clear()
    assert plan["stage_queues"]["scoring"] == [1]


# ──────────────────────────────────────────────────────────────────────────────
# Phantom-score preflight. A scoring job interrupted between the per-model write
# and the ResultWorker finalize leaves score_general NULL with a not_started phase
# row. The scoring predicate then reports no work (model rows exist) while the
# bucketer keeps re-queueing the folder and culling aborts on the missing
# composite — auto-drive spins until the loop guard stops it. plan_scope must
# finalize those images before it builds the stage queues.
# ──────────────────────────────────────────────────────────────────────────────

@patch("modules.run_phase_planner._images_in_scope", return_value=[])
def test_apply_run_finalizes_phantom_scores(_mock_scope, monkeypatch):
    calls = []

    def _fake_finalize(*, scope_path=None, dry_run=True, **kw):
        calls.append((scope_path, dry_run))
        return {"candidates": 3, "composites_backfilled": 3, "phase_finalized": 3}

    monkeypatch.setattr(
        "modules.phantom_score_finalize.finalize_phantom_scores", _fake_finalize
    )
    monkeypatch.setattr(
        "modules.db.reconcile_stale_running_phases_for_terminal_jobs", lambda **kw: 0
    )
    monkeypatch.setattr("modules.db.backfill_index_meta_for_folder", lambda p: 0)

    plan = plan_scope(["/tmp/folder"], ["scoring"], dry_run=False)

    assert calls == [("/tmp/folder", False)], "preflight must finalize with writes enabled"
    assert plan["actions"]["phantom_scores_finalized"] == 3
    assert plan["repaired"] == 3


@patch("modules.run_phase_planner._images_in_scope", return_value=[])
def test_dry_run_plan_never_writes_phantom_scores(_mock_scope, monkeypatch):
    def _must_not_run(**kw):
        raise AssertionError("a dry-run plan must not finalize anything")

    monkeypatch.setattr(
        "modules.phantom_score_finalize.finalize_phantom_scores", _must_not_run
    )
    plan = plan_scope(["/tmp/folder"], ["scoring"], dry_run=True)
    assert plan["actions"]["phantom_scores_finalized"] == 0
    assert plan["repaired"] == 0
