"""Tests for resolve_canonical_file_path_for_lookup (gallery WIN path vs DB WSL path)."""

from unittest.mock import MagicMock, patch

from modules import db_legacy as db


def _connector_with_responses(responses):
    """Map SQL substrings to query_one return values (first match wins)."""
    conn = MagicMock()

    def query_one(sql, params=None):
        sql_norm = " ".join(sql.split())
        for needle, row in responses:
            if needle in sql_norm:
                return row
        return None

    conn.query_one.side_effect = query_one
    return conn


def test_resolve_canonical_exact_images_file_path():
    conn = _connector_with_responses([
        ("FROM images WHERE file_path", {"file_path": "/mnt/d/Photos/a.NEF"}),
    ])
    with patch.object(db, "get_connector", return_value=conn):
        assert db.resolve_canonical_file_path_for_lookup("/mnt/d/Photos/a.NEF") == "/mnt/d/Photos/a.NEF"


def test_resolve_canonical_via_file_paths_win_alias():
    conn = _connector_with_responses([
        ("FROM images WHERE file_path", None),
        ("INNER JOIN file_paths", {"file_path": "/mnt/d/Photos/a.NEF"}),
    ])
    with patch.object(db, "get_connector", return_value=conn):
        assert db.resolve_canonical_file_path_for_lookup("D:/Photos/a.NEF") == "/mnt/d/Photos/a.NEF"


def test_resolve_canonical_wsl_variant_after_win_miss():
    calls = []

    def query_one(sql, params=None):
        calls.append(params)
        sql_norm = " ".join(sql.split())
        if "FROM images WHERE file_path" in sql_norm:
            p = params[0] if params else None
            if p == "/mnt/d/Photos/a.NEF":
                return {"file_path": "/mnt/d/Photos/a.NEF"}
        if "INNER JOIN file_paths" in sql_norm:
            return None
        return None

    conn = MagicMock()
    conn.query_one.side_effect = query_one
    with patch.object(db, "get_connector", return_value=conn):
        assert db.resolve_canonical_file_path_for_lookup("D:\\Photos\\a.NEF") == "/mnt/d/Photos/a.NEF"


def test_resolve_canonical_returns_none_when_unmatched():
    conn = _connector_with_responses([])
    with patch.object(db, "get_connector", return_value=conn):
        assert db.resolve_canonical_file_path_for_lookup("Z:/nowhere/missing.jpg") is None
