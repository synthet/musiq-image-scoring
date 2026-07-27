"""
Persistent audit log for critical DB mutations.

Writes RFC 6902 (JSON Patch) style change records to the ``auditlog`` table so
score / cull / rating / job-lifecycle changes can be reconstructed when
debugging: *who* (``thread_name`` / ``source``), in *what run* (``run_id``),
during *which phase* (``phase_code``) changed *what* (``table_name`` /
``record_id``) and *how* (``patch`` — a list of ``{op, path, value}`` ops, plus a
non-standard ``oldValue`` on ``replace`` / ``remove`` so the prior state is
recoverable).

Design rules:

* **Never throws.** A failure to audit must never break the underlying DB
  write — every public entry point swallows and debug-logs its own errors.
* **Gated** by config ``database.audit_log_enabled`` (default ``True``) and an
  optional per-table allowlist ``database.audit_log_tables`` (empty ⇒ all).
* **Postgres-only persistence.** The ``patch`` column is ``JSONB`` and is written
  with a ``?::jsonb`` cast, so on non-Postgres engines this module is a no-op
  (the table only exists in the Postgres schema / Alembic migration ``0027``).
* **Ambient context** (``run_id``, ``phase_code``, ``source``) flows via a
  :class:`contextvars.ContextVar` set by :func:`audit_context`; ``thread_name``
  is captured automatically from the calling thread. Note that ``contextvars``
  do **not** propagate into worker threads that a runner spawns, so callers that
  hand work to a thread should set ``run_id`` explicitly or re-enter
  :func:`audit_context` inside that thread.
"""
from __future__ import annotations

import contextvars
import datetime
import json
import logging
import threading
from collections.abc import Iterable, Mapping, Sequence
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)

# RFC 6902 operations we emit.
OP_ADD = "add"
OP_REPLACE = "replace"
OP_REMOVE = "remove"

# Sentinel: a key absent from the "before" snapshot (so we emit ``add`` not ``replace``).
_MISSING = object()

_audit_ctx: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "audit_ctx", default=None
)


# ---------------------------------------------------------------------------
# Ambient context
# ---------------------------------------------------------------------------
@contextmanager
def audit_context(
    *,
    run_id: Any = None,
    phase_code: Any = None,
    source: str | None = None,
):
    """Bind ambient audit attributes for the duration of the ``with`` block.

    Values merge over any enclosing context; ``None`` arguments leave the
    inherited value untouched. Restored on exit even if the body raises.
    """
    prev = _audit_ctx.get() or {}
    merged = dict(prev)
    if run_id is not None:
        merged["run_id"] = run_id
    if phase_code is not None:
        merged["phase_code"] = _coerce_phase(phase_code)
    if source is not None:
        merged["source"] = source
    token = _audit_ctx.set(merged)
    try:
        yield
    finally:
        _audit_ctx.reset(token)


def current_audit_context() -> dict:
    """Return a copy of the ambient audit context (never ``None``)."""
    return dict(_audit_ctx.get() or {})


# ---------------------------------------------------------------------------
# Config gating
# ---------------------------------------------------------------------------
def _enabled() -> bool:
    try:
        from modules.config import get_config_value

        return bool(get_config_value("database.audit_log_enabled", default=True))
    except Exception:
        return True


def _table_allowed(table_name: str) -> bool:
    try:
        from modules.config import get_config_value

        allow = get_config_value("database.audit_log_tables", default=None)
    except Exception:
        allow = None
    if not allow:
        return True
    try:
        return str(table_name) in {str(t) for t in allow}
    except TypeError:
        return True


def is_enabled(table_name: str) -> bool:
    """True when auditing should run for ``table_name``.

    Cheap pre-check so callers can skip the extra "before" SELECT that building
    an update patch requires when auditing is off.
    """
    if not _enabled() or not _table_allowed(table_name):
        return False
    return _is_postgres()


def _is_postgres() -> bool:
    try:
        from modules import db as _db

        return _db._get_db_engine() == "postgres"
    except Exception:
        return False


def _connector():
    """Lazy connector accessor (kept indirect so tests can patch it)."""
    from modules.db import get_connector

    return get_connector()


# ---------------------------------------------------------------------------
# Value / path helpers (RFC 6901 pointer escaping + JSON-safe coercion)
# ---------------------------------------------------------------------------
def _escape_token(token: str) -> str:
    """Escape a single JSON Pointer reference token (RFC 6901 §3)."""
    return str(token).replace("~", "~0").replace("/", "~1")


def _path(field: str) -> str:
    return "/" + _escape_token(field)


def _coerce_phase(phase_code: Any) -> str | None:
    if phase_code is None:
        return None
    # Tolerate PhaseCode enums (``.value``) and plain strings.
    val = getattr(phase_code, "value", phase_code)
    return str(val)


