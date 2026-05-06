"""Tests for the empty-scope defensive guard in MetadataRunner.

Regression coverage for job 2140 / folder 71957 — the metadata phase ran for
17ms and silently advanced because ``get_images_by_folder`` returned an empty
list while the folder actually held 1544 indexed images. The guard fails the
phase loudly when scope=0 but the folder demonstrably has indexed images.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def runner():
    """Build a MetadataRunner without importing the live db at module scope.

    The runner's __init__ does not touch the DB, so a vanilla instance is fine
    once we patch the module-level ``db`` reference for the methods under test.
    """
    from modules.metadata_runner import MetadataRunner

    return MetadataRunner()


def _patch_db(**overrides):
    """Patch ``modules.metadata_runner.db`` with sensible no-op defaults."""
    db_mock = MagicMock()
    db_mock.get_all_images.return_value = []
    db_mock.get_images_by_folder.return_value = []
    db_mock.list_folder_paths_under_scope.return_value = []
    db_mock.get_image_details.return_value = None
    db_mock.invalidate_folder_images_cache.return_value = None
    db_mock.invalidate_folder_phase_aggregates.return_value = None
    db_mock.create_job.return_value = 9999
    db_mock.update_job_status.return_value = None
    db_mock.job_should_stop_processing.return_value = False
    db_mock.get_job.return_value = {"status": "completed"}
    db_mock.JOB_TERMINAL_STATES = {"completed", "failed", "interrupted", "cancelled"}
    db_mock.GRACEFUL_PAUSE_MSG = "graceful pause"
    db_mock.reconcile_stale_running_phases_for_jobs.return_value = None
    db_mock.get_image_count.return_value = 0
    for k, v in overrides.items():
        setattr(db_mock, k, v)
    return patch("modules.metadata_runner.db", db_mock), db_mock


def _patch_event_manager():
    return patch("modules.metadata_runner.event_manager", MagicMock())


def _patch_filter_passthrough():
    return patch(
        "modules.metadata_runner.filter_image_rows_for_nef_policy",
        side_effect=lambda rows: rows,
    )


def test_empty_scope_with_indexed_folder_fails_loudly(runner, tmp_path):
    """Scope=0 + folder has indexed images → phase fails (does not silently complete)."""
    folder = tmp_path / "shoot"
    folder.mkdir()

    db_patch, db_mock = _patch_db(
        get_images_by_folder=MagicMock(return_value=[]),
        get_image_count=MagicMock(return_value=1544),
    )
    with db_patch, _patch_event_manager(), _patch_filter_passthrough():
        runner._run_batch_internal(
            input_path=str(folder),
            job_id=2140,
            skip_existing=True,
            resolved_image_ids=None,
            report_collector=None,
        )

    failed_calls = [
        c for c in db_mock.update_job_status.call_args_list
        if len(c.args) >= 2 and c.args[1] == "failed"
    ]
    assert failed_calls, (
        f"Expected update_job_status(..., 'failed') when scope was empty but "
        f"folder had indexed images; got {db_mock.update_job_status.call_args_list!r}"
    )
    assert runner.status_message == "Error Empty Scope"


def test_empty_scope_with_empty_folder_does_not_fail(runner, tmp_path):
    """Scope=0 + folder genuinely empty → no error, runner proceeds (and finds nothing)."""
    folder = tmp_path / "shoot"
    folder.mkdir()

    db_patch, db_mock = _patch_db(
        get_images_by_folder=MagicMock(return_value=[]),
        get_image_count=MagicMock(return_value=0),
    )
    with db_patch, _patch_event_manager(), _patch_filter_passthrough():
        runner._run_batch_internal(
            input_path=str(folder),
            job_id=2140,
            skip_existing=True,
            resolved_image_ids=None,
            report_collector=None,
        )

    assert runner.status_message != "Error Empty Scope"
    failed_calls = [
        c for c in db_mock.update_job_status.call_args_list
        if len(c.args) >= 2 and c.args[1] == "failed"
    ]
    assert not failed_calls, (
        f"Empty folder should not fail the phase; got "
        f"{db_mock.update_job_status.call_args_list!r}"
    )


def test_resolved_image_ids_skips_guard(runner, tmp_path):
    """When the dispatcher passed an explicit ID list, the empty-scope guard must not fire."""
    folder = tmp_path / "shoot"
    folder.mkdir()

    # Even with 0 matched images and a populated folder, the guard should not
    # trigger because the caller explicitly asked for a (possibly empty) set.
    db_patch, db_mock = _patch_db(
        get_all_images=MagicMock(return_value=[]),
        get_image_count=MagicMock(return_value=1544),
    )
    with db_patch, _patch_event_manager(), _patch_filter_passthrough():
        runner._run_batch_internal(
            input_path=str(folder),
            job_id=2140,
            skip_existing=True,
            resolved_image_ids=[1, 2, 3],
            report_collector=None,
        )

    assert runner.status_message != "Error Empty Scope"
