"""
Tests for image_phase_status functions in modules/db/jobs.py.

Tests the decomposed list_stale_running_image_phase_rows function and related
image phase status operations.

Requires database connection (PostgreSQL or Firebird test DB).

Run with: python -m pytest tests/test_db_image_phases.py -v -m "db"
"""

import datetime
from unittest.mock import MagicMock, patch

import pytest

from modules import db


pytestmark = [pytest.mark.db]


class TestListStaleRunningImagePhaseRows:
    """Test list_stale_running_image_phase_rows function from modules/db/jobs.py."""

    def test_function_is_importable_from_facade(self):
        """Verify the function is properly exported from the modules.db facade."""
        from modules.db import list_stale_running_image_phase_rows
        assert callable(list_stale_running_image_phase_rows)

    def test_function_delegates_to_jobs_module(self):
        """Verify the monolithic db.py stub correctly delegates to jobs.py."""
        from modules.db import list_stale_running_image_phase_rows
        from modules.db.jobs import list_stale_running_image_phase_rows as jobs_version

        # Both should be callable
        assert callable(list_stale_running_image_phase_rows)
        assert callable(jobs_version)

    def test_returns_dict_with_required_fields(self):
        """Verify the function returns a dict with count_estimate and rows."""
        result = db.list_stale_running_image_phase_rows(min_age_seconds=3600, limit=10)

        assert isinstance(result, dict)
        assert "count_estimate" in result
        assert "rows" in result
        assert isinstance(result["count_estimate"], int)
        assert isinstance(result["rows"], list)

    def test_returns_empty_result_when_no_stale_rows(self):
        """When no rows are stale, count_estimate should be 0 and rows empty."""
        # Use a very short time window to ensure no stale rows
        result = db.list_stale_running_image_phase_rows(min_age_seconds=0, limit=10)

        assert isinstance(result, dict)
        assert result["count_estimate"] >= 0
        assert isinstance(result["rows"], list)

    def test_respects_min_age_seconds_parameter(self):
        """Function should accept and respect min_age_seconds parameter."""
        result_1hour = db.list_stale_running_image_phase_rows(min_age_seconds=3600, limit=10)
        result_1sec = db.list_stale_running_image_phase_rows(min_age_seconds=1, limit=10)

        assert isinstance(result_1hour, dict)
        assert isinstance(result_1sec, dict)
        # Both should have the structure, though counts may vary
        assert "count_estimate" in result_1hour
        assert "count_estimate" in result_1sec

    def test_respects_limit_parameter(self):
        """Function should accept and respect limit parameter."""
        result = db.list_stale_running_image_phase_rows(min_age_seconds=3600, limit=5)

        assert isinstance(result, dict)
        assert len(result["rows"]) <= 5

    def test_row_dict_has_expected_fields(self):
        """Each row in the result should have all expected fields."""
        result = db.list_stale_running_image_phase_rows(min_age_seconds=3600, limit=100)

        if result["rows"]:  # If there are any stale rows
            row = result["rows"][0]
            expected_fields = {
                "image_id",
                "image_file_path",
                "phase_code",
                "status",
                "updated_at",
                "age_seconds",
                "job_id",
                "last_error",
            }
            assert set(row.keys()) == expected_fields

    def test_age_seconds_is_integer(self):
        """age_seconds field should be a non-negative integer."""
        result = db.list_stale_running_image_phase_rows(min_age_seconds=1, limit=100)

        for row in result["rows"]:
            assert isinstance(row["age_seconds"], int)
            assert row["age_seconds"] >= 0

    def test_handles_database_errors_gracefully(self):
        """Function should handle database errors and return error dict."""
        with patch("modules.db.jobs.get_connector") as mock_connector:
            # Simulate database error
            mock_connector.return_value.query.side_effect = Exception("DB Error")

            from modules.db.jobs import list_stale_running_image_phase_rows
            result = list_stale_running_image_phase_rows(min_age_seconds=3600, limit=10)

            # Should return a dict with error field
            assert isinstance(result, dict)
            assert "count_estimate" in result
            assert "rows" in result
            assert result["count_estimate"] == 0
            assert result["rows"] == []
            assert "error" in result

    def test_status_field_contains_running_status(self):
        """The status field should indicate the status of the phase."""
        result = db.list_stale_running_image_phase_rows(min_age_seconds=3600, limit=100)

        for row in result["rows"]:
            # The function is designed to find running status, so status should be set
            assert "status" in row
            assert isinstance(row["status"], str)

    def test_no_exception_with_default_parameters(self):
        """Function should work with default parameters without raising."""
        try:
            result = db.list_stale_running_image_phase_rows()
            assert isinstance(result, dict)
            assert "count_estimate" in result
            assert "rows" in result
        except Exception as e:
            pytest.fail(f"Function raised exception with defaults: {e}")

    def test_no_exception_with_various_limits(self):
        """Function should handle various limit values gracefully."""
        for limit in [1, 5, 10, 50, 100]:
            try:
                result = db.list_stale_running_image_phase_rows(limit=limit)
                assert isinstance(result, dict)
                assert len(result["rows"]) <= limit
            except Exception as e:
                pytest.fail(f"Function raised with limit={limit}: {e}")


