"""Unit tests for the PostgreSQL deadlock-retry helper.

These exercise ``run_with_deadlock_retry`` and ``is_deadlock_error`` from
``modules.db_postgres`` without requiring a live database — the helper is a
pure-Python wrapper around the caller's callable.
"""

from __future__ import annotations

import pytest

pytest.importorskip("psycopg2")

from unittest.mock import patch

from psycopg2 import DatabaseError, OperationalError

from modules.db_postgres import is_deadlock_error, run_with_deadlock_retry


# psycopg2's DatabaseError exposes ``pgcode`` as a read-only property that
# reads from the underlying diagnostics — we cannot set it on a real instance.
# Override it with a normal attribute on the subclass so tests can inject one.
class _PgError(DatabaseError):
    pgcode = None  # type: ignore[assignment]

    def __init__(self, msg: str, pgcode: str | None = None) -> None:
        super().__init__(msg)
        type(self).__dict__  # ensure subclass dict is materialised
        object.__setattr__(self, "_pgcode_value", pgcode)

    def __getattribute__(self, name):  # noqa: D401 - test helper
        if name == "pgcode":
            return object.__getattribute__(self, "_pgcode_value")
        return object.__getattribute__(self, name)


def _make_deadlock_error() -> _PgError:
    return _PgError("deadlock detected", pgcode="40P01")


def test_is_deadlock_error_recognises_pgcode_40p01():
    assert is_deadlock_error(_PgError("something", pgcode="40P01")) is True


def test_is_deadlock_error_recognises_message_text():
    assert is_deadlock_error(DatabaseError("deadlock detected\nDETAIL: ...")) is True


def test_is_deadlock_error_rejects_unrelated_db_error():
    assert is_deadlock_error(OperationalError("connection closed")) is False


def test_run_with_deadlock_retry_returns_value_when_no_error():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        return "ok"

    assert run_with_deadlock_retry(fn) == "ok"
    assert calls["n"] == 1


def test_run_with_deadlock_retry_retries_then_succeeds():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _make_deadlock_error()
        return 42

    with patch("time.sleep") as sleeper:
        assert run_with_deadlock_retry(fn, max_attempts=4, op_name="test") == 42
    assert calls["n"] == 3
    assert sleeper.call_count == 2


def test_run_with_deadlock_retry_raises_after_max_attempts():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise _make_deadlock_error()

    with patch("time.sleep"):
        with pytest.raises(DatabaseError):
            run_with_deadlock_retry(fn, max_attempts=3, op_name="test")
    assert calls["n"] == 3


def test_run_with_deadlock_retry_does_not_retry_non_deadlock():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise _PgError("syntax error at or near '?'", pgcode="42601")

    with patch("time.sleep") as sleeper:
        with pytest.raises(DatabaseError):
            run_with_deadlock_retry(fn, max_attempts=4, op_name="test")
    assert calls["n"] == 1
    sleeper.assert_not_called()
