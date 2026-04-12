from unittest.mock import MagicMock
from types import SimpleNamespace

from modules import config
from modules import db


def _mock_config(engine="firebird", dual_write=False):
    return {
        "engine": engine,
        "dual_write": dual_write,
    }


def test_get_database_engine_explicit(monkeypatch):
    monkeypatch.setenv("IMAGE_SCORING_DB_ENGINE_DEFAULT", "postgres")
    monkeypatch.setattr(
        config,
        "get_config_section",
        lambda section: {"engine": "POSTGRES"} if section == "database" else {},
    )
    assert config.get_database_engine() == "postgres"


def test_get_database_engine_omitted_defaults_postgres(monkeypatch):
    monkeypatch.delenv("IMAGE_SCORING_DB_ENGINE_DEFAULT", raising=False)
    monkeypatch.setattr(
        config,
        "get_config_section",
        lambda section: {} if section == "database" else {},
    )
    assert config.get_database_engine() == "postgres"


def test_get_db_firebird_default_engine(monkeypatch):
    """get_db() returns FirebirdConnectionProxy when engine=firebird."""
    fake_fb_conn = MagicMock()
    monkeypatch.setattr(
        db.config,
        "get_config_section",
        lambda name: _mock_config(engine="firebird", dual_write=False),
    )
    monkeypatch.setattr(db, "connect", lambda *args, **kwargs: fake_fb_conn)
    monkeypatch.setattr(db, "DB_PATH", "dummy.fdb")
    monkeypatch.setattr(db, "DEBUG_DB_CONNECTION", False)
    monkeypatch.setenv("FIREBIRD_USE_LOCAL_PATH", "1")

    conn = db.get_db()

    assert isinstance(conn, db.FirebirdConnectionProxy)


def test_get_db_postgres_primary_and_qmark_rows(monkeypatch):
    """get_db() returns PostgresConnectionProxy when engine=postgres,
    and the cursor proxy translates ? placeholders to %s."""
    class _Desc:
        def __init__(self, name):
            self.name = name

    class FakePGCursor:
        def __init__(self):
            self.executed = []
            self.description = [_Desc("id"), _Desc("file_name")]

        def execute(self, query, params=None):
            self.executed.append((query, params))

        def fetchone(self):
            return (7, "img.jpg")

        def fetchall(self):
            return []

    class FakePGConn:
        def __init__(self):
            self.cur = FakePGCursor()

        def cursor(self):
            return self.cur

        def commit(self):
            pass

        def rollback(self):
            pass

    fake_pg_conn = FakePGConn()
    release_calls = []

    monkeypatch.setenv("IMAGE_SCORING_DB_ENGINE_DEFAULT", "postgres")
    monkeypatch.setattr(
        db.config,
        "get_config_section",
        lambda name: _mock_config(engine="postgres", dual_write=True),
    )
    fake_pg_mod = SimpleNamespace(
        get_pg_connection=lambda: fake_pg_conn,
        release_pg_connection=lambda conn: release_calls.append(conn),
    )
    monkeypatch.setattr(db, "db_postgres", fake_pg_mod)

    conn = db.get_db()
    assert isinstance(conn, db.PostgresConnectionProxy)

    cur = conn.cursor()
    cur.execute("SELECT id, file_name FROM images WHERE id = ?", (7,))
    row = cur.fetchone()

    assert fake_pg_conn.cur.executed[0][0].count("%s") == 1
    assert "?" not in fake_pg_conn.cur.executed[0][0]
    assert row["id"] == 7
    assert row["file_name"] == "img.jpg"
    conn.close()
    assert release_calls == [fake_pg_conn]


def test_postgres_proxy_translates_firebird_sql(monkeypatch):
    """PostgresCursorProxy applies full Firebird→PG translation
    (upsert, SELECT FIRST, DATEDIFF, etc.), not just ? → %s."""
    class _Desc:
        def __init__(self, name):
            self.name = name

    class FakePGCursor:
        def __init__(self):
            self.executed = []
            self.description = [_Desc("id")]

        def execute(self, query, params=None):
            self.executed.append((query, params))

        def fetchall(self):
            return []

    fake_cur = FakePGCursor()
    proxy = db.PostgresCursorProxy(fake_cur)

    proxy.execute("SELECT FIRST 10 id FROM images WHERE score > ?", (0.5,))
    translated = fake_cur.executed[0][0]

    assert "FIRST" not in translated
    assert "LIMIT 10" in translated
    assert "%s" in translated
    assert "?" not in translated


def test_dual_write_removed_reports_disabled():
    """Firebird→Postgres dual-write queue was removed; stats stub stays off."""
    stats = db.get_dual_write_stats()
    assert stats["enabled"] is False
    assert stats["queue_depth"] == 0
    assert stats["queued"] == 0


# ---- _translate_fb_to_pg() unit tests ----

def test_translate_rand_to_random():
    """RAND() → RANDOM()"""
    sql = "SELECT * FROM images ORDER BY RAND() FETCH FIRST 10 ROWS ONLY"
    result = db._translate_fb_to_pg(sql)
    assert "RANDOM()" in result
    assert "RAND()" not in result
    assert "LIMIT 10" in result


def test_translate_list_to_string_agg():
    """LIST(expr, sep) → STRING_AGG(expr, sep)"""
    sql = "SELECT LIST(kd.keyword_display, ', ') FROM image_keywords ik"
    result = db._translate_fb_to_pg(sql)
    assert "STRING_AGG(" in result
    assert "LIST(" not in result


def test_translate_fetch_first_param():
    """FETCH FIRST ? ROWS ONLY → LIMIT %s"""
    sql = "SELECT * FROM jobs ORDER BY id FETCH FIRST ? ROWS ONLY"
    result = db._translate_fb_to_pg(sql)
    assert "LIMIT %s" in result
    assert "FETCH" not in result


def test_translate_select_first_n():
    """SELECT FIRST n → SELECT ... LIMIT n"""
    sql = "SELECT FIRST 5 id FROM images"
    result = db._translate_fb_to_pg(sql)
    assert "FIRST" not in result
    assert "LIMIT 5" in result


def test_translate_datediff():
    """DATEDIFF(SECOND FROM a TO b) → EXTRACT(EPOCH FROM (b - a))::INTEGER"""
    sql = "SELECT DATEDIFF(SECOND FROM started_at TO finished_at) FROM jobs"
    result = db._translate_fb_to_pg(sql)
    assert "EXTRACT(EPOCH FROM (finished_at - started_at))::INTEGER" in result
    assert "DATEDIFF" not in result


def test_translate_placeholder_in_string_literal():
    """? inside string literals should NOT be translated to %s."""
    sql = "SELECT * FROM images WHERE label = '?' AND id = ?"
    result = db._translate_fb_to_pg(sql)
    assert result == "SELECT * FROM images WHERE label = '?' AND id = %s"


def test_translate_upsert():
    """UPDATE OR INSERT → INSERT ... ON CONFLICT ... DO UPDATE SET"""
    sql = "UPDATE OR INSERT INTO cluster_progress (folder_path, last_run) VALUES (?, ?) MATCHING (folder_path)"
    result = db._translate_fb_to_pg(sql)
    assert "INSERT INTO cluster_progress" in result
    assert "ON CONFLICT (folder_path) DO UPDATE SET" in result
    assert "last_run = EXCLUDED.last_run" in result
