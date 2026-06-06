"""Tests for phase work claim helpers (no DB)."""

from unittest.mock import MagicMock, patch

from modules.phase_work_claims import (
    claim_image_phases,
    reconcile_orphan_work_claims,
    reconcile_orphan_work_claims_all,
    release_claims_for_job,
)


@patch("modules.phase_work_claims.db.get_connector")
def test_claim_skips_blocked_other_job(mock_conn):
    connector = MagicMock()
    mock_conn.return_value = connector
    connector.query.return_value = [{"image_id": 10, "job_id": 99}]
    connector.query_one.return_value = {"job_id": 99}

    out = claim_image_phases(1, "scoring", [10])
    assert out["claimed"] == []
    assert out["skipped_already_claimed"] == [10]


@patch("modules.phase_work_claims.db.get_connector")
def test_release_claims_for_job(mock_conn):
    connector = MagicMock()
    mock_conn.return_value = connector
    connector.query_one.return_value = {"cnt": 2}
    n = release_claims_for_job(5)
    assert n == 2
    connector.execute.assert_called_once()


@patch("modules.phase_work_claims.release_claims_for_job")
@patch("modules.phase_work_claims.db.get_connector")
def test_reconcile_orphan_work_claims_releases_terminal_jobs(mock_conn, mock_release):
    connector = MagicMock()
    mock_conn.return_value = connector
    connector.query.return_value = [{"job_id": 10}, {"job_id": 11}]
    mock_release.side_effect = [5, 2]

    out = reconcile_orphan_work_claims(limit_jobs=50)

    assert out["released_rows"] == 7
    assert out["job_ids"] == [10, 11]
    mock_release.assert_any_call(10)
    mock_release.assert_any_call(11)


@patch("modules.phase_work_claims.reconcile_orphan_work_claims")
def test_reconcile_orphan_work_claims_all_loops_until_clear(mock_reconcile):
    mock_reconcile.side_effect = [
        {"released_rows": 100, "job_ids": [1, 2]},
        {"released_rows": 50, "job_ids": [3]},
        {"released_rows": 0, "job_ids": []},
    ]

    out = reconcile_orphan_work_claims_all(limit_jobs=500, max_passes=10)

    assert out["released_rows"] == 150
    assert out["job_ids"] == [1, 2, 3]
    assert out["passes"] == 3
    assert mock_reconcile.call_count == 3