def _jsonable(value: Any) -> Any:
    """Best-effort coercion of a column value to a JSON-serializable form."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


def _values_equal(old: Any, new: Any) -> bool:
    if old is new:
        return True
    return _jsonable(old) == _jsonable(new)


# ---------------------------------------------------------------------------
# Patch builders
# ---------------------------------------------------------------------------
def build_insert_patch(
    fields: Mapping[str, Any], *, include_none: bool = False
) -> list:
    """RFC 6902 patch for a freshly inserted row: one ``add`` op per field."""
    patch: list = []
    for key, val in fields.items():
        if val is None and not include_none:
            continue
        patch.append({"op": OP_ADD, "path": _path(key), "value": _jsonable(val)})
    return patch


def build_update_patch(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any],
    *,
    include_old: bool = True,
) -> list:
    """RFC 6902 patch for an update: ``replace`` ops for changed keys only.

    ``add`` is used when the key was absent from ``before``. When
    ``include_old`` is set, a non-standard ``oldValue`` is attached to
    ``replace`` ops to retain the prior state for debugging (extra keys are
    ignored by spec-compliant patch appliers).
    """
    before = before or {}
    patch: list = []
    for key, new_val in after.items():
        old_val = before.get(key, _MISSING)
        if old_val is _MISSING:
            patch.append({"op": OP_ADD, "path": _path(key), "value": _jsonable(new_val)})
            continue
        if _values_equal(old_val, new_val):
            continue
        op = {"op": OP_REPLACE, "path": _path(key), "value": _jsonable(new_val)}
        if include_old:
            op["oldValue"] = _jsonable(old_val)
        patch.append(op)
    return patch


def build_field_update_patch(
    field: str, old_value: Any, new_value: Any, *, include_old: bool = True
) -> list:
    """Convenience: an update patch for a single column."""
    if _values_equal(old_value, new_value):
        return []
    op = {"op": OP_REPLACE, "path": _path(field), "value": _jsonable(new_value)}
    if include_old:
        op["oldValue"] = _jsonable(old_value)
    return [op]


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------
_INSERT_SQL = (
    "INSERT INTO auditlog "
    "(table_name, record_id, operation, patch, thread_name, run_id, phase_code, source, created_at) "
    "VALUES (?, ?, ?, ?::jsonb, ?, ?, ?, ?, ?)"
)


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _resolve_params(
    table_name: str,
    record_id: Any,
    operation: str,
    patch: Sequence,
    run_id: Any,
    phase_code: Any,
    source: str | None,
) -> tuple:
    ctx = current_audit_context()
    eff_run = run_id if run_id is not None else ctx.get("run_id")
    eff_phase = _coerce_phase(phase_code) if phase_code is not None else ctx.get("phase_code")
    eff_source = source if source is not None else ctx.get("source")
    thread_name = threading.current_thread().name
    return (
        str(table_name)[:64],
        _coerce_int(record_id),
        str(operation)[:16],
        json.dumps(list(patch), default=str),
        (str(thread_name)[:128] if thread_name else None),
        _coerce_int(eff_run),
        (str(eff_phase)[:50] if eff_phase else None),
        (str(eff_source)[:128] if eff_source else None),
        datetime.datetime.now(),
    )


def record_audit(
    table_name: str,
    record_id: Any,
    operation: str,
    patch: Sequence,
    *,
    run_id: Any = None,
    phase_code: Any = None,
    source: str | None = None,
    tx: Any = None,
) -> None:
    """Persist one audit record. No-op when disabled, non-Postgres, or empty patch.

    Pass ``tx`` (an ``ITransaction``) to enlist the audit write in an ongoing
    transaction; otherwise a standalone connector write is used. Never raises.
    """
    if not patch:
        return
    if not is_enabled(table_name):
        return
    try:
        params = _resolve_params(
            table_name, record_id, operation, patch, run_id, phase_code, source
        )
        if tx is not None:
            tx.execute(_INSERT_SQL, params)
        else:
            _connector().execute(_INSERT_SQL, params)
    except Exception:
        logger.debug(
            "audit write failed for %s#%s (%s)", table_name, record_id, operation,
            exc_info=True,
        )


def record_audit_batch(
    table_name: str,
    operation: str,
    rows: Iterable[tuple],
    *,
    run_id: Any = None,
    phase_code: Any = None,
    source: str | None = None,
) -> None:
    """Persist many audit records via a single ``execute_many``.

    ``rows`` is an iterable of ``(record_id, patch)`` tuples. Records with an
    empty patch are skipped. Never raises.
    """
    if not is_enabled(table_name):
        return
    try:
        param_rows = [
            _resolve_params(
                table_name, record_id, operation, patch, run_id, phase_code, source
            )
            for record_id, patch in rows
            if patch
        ]
        if not param_rows:
            return
        _connector().execute_many(_INSERT_SQL, param_rows)
    except Exception:
        logger.debug(
            "audit batch write failed for %s (%s)", table_name, operation,
            exc_info=True,
        )
