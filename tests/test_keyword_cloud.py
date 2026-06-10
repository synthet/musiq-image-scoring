"""Unit tests for keyword tag-cloud helpers and the exact keyword filter.

No DB / hardware required — uses a fake connector to capture emitted SQL.
"""

import modules.keyword_discovery as kd
from modules.db_legacy import _add_keyword_filter


# ---------------------------------------------------------------------------
# _add_keyword_filter — substring vs exact
# ---------------------------------------------------------------------------

def test_add_keyword_filter_substring_default():
    conditions, params = [], []
    _add_keyword_filter(conditions, params, "Bird")
    assert len(conditions) == 1
    assert "kd.keyword_norm LIKE ?" in conditions[0]
    assert params == ["%bird%"]


def test_add_keyword_filter_exact():
    conditions, params = [], []
    _add_keyword_filter(conditions, params, "species:American Robin", exact=True)
    assert len(conditions) == 1
    assert "kd.keyword_norm = ?" in conditions[0]
    assert "LIKE" not in conditions[0]
    assert params == ["species:american robin"]


def test_add_keyword_filter_skips_blank():
    conditions, params = [], []
    _add_keyword_filter(conditions, params, "   ")
    assert conditions == []
    assert params == []


# ---------------------------------------------------------------------------
# get_keyword_cloud — species vs general predicate selection
# ---------------------------------------------------------------------------

class _FakeConn:
    def __init__(self, conn_type="postgres"):
        self.type = conn_type
        self.captured_sql = None
        self.captured_params = None

    def query(self, sql, params):
        self.captured_sql = sql
        self.captured_params = params
        return [
            {"keyword_norm": "species:american robin",
             "keyword_display": "species:American Robin", "count": 5},
        ]


def _patch_conn(monkeypatch, conn):
    monkeypatch.setattr(kd, "get_connector", lambda: conn)


def test_keyword_cloud_species_uses_like_prefix(monkeypatch):
    conn = _FakeConn("postgres")
    _patch_conn(monkeypatch, conn)
    rows = kd.get_keyword_cloud(kind="species", limit=10)
    assert "kd.keyword_norm LIKE %s" in conn.captured_sql
    assert "NOT LIKE" not in conn.captured_sql
    assert conn.captured_params[0] == "species:%"
    assert rows and rows[0]["count"] == 5


def test_keyword_cloud_general_excludes_species(monkeypatch):
    conn = _FakeConn("postgres")
    _patch_conn(monkeypatch, conn)
    kd.get_keyword_cloud(kind="general", limit=10)
    assert "kd.keyword_norm NOT LIKE %s" in conn.captured_sql
    assert conn.captured_params[0] == "species:%"


def test_keyword_cloud_firebird_uses_question_placeholder(monkeypatch):
    conn = _FakeConn("firebird")
    _patch_conn(monkeypatch, conn)
    kd.get_keyword_cloud(kind="species", limit=10)
    assert "LIKE ?" in conn.captured_sql
    assert "ROWS 1 TO ?" in conn.captured_sql


def test_keyword_cloud_returns_empty_on_error(monkeypatch):
    class _Boom:
        type = "postgres"

        def query(self, *a, **k):
            raise RuntimeError("db down")

    _patch_conn(monkeypatch, _Boom())
    assert kd.get_keyword_cloud(kind="general") == []
