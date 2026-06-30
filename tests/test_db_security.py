"""Tests for SQL injection prevention in db.py sort validation."""
import pytest
from modules.db import _validate_sort, ALLOWED_SORT_COLUMNS, ALLOWED_SORT_ORDERS


class TestValidateSort:
    """Test the _validate_sort function for SQL injection prevention."""

    def test_valid_sort_column(self):
        """Valid column names should pass through unchanged."""
        for col in ALLOWED_SORT_COLUMNS:
            result_col, _ = _validate_sort(col, "desc")
            assert result_col == col

    def test_valid_sort_orders(self):
        """Valid order values should be returned uppercase."""
        _, order = _validate_sort("score_general", "asc")
        assert order == "ASC"
        _, order = _validate_sort("score_general", "desc")
        assert order == "DESC"

    def test_invalid_sort_column_defaults(self):
        """Invalid column names should default to score_general."""
        col, _ = _validate_sort("DROP TABLE images; --", "desc")
        assert col == "score_general"

    def test_sql_injection_in_sort_by(self):
        """SQL injection attempts in sort_by should be sanitized."""
        malicious = [
            "1; DROP TABLE images",
            "score_general; DELETE FROM images",
            "score_general UNION SELECT * FROM jobs",
            "' OR '1'='1",
            "score_general--",
        ]
        for payload in malicious:
            col, _ = _validate_sort(payload, "desc")
            assert col == "score_general", f"Injection not blocked: {payload}"

    def test_invalid_order_defaults(self):
        """Invalid order values should default to DESC."""
        _, order = _validate_sort("score_general", "INVALID")
        assert order == "DESC"

    def test_sql_injection_in_order(self):
        """SQL injection attempts in order should be sanitized."""
        _, order = _validate_sort("score_general", "desc; DROP TABLE images")
        assert order == "DESC"

    def test_case_insensitive_order(self):
        """Order validation should be case-insensitive."""
        _, order = _validate_sort("score_general", "ASC")
        assert order == "ASC"
        _, order = _validate_sort("score_general", "Desc")
        assert order == "DESC"

    def test_empty_values(self):
        """Empty strings should return safe defaults."""
        col, order = _validate_sort("", "")
        assert col == "score_general"
        assert order == "DESC"

    def test_model_sort_key_allowed(self):
        col, _ = _validate_sort("model:clip_quality_v0", "desc")
        assert col == "model:clip_quality_v0"

    def test_invalid_model_sort_key_rejected(self):
        col, _ = _validate_sort("model:clip;drop", "desc")
        assert col == "score_general"