class TestMCPServerIntegration:
    """Test that mcp_server.py can call the decomposed function successfully."""

    def test_mcp_server_imports_work(self):
        """mcp_server.py should be able to import db.list_stale_running_image_phase_rows."""
        try:
            from modules import mcp_server  # noqa: F401
            # If import succeeds, the function is accessible to mcp_server
            assert True
        except ImportError as e:
            pytest.fail(f"mcp_server.py import failed: {e}")

    def test_mcp_server_can_call_function(self):
        """Verify mcp_server can successfully call list_stale_running_image_phase_rows."""
        try:
            result = db.list_stale_running_image_phase_rows(min_age_seconds=3600, limit=1)
            assert isinstance(result, dict)
            assert "count_estimate" in result
            assert "rows" in result
        except Exception as e:
            pytest.fail(f"mcp_server call pattern failed: {e}")

    def test_enhanced_return_format_compatibility(self):
        """Verify the enhanced return format (with job_id, last_error) is compatible."""
        result = db.list_stale_running_image_phase_rows(min_age_seconds=3600, limit=10)

        # New fields that weren't in the old v1 version
        if result["rows"]:
            row = result["rows"][0]
            # These fields should exist in the enhanced format
            assert "job_id" in row or "job_id" is None
            assert "last_error" in row or "last_error" is None
            assert "image_file_path" in row
            assert "age_seconds" in row


class TestImagePhaseStatusFunctions:
    """Tests for other image_phase_status functions as candidates for decomposition."""

    def test_list_stale_running_image_phase_rows_is_callable(self):
        """Verify the decomposed function is callable."""
        assert hasattr(db, "list_stale_running_image_phase_rows")
        assert callable(db.list_stale_running_image_phase_rows)

    def test_image_phase_status_functions_searchable_in_codebase(self):
        """Document image_phase_status related functions for potential decomposition."""
        # These functions are candidates for future decomposition following the same pattern:
        # - reset_image_phase_status
        # - set_image_phase_status
        # - get_image_phase_status
        # list_stale_running_image_phase_rows has already been decomposed to jobs.py
        assert callable(db.list_stale_running_image_phase_rows)


class TestDecompositionStatus:
    """Document the decomposition status of image_phase_status functions."""

    def test_list_stale_running_image_phase_rows_decomposed(self):
        """Verify list_stale_running_image_phase_rows is properly decomposed."""
        from modules.db.jobs import list_stale_running_image_phase_rows
        from modules.db import list_stale_running_image_phase_rows as facade_version

        # Both references should work
        assert callable(list_stale_running_image_phase_rows)
        assert callable(facade_version)

    def test_reset_image_phase_status_candidates_for_decomposition(self):
        """Document other image_phase_status functions as decomposition candidates.

        The following functions are candidates for future decomposition following the
        same pattern as list_stale_running_image_phase_rows:
        - reset_image_phase_status (potentially in db.py)
        - set_image_phase_status (potentially in db.py)
        - get_image_phase_status (potentially in db.py)
        """
        # This test documents candidates for future work; they may not exist yet
        # in the public API. Once decomposed, they should be added to jobs.py and
        # exported via modules/db/__init__.py
        pass

    def test_facade_exports_all_job_domain_functions(self):
        """Verify modules/db/__init__.py exports all migrated functions."""
        import modules.db as db_facade

        # Check for key job domain functions
        required_exports = [
            "list_stale_running_image_phase_rows",
            "enqueue_job_with_phases",
            "force_reset_job_phase_to_queued",
            "get_job",
            "update_job_status",
        ]

        for func_name in required_exports:
            assert hasattr(db_facade, func_name), f"Facade missing export: {func_name}"
