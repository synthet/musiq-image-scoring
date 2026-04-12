"""
Tests for SelectionRunner phase-aware completion logic.

Validates that when a selection job has multiple phases (e.g. culling + bird_species),
the runner completes only the culling phase and enqueues a follow-up job for remaining
phases instead of bulk-completing everything.
"""

import json
import threading
import pytest
from unittest.mock import patch, MagicMock, call


# ──────────────────────────────────────────────────────────────────────────────
# _resolve_multi_phase_job_phases_sync_code — safety net
# ──────────────────────────────────────────────────────────────────────────────

def test_bulk_completed_blocked_when_unstarted_phases():
    """_resolve_multi_phase should NOT return __bulk_completed__ when phases have never started."""
    from modules.db import _resolve_multi_phase_job_phases_sync_code

    phases = [
        {"phase_code": "culling", "state": "running", "started_at": "2026-03-24T00:00:00"},
        {"phase_code": "bird_species", "state": "pending", "started_at": None},
    ]
    with patch("modules.db.get_job_phases", return_value=phases):
        result = _resolve_multi_phase_job_phases_sync_code(999, "completed")

    # Should NOT bulk-complete; should return the running phase
    assert result != "__bulk_completed__"
    assert result == "culling"


def test_completed_prefers_running_phase_when_all_have_started_at():
    """When a later phase is running, complete that row — never bulk-complete all phases."""
    from modules.db import _resolve_multi_phase_job_phases_sync_code

    phases = [
        {"phase_code": "culling", "state": "completed", "started_at": "2026-03-24T00:00:00"},
        {"phase_code": "bird_species", "state": "running", "started_at": "2026-03-24T00:01:00"},
    ]
    with patch("modules.db.get_job_phases", return_value=phases):
        result = _resolve_multi_phase_job_phases_sync_code(999, "completed")

    assert result == "bird_species"


def test_completed_returns_none_when_all_phases_already_terminal():
    """No phase row to sync when everything is already completed or skipped."""
    from modules.db import _resolve_multi_phase_job_phases_sync_code

    phases = [
        {"phase_code": "culling", "state": "completed", "started_at": "2026-03-24T00:00:00"},
        {"phase_code": "bird_species", "state": "skipped", "started_at": None},
    ]
    with patch("modules.db.get_job_phases", return_value=phases):
        result = _resolve_multi_phase_job_phases_sync_code(999, "completed")

    assert result is None


def test_resolve_empty_phases_returns_none():
    from modules.db import _resolve_multi_phase_job_phases_sync_code

    with patch("modules.db.get_job_phases", return_value=[]):
        assert _resolve_multi_phase_job_phases_sync_code(1, "completed") is None


def test_resolve_single_phase_row_returns_none():
    """Multi-phase logic only applies when there are 2+ job_phases rows."""
    from modules.db import _resolve_multi_phase_job_phases_sync_code

    phases = [
        {"phase_code": "scoring", "state": "running", "started_at": "2026-03-24T00:00:00"},
    ]
    with patch("modules.db.get_job_phases", return_value=phases):
        assert _resolve_multi_phase_job_phases_sync_code(1, "completed") is None


def test_running_prefers_existing_running_row():
    from modules.db import _resolve_multi_phase_job_phases_sync_code

    phases = [
        {"phase_code": "indexing", "state": "completed", "started_at": "2026-03-24T00:00:00"},
        {"phase_code": "scoring", "state": "running", "started_at": "2026-03-24T00:01:00"},
        {"phase_code": "keywords", "state": "pending", "started_at": None},
    ]
    with patch("modules.db.get_job_phases", return_value=phases):
        assert _resolve_multi_phase_job_phases_sync_code(1, "running") == "scoring"


def test_running_maps_to_first_queued_when_none_running():
    from modules.db import _resolve_multi_phase_job_phases_sync_code

    phases = [
        {"phase_code": "indexing", "state": "queued", "started_at": None},
        {"phase_code": "scoring", "state": "pending", "started_at": None},
    ]
    with patch("modules.db.get_job_phases", return_value=phases):
        assert _resolve_multi_phase_job_phases_sync_code(1, "running") == "indexing"


def test_running_fallback_first_row_when_no_running_or_queued():
    from modules.db import _resolve_multi_phase_job_phases_sync_code

    phases = [
        {"phase_code": "alpha", "state": "completed", "started_at": "2026-03-24T00:00:00"},
        {"phase_code": "beta", "state": "completed", "started_at": "2026-03-24T00:01:00"},
    ]
    with patch("modules.db.get_job_phases", return_value=phases):
        assert _resolve_multi_phase_job_phases_sync_code(1, "running") == "alpha"


def test_completed_non_terminal_without_unstarted_row():
    """started_at set on a later phase but state not terminal — still pick that phase."""
    from modules.db import _resolve_multi_phase_job_phases_sync_code

    phases = [
        {"phase_code": "culling", "state": "completed", "started_at": "2026-03-24T00:00:00"},
        {
            "phase_code": "bird_species",
            "state": "queued",
            "started_at": "2026-03-24T00:01:00",
        },
    ]
    with patch("modules.db.get_job_phases", return_value=phases):
        assert _resolve_multi_phase_job_phases_sync_code(1, "completed") == "bird_species"


def test_completed_all_terminal_treats_cancelled_spelling():
    from modules.db import _resolve_multi_phase_job_phases_sync_code

    phases = [
        {"phase_code": "culling", "state": "completed", "started_at": "2026-03-24T00:00:00"},
        {"phase_code": "bird_species", "state": "cancelled", "started_at": None},
    ]
    with patch("modules.db.get_job_phases", return_value=phases):
        assert _resolve_multi_phase_job_phases_sync_code(1, "completed") is None


