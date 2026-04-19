import pytest
from unittest.mock import MagicMock
from modules import db

@pytest.fixture
def mock_connector(monkeypatch):
    mock_conn = MagicMock()
    monkeypatch.setattr(db, "get_connector", lambda: mock_conn)
    return mock_conn

def test_count_jobs_with_status_filter(mock_connector):
    # Mock return value for query_one
    mock_connector.query_one.return_value = {"cnt": 10}

    status_filter = ["completed", "failed"]
    count = db.count_jobs(status_filter=status_filter)

    assert count == 10
    # Verify the SQL and params
    args, _ = mock_connector.query_one.call_args
    sql, params = args
    assert "status IN (?,?)" in sql
    assert params == ("completed", "failed")

def test_get_jobs_with_status_filter(mock_connector):
    # Mock return value for query
    mock_connector.query.return_value = [{"id": 1, "status": "completed"}]

    status_filter = ["completed"]
    rows = db.get_jobs(limit=10, status_filter=status_filter)

    assert len(rows) == 1
    assert rows[0]["id"] == 1

    # Verify the SQL and params
    args, _ = mock_connector.query.call_args
    sql, params = args
    assert "status IN (?)" in sql
    assert "OFFSET ? ROWS FETCH NEXT ? ROWS ONLY" in sql
    # Params order: status_filter, offset, limit
    assert params == ("completed", 0, 10)

def test_get_jobs_with_history_only(mock_connector):
    mock_connector.query.return_value = []

    # This should use _JOB_HISTORY_STATUSES
    db.get_jobs(history_only=True)

    args, _ = mock_connector.query.call_args
    sql, params = args
    # _JOB_HISTORY_STATUSES has 5 items: ("completed", "failed", "canceled", "cancelled", "interrupted")
    assert "status IN (?,?,?,?,?)" in sql
    assert "completed" in params
    assert "failed" in params
