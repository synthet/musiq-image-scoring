import sys
import os
import glob
import subprocess
import logging
import pytest

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Default local unit tests to connect to the isolated db-e2e container port
if "POSTGRES_PORT" not in os.environ:
    os.environ["POSTGRES_PORT"] = "5433"

from modules.test_db_constants import (
    POSTGRES_TEST_DB,
    postgres_production_allowed_in_pytest,
)

_log = logging.getLogger(__name__)


@pytest.fixture(autouse=True)
def _isolate_config_cache():
    """Reset the module-global config cache around every test.

    ``modules.config.load_config()`` caches the merged config keyed on file mtime.
    Tests that monkeypatch ``CONFIG_FILE``/``ENVIRONMENT_FILE`` to a tmp_path and
    write fresh files rely on a clean read; on coarse-mtime filesystems (WSL
    /mnt/d) successive tmp writes can share an mtime, so without an explicit
    invalidate a test could read a previous test's cached config. Production is
    unaffected — every ``save_config_*`` already invalidates on write.
    """
    try:
        from modules import config as _cfg

        _cfg.invalidate_config_cache()
    except Exception:
        pass
    yield
    try:
        from modules import config as _cfg

        _cfg.invalidate_config_cache()
    except Exception:
        pass


def _postgres_tests_enabled(_config):
    """Return whether Postgres test setup should be active (explicit opt-in only)."""
    if os.environ.get("SKIP_POSTGRES_TESTS", "").strip().lower() in ("1", "true", "yes"):
        return False
    if os.environ.get("RUN_POSTGRES_TESTS", "").strip().lower() in ("1", "true", "yes"):
        return True
    marker_expr = ""
    if _config is not None:
        try:
            marker_expr = (_config.getoption("-m") or "").strip()
        except Exception:
            marker_expr = ""
    marker_expr = marker_expr.lower()
    if "postgres" not in marker_expr:
        return False
    if "not postgres" in marker_expr:
        return False
    return True


@pytest.fixture(scope="session")
def postgres_test_session(request):
    """
    Isolated PostgreSQL database (image_scoring_test) with full app schema.
    Activation is explicit opt-in via ``RUN_POSTGRES_TESTS=1`` or ``pytest -m postgres``.
    """
    if not _postgres_tests_enabled(request.config):
        pytest.skip(
            "PostgreSQL tests disabled (set RUN_POSTGRES_TESTS=1 or run with -m postgres)"
        )

    try:
        from modules import db_postgres
    except ModuleNotFoundError as e:
        pytest.skip(f"PostgreSQL driver not available: {e}")

    prev_db = os.environ.get("POSTGRES_DB")
    os.environ["POSTGRES_DB"] = POSTGRES_TEST_DB
    db_postgres.reset_pool()
    try:
        try:
            db_postgres.ensure_database_exists(POSTGRES_TEST_DB)
        except Exception as e:
            pytest.skip(f"PostgreSQL unavailable (create DB): {e}")
        db_postgres.reset_pool()
        try:
            db_postgres.init_db()
        except Exception as e:
            pytest.skip(f"PostgreSQL schema init failed: {e}")
        yield POSTGRES_TEST_DB
    finally:
        db_postgres.reset_pool()
        if prev_db is None:
            os.environ.pop("POSTGRES_DB", None)
        else:
            os.environ["POSTGRES_DB"] = prev_db


@pytest.fixture
def clean_postgres(postgres_test_session):
    """Empty all app tables before each test (requires postgres_test_session)."""
    from modules import db_postgres

    db_postgres.truncate_app_tables()
    db_postgres.reset_pool()
    try:
        from modules.db_connector import reset_connector

        reset_connector()
    except Exception:
        pass
    yield


def pytest_sessionstart(session):
    """Ensure the PostgreSQL test catalog exists before running tests.

    Since v6.4 the default engine is ``postgres`` for all environments.
    Firebird test setup (``scripts/setup_test_db.py``) is no longer invoked
    automatically — run it manually if you need a Firebird test database.
    """
    if _postgres_tests_enabled(session.config) and not postgres_production_allowed_in_pytest():
        try:
            from modules import config
        except Exception as e:
            _log.debug("pytest_sessionstart: skip config import: %s", e)
        else:
            engine = config.get_database_engine()
            if engine == "postgres":
                try:
                    from modules import db_postgres
                except ModuleNotFoundError as e:
                    _log.debug("pytest_sessionstart: skip postgres: %s", e)
                else:
                    try:
                        db_postgres.ensure_database_exists(POSTGRES_TEST_DB)
                        print(f"\n[conftest] PostgreSQL test database '{POSTGRES_TEST_DB}' ready.\n")
                    except Exception as e:
                        _log.warning(
                            "pytest_sessionstart: could not ensure database %s exists: %s "
                            "(Postgres may not be running)",
                            POSTGRES_TEST_DB,
                            e,
                        )
            elif engine == "firebird":
                # Legacy: manual Firebird setup still supported via env override
                script_path = os.path.join(project_root, "scripts", "setup_test_db.py")
                if os.path.exists(script_path):
                    print("\n[conftest] Firebird engine detected — running setup_test_db.py...")
                    try:
                        subprocess.run([sys.executable, script_path], check=True, cwd=project_root)
                    except Exception as e:
                        print(f"[conftest] WARNING: Firebird test DB setup failed: {e}")
                        print("Tests may fail for Firebird-dependent tests.")


def pytest_sessionfinish(session, exitstatus):
    """Best-effort removal of orphan Firebird test DBs and migration *.bak sidecars at repo root.

    .. deprecated:: 6.4
       Firebird test DB cleanup will be removed in v7.0 when Firebird support is dropped.
    """
    patterns = (
        os.path.join(project_root, "TEST_*.fdb"),
        os.path.join(project_root, "TEST_*.fdb.*"),
    )
    for pattern in patterns:
        for path in glob.glob(pattern):
            try:
                if os.path.isfile(path):
                    os.remove(path)
            except OSError:
                pass
