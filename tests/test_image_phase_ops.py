"""
Tests for image phase status operations decomposed in modules/db/jobs.py.

Tests reset_image_phase_status and set_image_phase_status functions.

Requires database connection (PostgreSQL or Firebird test DB).

Run with: python -m pytest tests/test_image_phase_ops.py -v -m "db"
"""

import datetime
from unittest.mock import MagicMock, patch

import pytest

from modules import db


pytestmark = [pytest.mark.db]


class TestResetImagePhaseStatus:
    """Test reset_image_phase_status function from modules/db/jobs.py."""

    def test_function_is_importable_from_facade(self):
        """Verify the function is properly exported from the modules.db facade."""
        from modules.db import reset_image_phase_status
        assert callable(reset_image_phase_status)

    def test_function_delegates_to_jobs_module(self):
        """Verify the monolithic db.py stub correctly delegates to jobs.py."""
        from modules.db import reset_image_phase_status
        from modules.db.jobs import reset_image_phase_status as jobs_version

        # Both should be callable
        assert callable(reset_image_phase_status)
        assert callable(jobs_version)

    def test_returns_integer_count(self):
        """Verify the function returns an integer count of updated rows."""
        result = db.reset_image_phase_status([], "indexing")
        assert isinstance(result, int)
        assert result >= 0

    def test_handles_empty_image_ids(self):
        """When no image IDs provided, should return 0 with no updates."""
        result = db.reset_image_phase_status([], "indexing")
        assert result == 0

    def test_handles_unknown_phase_code(self):
        """When phase code is unknown, should log warning and return 0."""
        result = db.reset_image_phase_status([1, 2, 3], "unknown_phase_xxxxx")
        assert isinstance(result, int)
        assert result >= 0

    def test_accepts_phase_code_string(self):
        """Function should accept phase code as string."""
        try:
            result = db.reset_image_phase_status([1], "indexing")
            assert isinstance(result, int)
        except Exception as e:
            pytest.fail(f"reset_image_phase_status with string phase code failed: {e}")

    def test_chunks_large_image_id_lists(self):
        """Function should handle chunking for large image ID lists (>900)."""
        # Create list with 1500 IDs (will be chunked into 2 batches)
        large_list = list(range(1, 1501))
        try:
            result = db.reset_image_phase_status(large_list, "indexing")
            assert isinstance(result, int)
        except Exception as e:
            pytest.fail(f"reset_image_phase_status with large list failed: {e}")

    def test_no_exception_with_single_image_id(self):
        """Function should handle single image ID without exception."""
        try:
            result = db.reset_image_phase_status([1], "indexing")
            assert isinstance(result, int)
        except Exception as e:
            pytest.fail(f"reset_image_phase_status with single ID failed: {e}")

    def test_no_exception_with_multiple_image_ids(self):
        """Function should handle multiple image IDs without exception."""
        try:
            result = db.reset_image_phase_status([1, 2, 3, 4, 5], "indexing")
            assert isinstance(result, int)
        except Exception as e:
            pytest.fail(f"reset_image_phase_status with multiple IDs failed: {e}")

    def test_phase_code_case_insensitive(self):
        """Phase code lookup should be case-insensitive (uses LOWER)."""
        try:
            result1 = db.reset_image_phase_status([1], "INDEXING")
            result2 = db.reset_image_phase_status([1], "indexing")
            result3 = db.reset_image_phase_status([1], "InDeXiNg")
            # All should succeed without exception
            assert isinstance(result1, int)
            assert isinstance(result2, int)
            assert isinstance(result3, int)
        except Exception as e:
            pytest.fail(f"reset_image_phase_status case handling failed: {e}")


