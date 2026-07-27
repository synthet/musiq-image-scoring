"""
ApiConnector — IConnector implementation that proxies SQL to a remote backend.

Sends all queries to ``POST /api/db/query`` on the configured backend URL.
This allows a remote process (e.g. the scoring worker, Electron app) to
execute database operations without a direct database driver connection.

Endpoint contract (served by ``modules/api_db.py``):

    POST /api/db/query
        Body:  { "sql": str, "params": list, "write": bool }
        Response: { "rows": list[dict], "rowcount": int }

    POST /api/db/transaction
        Body:  { "statements": [{"sql": str, "params": list}] }
        Response: { "ok": true }

    GET /api/db/ping
        Response: { "ok": true, "engine": "firebird" | "postgres" }

Write paths (``execute``, ``execute_returning``, ``execute_many``, ``run_transaction`` batch)
send ``X-DB-Write-Token`` when ``database.query_token`` is set in config (same as
``modules/api_db.py``).

Note on transactions:
    ``run_transaction`` sends a batch of write statements atomically via
    ``POST /api/db/transaction``.  Read operations inside a remote transaction
    callback execute as normal ``/api/db/query`` calls (no server-side session
    state), so the atomicity guarantee applies only to write statements.
    For full transactional semantics, run the server-side connector directly.
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _read_query_token_from_config() -> str:
    try:
        from modules import config as _cfg

        return str(
            (_cfg.get_config_section("database") or {}).get("query_token", "") or ""
        ).strip()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Transaction context
# ---------------------------------------------------------------------------

class _ApiTx:
    """Transaction context for ApiConnector.run_transaction callbacks.

    Read operations are forwarded immediately via the connector.
    Write operations are collected and sent as an atomic batch to
    ``POST /api/db/transaction`` after the callback returns.
    """

    def __init__(self, connector: ApiConnector) -> None:
        self._c = connector
        self._writes: list[dict] = []

    def query(self, sql: str, params: Sequence | None = None) -> list[dict]:
        # Reads are forwarded immediately (non-transactional for remote connector).
        return self._c.query(sql, params)

    def query_one(self, sql: str, params: Sequence | None = None) -> dict | None:
        return self._c.query_one(sql, params)

    def execute(self, sql: str, params: Sequence | None = None) -> int:
        self._writes.append({"sql": sql, "params": list(params or [])})
        return 0  # rowcount unknown until batch is committed

    def execute_returning(self, sql: str, params: Sequence | None = None) -> list[dict]:
        self._writes.append({"sql": sql, "params": list(params or []), "returning": True})
        return []  # actual rows returned when batch commits


# ---------------------------------------------------------------------------
# Connector
# ---------------------------------------------------------------------------

class ApiConnector:
    """Connector that proxies SQL to a remote ``/api/db/query`` endpoint."""

    type = 'api'

    def __init__(
        self,
        base_url: str = "http://localhost:7860",
        write_token: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip('/')
        self._session: Any = None
        if write_token is not None:
            self._write_token = str(write_token).strip()
        else:
            self._write_token = _read_query_token_from_config()

    @property
    def _s(self):
        if self._session is None:
            import requests
            self._session = requests.Session()
        return self._session

    def _post(
        self,
        path: str,
        payload: dict,
        timeout: float = 30.0,
        *,
        send_write_token: bool = False,
    ) -> dict:
        url = f"{self._base_url}{path}"
        if send_write_token and self._write_token:
            resp = self._s.post(
                url,
                json=payload,
                headers={"X-DB-Write-Token": self._write_token},
                timeout=timeout,
            )
        else:
            resp = self._s.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # IConnector
    # ------------------------------------------------------------------

    def query(self, sql: str, params: Sequence | None = None) -> list[dict]:
        data = self._post(
            "/api/db/query",
            {"sql": sql, "params": list(params or []), "write": False},
        )
        return data.get("rows", [])

    def query_one(self, sql: str, params: Sequence | None = None) -> dict | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def execute(self, sql: str, params: Sequence | None = None) -> int:
        data = self._post(
            "/api/db/query",
            {"sql": sql, "params": list(params or []), "write": True},
            send_write_token=True,
        )
        return int(data.get("rowcount", 0))

    def execute_returning(self, sql: str, params: Sequence | None = None) -> list[dict]:
        data = self._post(
            "/api/db/query",
            {"sql": sql, "params": list(params or []), "write": True},
            send_write_token=True,
        )
        return data.get("rows", [])

    def execute_many(self, sql: str, params_list: list[Sequence]) -> None:
        self._post(
            "/api/db/query",
            {
                "sql": sql,
                "params": [list(p) for p in params_list],
                "executemany": True,
                "write": True,
            },
            timeout=120.0,
            send_write_token=True,
        )

    def run_transaction(self, callback: Callable[[_ApiTx], T]) -> T:
        """Collect write statements, then send as an atomic batch."""
        tx = _ApiTx(self)
        result = callback(tx)
        if tx._writes:
            self._post(
                "/api/db/transaction",
                {"statements": tx._writes},
                timeout=60.0,
                send_write_token=True,
            )
        return result

    def check_connection(self) -> bool:
        try:
            resp = self._s.get(f"{self._base_url}/api/db/ping", timeout=5.0)
            return resp.status_code == 200
        except Exception as e:
            logger.warning("ApiConnector ping failed (%s): %s", self._base_url, e)
            return False

    def verify_startup(self) -> bool:
        return self.check_connection()

    def close(self) -> None:
        if self._session is not None:
            try:
                self._session.close()
            except Exception:
                pass
            self._session = None
