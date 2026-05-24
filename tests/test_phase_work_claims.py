"""Tests for phase work claim helpers (no DB)."""

from unittest.mock import MagicMock, patch

from modules.phase_work_claims import claim_image_phases, release_claims_for_job


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
