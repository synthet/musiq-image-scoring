"""Tests for validate_readonly_sql_for_api and validate_write_sql_for_api (issues #209, #210, #211)."""
import pytest
from modules.db import validate_readonly_sql_for_api, validate_write_sql_for_api


class TestReadonlyValidator:
    """validate_readonly_sql_for_api — issue #209 and #216."""

    def test_plain_select_allowed(self):
        assert validate_readonly_sql_for_api("SELECT id FROM images") is None

    def test_cte_select_allowed(self):
        assert validate_readonly_sql_for_api("WITH t AS (SELECT 1) SELECT * FROM t") is None

    def test_empty_blocked(self):
        assert validate_readonly_sql_for_api("") is not None
        assert validate_readonly_sql_for_api("   ") is not None

    def test_non_select_blocked(self):
        assert validate_readonly_sql_for_api("UPDATE images SET score=0") is not None
        assert validate_readonly_sql_for_api("INSERT INTO images VALUES (1)") is not None

    def test_semicolon_blocked(self):
        assert validate_readonly_sql_for_api("SELECT 1; DROP TABLE images") is not None

    def test_comment_blocked(self):
        assert validate_readonly_sql_for_api("SELECT 1 -- comment") is not None
        assert validate_readonly_sql_for_api("SELECT /* comment */ 1") is not None

    # issue #209: file-exfiltration functions must be blocked
    @pytest.mark.parametrize("fn", [
        "pg_read_file",
        "pg_read_binary_file",
        "pg_ls_dir",
        "pg_stat_file",
        "lo_export",
        "lo_import",
        "dblink",
        "pg_execute_server_program",
    ])
    def test_pg_file_functions_blocked(self, fn):
        assert validate_readonly_sql_for_api(f"SELECT {fn}('/etc/passwd')") is not None

    def test_pg_read_file_via_cte_blocked(self):
        # The CTE wrapper must not bypass the deny-list
        sql = "WITH s AS (SELECT pg_read_file('/etc/passwd')) SELECT * FROM s"
        assert validate_readonly_sql_for_api(sql) is not None

    def test_dblink_via_cte_blocked(self):
        sql = "WITH d AS (SELECT dblink('host=evil','SELECT 1')) SELECT * FROM d"
        assert validate_readonly_sql_for_api(sql) is not None

    def test_pg_file_case_insensitive(self):
        assert validate_readonly_sql_for_api("SELECT PG_READ_FILE('/tmp/x')") is not None
        assert validate_readonly_sql_for_api("SELECT Pg_Read_File('/tmp/x')") is not None


class TestWriteValidator:
    """validate_write_sql_for_api — issue #211."""

    def test_insert_allowed(self):
        assert validate_write_sql_for_api("INSERT INTO images (file_path) VALUES ('/a')") is None

    def test_update_allowed(self):
        assert validate_write_sql_for_api("UPDATE images SET rating=3 WHERE id=1") is None

    def test_delete_allowed(self):
        assert validate_write_sql_for_api("DELETE FROM images WHERE id=1") is None

    def test_empty_blocked(self):
        assert validate_write_sql_for_api("") is not None

    def test_select_blocked(self):
        assert validate_write_sql_for_api("SELECT 1") is not None

    def test_ddl_blocked(self):
        assert validate_write_sql_for_api("DROP TABLE images") is not None
        assert validate_write_sql_for_api("ALTER TABLE images ADD COLUMN x INT") is not None
        assert validate_write_sql_for_api("CREATE TABLE evil (id INT)") is not None
        assert validate_write_sql_for_api("TRUNCATE images") is not None

    # issue #211: bare ";" must be blocked (previously only ";--" was blocked)
    def test_multi_statement_blocked(self):
        assert validate_write_sql_for_api("UPDATE images SET score=0; DROP TABLE stacks") is not None

    def test_bare_semicolon_blocked(self):
        assert validate_write_sql_for_api("UPDATE images SET score=0;") is not None

    def test_line_comment_blocked(self):
        assert validate_write_sql_for_api("UPDATE images SET score=0 -- comment") is not None

    def test_block_comment_blocked(self):
        assert validate_write_sql_for_api("UPDATE images SET score=0 /* comment */") is not None


class TestTransactionEndpoint:
    """POST /api/db/transaction must validate each statement — issue #210."""

    def _client(self):
        fastapi = pytest.importorskip("fastapi")
        pytest.importorskip("fastapi.testclient")
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from modules import api_db

        app = FastAPI()
        app.include_router(api_db.router)
        return TestClient(app)

    def _cfg_patch(self):
        from unittest.mock import patch

        return patch(
            "modules.api_db._cfg" if False else "modules.config.get_config_section",
            return_value={"query_token": "test-token"},
        )

    def test_ddl_statement_rejected(self):
        from unittest.mock import patch

        client = self._client()
        with patch("modules.config.get_config_section", return_value={"query_token": "tok"}):
            resp = client.post(
                "/api/db/transaction",
                headers={"X-DB-Write-Token": "tok"},
                json={"statements": [{"sql": "DROP TABLE images", "params": []}]},
            )
        # Should be rejected before hitting the DB
        assert resp.status_code in (400, 500)

    def test_valid_statements_pass_validation(self):
        from unittest.mock import patch, MagicMock

        client = self._client()
        mock_connector = MagicMock()
        mock_connector.run_transaction.side_effect = lambda fn: fn(MagicMock())

        with patch("modules.config.get_config_section", return_value={"query_token": "tok"}):
            with patch("modules.api_db.db.validate_write_sql_for_api", return_value=None) as mock_val:
                with patch("modules.db_connector.get_connector", return_value=mock_connector):
                    resp = client.post(
                        "/api/db/transaction",
                        headers={"X-DB-Write-Token": "tok"},
                        json={"statements": [{"sql": "UPDATE images SET rating=3 WHERE id=1", "params": []}]},
                    )
        mock_val.assert_called()