def test_failed_prefers_running_phase():
    from modules.db import _resolve_multi_phase_job_phases_sync_code

    phases = [
        {"phase_code": "scoring", "state": "completed", "started_at": "2026-03-24T00:00:00"},
        {"phase_code": "keywords", "state": "running", "started_at": "2026-03-24T00:01:00"},
    ]
    with patch("modules.db.get_job_phases", return_value=phases):
        assert _resolve_multi_phase_job_phases_sync_code(1, "failed") == "keywords"


def test_failed_returns_last_phase_when_none_running():
    from modules.db import _resolve_multi_phase_job_phases_sync_code

    phases = [
        {"phase_code": "a", "state": "completed", "started_at": "2026-03-24T00:00:00"},
        {"phase_code": "b", "state": "completed", "started_at": "2026-03-24T00:01:00"},
    ]
    with patch("modules.db.get_job_phases", return_value=phases):
        assert _resolve_multi_phase_job_phases_sync_code(1, "interrupted") == "b"


def test_resolve_misc_job_status_returns_none():
    from modules.db import _resolve_multi_phase_job_phases_sync_code

    phases = [
        {"phase_code": "x", "state": "queued", "started_at": None},
        {"phase_code": "y", "state": "pending", "started_at": None},
    ]
    with patch("modules.db.get_job_phases", return_value=phases):
        assert _resolve_multi_phase_job_phases_sync_code(1, "queued") is None
        assert _resolve_multi_phase_job_phases_sync_code(1, "paused") is None


# ──────────────────────────────────────────────────────────────────────────────
# SelectionRunner._complete_phase_and_advance
# ──────────────────────────────────────────────────────────────────────────────

def test_selection_runner_enqueues_bird_species():
    """When culling finishes and bird_species phase is pending, a follow-up job should be enqueued."""
    from modules.selection_runner import SelectionRunner

    runner = SelectionRunner()
    log_messages = []

    phases_after_culling = [
        {"phase_code": "culling", "state": "completed", "started_at": "2026-03-24T00:00:00", "completed_at": "2026-03-24T00:01:00"},
        {"phase_code": "bird_species", "state": "pending", "started_at": None, "completed_at": None},
    ]

    with patch("modules.selection_runner.db") as mock_db, \
         patch("modules.selection_runner.event_manager") as mock_em:
        mock_db.get_job_phases.return_value = phases_after_culling
        mock_db.enqueue_job.return_value = (500, 1)  # follow-up job_id, position

        runner._complete_phase_and_advance(449, "/mnt/d/Photos/test", log_messages.append)

    # Should have set culling phase to completed
    mock_db.set_job_phase_state.assert_any_call(449, "culling", "completed")

    # Should have enqueued a bird_species job
    mock_db.enqueue_job.assert_called_once()
    enqueue_args = mock_db.enqueue_job.call_args
    assert enqueue_args[1].get("job_type") == "bird_species" or enqueue_args[0][2] == "bird_species"

    # Should have created job phases for the follow-up job
    mock_db.create_job_phases.assert_called_once_with(500, ["bird_species"], first_phase_state="queued")

    # Should mark bird_species as completed on the PARENT job so the UI shows it as fully done
    mock_db.set_job_phase_state.assert_any_call(449, "bird_species", "completed")

    # Should have completed the parent job
    mock_db.update_job_status.assert_called_once_with(449, "completed")

    # Log should mention advancing
    assert any("bird_species" in msg for msg in log_messages)


def test_selection_runner_no_followup_when_no_remaining():
    """When culling is the only phase, just complete the job normally."""
    from modules.selection_runner import SelectionRunner

    runner = SelectionRunner()

    phases_only_culling = [
        {"phase_code": "culling", "state": "completed", "started_at": "2026-03-24T00:00:00", "completed_at": "2026-03-24T00:01:00"},
    ]

    with patch("modules.selection_runner.db") as mock_db, \
         patch("modules.selection_runner.event_manager"):
        mock_db.get_job_phases.return_value = phases_only_culling

        runner._complete_phase_and_advance(449, "/mnt/d/Photos/test", lambda msg: None)

    # Should NOT have enqueued any follow-up job
    mock_db.enqueue_job.assert_not_called()

    # Should have completed the job
    mock_db.update_job_status.assert_called_once_with(449, "completed")


def test_parent_job_bird_species_phase_marked_completed():
    """Parent job's bird_species phase row is set to 'completed' so the UI shows the job fully done.

    This is intentional UI-completeness behaviour: the real work happens in the child
    follow-up job, but the parent's phase row must not stay 'pending' indefinitely.
    """
    from modules.selection_runner import SelectionRunner
    from unittest.mock import call

    runner = SelectionRunner()

    phases = [
        {"phase_code": "culling", "state": "completed", "started_at": "2026-03-24T00:00:00", "completed_at": "2026-03-24T00:01:00"},
        {"phase_code": "bird_species", "state": "pending", "started_at": None, "completed_at": None},
    ]

    with patch("modules.selection_runner.db") as mock_db, \
         patch("modules.selection_runner.event_manager"):
        mock_db.get_job_phases.return_value = phases
        mock_db.enqueue_job.return_value = (501, 1)

        runner._complete_phase_and_advance(449, "/mnt/d/Photos/test", lambda msg: None)

    phase_state_calls = mock_db.set_job_phase_state.call_args_list
    assert call(449, "culling", "completed") in phase_state_calls, "culling must be marked completed on parent"
    assert call(449, "bird_species", "completed") in phase_state_calls, (
        "bird_species must be marked completed on parent job for UI visibility"
    )
