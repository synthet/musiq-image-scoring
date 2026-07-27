"""
IConnector — transport-layer protocol for database access.

This is a typing.Protocol (structural subtyping) so implementations do not
need to inherit from it; they just need matching method signatures.

The interface mirrors the gallery project's IDatabaseConnector, adapted for
synchronous Python:

    query()             → SELECT; returns list[dict]
    query_one()         → SELECT; returns first row or None
    execute()           → INSERT/UPDATE/DELETE; returns rowcount
    execute_returning() → INSERT/UPDATE/DELETE … RETURNING; returns list[dict]
    execute_many()      → batch INSERT/UPDATE/DELETE
    run_transaction()   → atomic multi-statement block
    check_connection()  → connectivity probe
    verify_startup()    → startup/readiness probe
    close()             → release resources

SQL dialect:
    Callers write SQL with Firebird ``?`` placeholders and Firebird syntax.
    Each connector implementation is responsible for dialect translation when
    targeting a different engine (e.g. ``PostgresConnector`` translates via
    ``_translate_fb_to_pg``).

Transaction context:
    ``run_transaction`` passes an ``ITransaction`` to the callback.
    ``ITransaction`` exposes the same query/execute surface but shares a
    single open connection/transaction, committing only when the callback
    returns normally.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import (
    Literal,
    Protocol,
    TypeVar,
    runtime_checkable,
)

T = TypeVar("T")


@runtime_checkable
class ITransaction(Protocol):
    """Query context passed to ``run_transaction`` callbacks.

    All operations share a single open transaction; the connector commits
    (or rolls back on exception) after the callback returns.
    """

    def query(self, sql: str, params: Sequence | None = None) -> list[dict]: ...
    def query_one(self, sql: str, params: Sequence | None = None) -> dict | None: ...
    def execute(self, sql: str, params: Sequence | None = None) -> int: ...
    def execute_returning(self, sql: str, params: Sequence | None = None) -> list[dict]: ...


@runtime_checkable
class IConnector(Protocol):
    """Structural protocol for database connector implementations.

    Implementations: FirebirdConnector, PostgresConnector, ApiConnector.
    """

    type: Literal['firebird', 'postgres', 'api']

    def query(self, sql: str, params: Sequence | None = None) -> list[dict]:
        """Execute a SELECT and return all rows as list[dict]."""
        ...

    def query_one(self, sql: str, params: Sequence | None = None) -> dict | None:
        """Execute a SELECT and return the first row as dict, or None."""
        ...

    def execute(self, sql: str, params: Sequence | None = None) -> int:
        """Execute INSERT/UPDATE/DELETE and return rowcount. Commits on success."""
        ...

    def execute_returning(self, sql: str, params: Sequence | None = None) -> list[dict]:
        """Execute INSERT/UPDATE/DELETE … RETURNING and return result rows. Commits."""
        ...

    def execute_many(self, sql: str, params_list: list[Sequence]) -> None:
        """Execute a statement for each parameter row. Commits on success."""
        ...

    def run_transaction(self, callback: Callable[[ITransaction], T]) -> T:
        """Run ``callback`` inside a single transaction.

        The callback receives an ITransaction context. The connector commits
        after a normal return, or rolls back on any exception (which is
        re-raised to the caller).
        """
        ...

    def check_connection(self) -> bool:
        """Return True if the database is reachable."""
        ...

    def verify_startup(self) -> bool:
        """Return True if the backend is fully ready (same as check_connection
        for direct connectors; may do additional checks for ApiConnector)."""
        ...

    def close(self) -> None:
        """Release any held resources (pool connections, HTTP sessions, etc.)."""
        ...
