"""Unit tests for verify_embedding_column_parity helpers."""

from unittest.mock import patch

import scripts.maintenance.verify_embedding_column_parity as vep


def test_run_audit_when_column_dropped():
    with patch.object(vep, "_column_exists", return_value=False):
        with patch("modules.db_postgres.execute_select_one", return_value={"c": 5}):
            report = vep.run_audit()
    assert report["legacy_column_dropped"] is True
    assert report["column_only"] == 0


def test_run_backfill_skips_when_column_dropped():
    with patch.object(vep, "_column_exists", return_value=False):
        assert vep.run_backfill() == 0