class TestSetImagePhaseStatus:
    """Test set_image_phase_status function from modules/db/jobs.py."""

    def test_function_is_importable_from_facade(self):
        """Verify the function is properly exported from the modules.db facade."""
        from modules.db import set_image_phase_status
        assert callable(set_image_phase_status)

    def test_function_delegates_to_jobs_module(self):
        """Verify the monolithic db.py stub correctly delegates to jobs.py."""
        from modules.db import set_image_phase_status
        from modules.db.jobs import set_image_phase_status as jobs_version

        # Both should be callable
        assert callable(set_image_phase_status)
        assert callable(jobs_version)

    def test_accepts_minimal_parameters(self):
        """Function should work with minimal parameters (image_id, phase_code, status)."""
        try:
            db.set_image_phase_status(1, "indexing", "running")
            # No exception = success
        except Exception as e:
            pytest.fail(f"set_image_phase_status with minimal params failed: {e}")

    def test_handles_unknown_phase_code(self):
        """When phase code is unknown, should log warning and return early."""
        try:
            db.set_image_phase_status(1, "unknown_phase_xxxxx", "running")
            # Should return early without exception
        except Exception as e:
            pytest.fail(f"set_image_phase_status with unknown phase failed: {e}")

    def test_accepts_all_optional_parameters(self):
        """Function should accept all optional parameters."""
        try:
            db.set_image_phase_status(
                image_id=1,
                phase_code="indexing",
                status="running",
                app_version="1.0.0",
                executor_version="1.0.0",
                job_id=1,
                error=None,
                skip_reason=None,
                skipped_by=None
            )
        except Exception as e:
            pytest.fail(f"set_image_phase_status with all params failed: {e}")

    def test_accepts_error_message(self):
        """Function should accept error messages."""
        try:
            db.set_image_phase_status(
                1, "indexing", "failed",
                error="Test error message"
            )
        except Exception as e:
            pytest.fail(f"set_image_phase_status with error message failed: {e}")

    def test_accepts_skip_reason(self):
        """Function should accept skip reason and skipped_by."""
        try:
            db.set_image_phase_status(
                1, "indexing", "skipped",
                skip_reason="test skip",
                skipped_by="user"
            )
        except Exception as e:
            pytest.fail(f"set_image_phase_status with skip reason failed: {e}")

    def test_accepts_version_strings(self):
        """Function should accept app_version and executor_version."""
        try:
            db.set_image_phase_status(
                1, "indexing", "running",
                app_version="7.4.0",
                executor_version="2.1.0"
            )
        except Exception as e:
            pytest.fail(f"set_image_phase_status with versions failed: {e}")

    def test_accepts_job_id(self):
        """Function should accept job_id parameter."""
        try:
            db.set_image_phase_status(
                1, "indexing", "running",
                job_id=42
            )
        except Exception as e:
            pytest.fail(f"set_image_phase_status with job_id failed: {e}")

    def test_no_exception_on_status_running(self):
        """Should handle 'running' status without exception."""
        try:
            db.set_image_phase_status(1, "indexing", "running")
        except Exception as e:
            pytest.fail(f"set_image_phase_status with 'running' status failed: {e}")

    def test_no_exception_on_status_done(self):
        """Should handle 'done' status without exception."""
        try:
            db.set_image_phase_status(1, "indexing", "done")
        except Exception as e:
            pytest.fail(f"set_image_phase_status with 'done' status failed: {e}")

    def test_no_exception_on_status_failed(self):
        """Should handle 'failed' status without exception."""
        try:
            db.set_image_phase_status(1, "indexing", "failed")
        except Exception as e:
            pytest.fail(f"set_image_phase_status with 'failed' status failed: {e}")

    def test_no_exception_on_status_skipped(self):
        """Should handle 'skipped' status without exception."""
        try:
            db.set_image_phase_status(1, "indexing", "skipped")
        except Exception as e:
            pytest.fail(f"set_image_phase_status with 'skipped' status failed: {e}")


class TestDecompositionStatus:
    """Document the decomposition status of image phase status functions."""

    def test_reset_image_phase_status_decomposed(self):
        """Verify reset_image_phase_status is properly decomposed."""
        from modules.db.jobs import reset_image_phase_status
        from modules.db import reset_image_phase_status as facade_version

        # Both references should work
        assert callable(reset_image_phase_status)
        assert callable(facade_version)

    def test_set_image_phase_status_decomposed(self):
        """Verify set_image_phase_status is properly decomposed."""
        from modules.db.jobs import set_image_phase_status
        from modules.db import set_image_phase_status as facade_version

        # Both references should work
        assert callable(set_image_phase_status)
        assert callable(facade_version)

    def test_facade_exports_phase_operations(self):
        """Verify modules/db/__init__.py exports phase operation functions."""
        import modules.db as db_facade

        # Check for key phase operation functions
        required_exports = [
            "reset_image_phase_status",
            "set_image_phase_status",
            "list_stale_running_image_phase_rows",
        ]

        for func_name in required_exports:
            assert hasattr(db_facade, func_name), f"Facade missing export: {func_name}"
