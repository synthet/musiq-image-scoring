"""
DbConnector factory — returns the appropriate IConnector implementation.

Reads ``database.engine`` from config.json (see :func:`modules.config.get_database_engine`):
    ``"postgres"``  (default) → PostgresConnector
    ``"api"``       → ApiConnector       (HTTP proxy)
    ``"firebird"``  → DEPRECATED, maps to PostgresConnector with a warning

Config keys used:
    database.engine       — "postgres" | "api" (legacy "firebird" accepted)
    database.api_url      — base URL for ApiConnector (default: http://localhost:7860)
    database.query_token  — sent as X-DB-Write-Token on ApiConnector mutating requests

The factory caches a singleton so all callers share one instance.
Use ``reset_connector()`` for tests or after a config change.
"""
from __future__ import annotations

import logging
import threading
from typing import Union

logger = logging.getLogger(__name__)

# Type alias (avoid importing concrete classes at module level to allow
# lazy imports inside the factory function)
_ConnectorType = Union["PostgresConnector", "ApiConnector"]  # noqa: F821  # type: ignore[name-defined]

_instance: _ConnectorType | None = None
_lock = threading.Lock()


def get_connector():
    """Return (or create) the singleton IConnector for this process.

    Thread-safe via double-checked locking.  Reads ``database.engine`` from
    config.json on first call; subsequent calls return the cached instance.
    """
    global _instance
    if _instance is not None:
        return _instance

    with _lock:
        # Double-checked locking
        if _instance is not None:
            return _instance

        try:
            from modules import config
            engine = config.get_database_engine()
        except Exception:
            engine = "postgres"

        if engine == "postgres":
            from modules.db_connector.postgres import PostgresConnector
            logger.info("DbConnector: using PostgresConnector")
            _instance = PostgresConnector()

        elif engine == "api":
            try:
                from modules import config as _cfg
                db_cfg = _cfg.get_config_section("database") or {}
                api_url = str(db_cfg.get("api_url", "http://localhost:7860")).strip()
                write_token = str(db_cfg.get("query_token", "") or "").strip()
            except Exception:
                api_url = "http://localhost:7860"
                write_token = ""
            from modules.db_connector.api import ApiConnector
            logger.info("DbConnector: using ApiConnector → %s", api_url)
            _instance = ApiConnector(base_url=api_url, write_token=write_token)

        elif engine == "firebird":
            # Legacy: Firebird has been decommissioned (2026-03).
            # Map to PostgresConnector for backward compatibility with old configs.
            logger.warning(
                "database.engine='firebird' is deprecated; mapping to PostgresConnector. "
                "Update config.json to set engine='postgres'."
            )
            from modules.db_connector.postgres import PostgresConnector
            _instance = PostgresConnector()

        else:
            logger.warning(
                "Unknown database.engine=%r; falling back to 'postgres'", engine
            )
            from modules.db_connector.postgres import PostgresConnector
            _instance = PostgresConnector()

        return _instance


def reset_connector() -> None:
    """Reset the cached connector instance (for tests or config reload).

    Calls ``close()`` on the existing instance before clearing it.
    """
    global _instance
    with _lock:
        if _instance is not None:
            try:
                _instance.close()
            except Exception:
                pass
        _instance = None
