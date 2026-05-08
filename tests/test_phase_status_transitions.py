"""Unit tests for the per-image phase-status transition contract.

Covers ``phases.is_transition_allowed`` and the matching guard inside
``db.set_image_phase_status`` (verified via monkeypatched connector — no real
DB needed).
"""

from __future__ import annotations

import logging

import pytest

from modules import phases


# ---------------------------------------------------------------------------
# Pure transition-map checks
# ---------------------------------------------------------------------------

LEGAL_TRANSITIONS = [
    (phases.PhaseStatus.NOT_STARTED, phases.PhaseStatus.RUNNING),
    (phases.PhaseStatus.NOT_STARTED, phases.PhaseStatus.NOT_STARTED),  # idempotent
    (phases.PhaseStatus.NOT_STARTED, phases.PhaseStatus.DONE),         # one-shot maintenance
    (phases.PhaseStatus.RUNNING, phases.PhaseStatus.DONE),
    (phases.PhaseStatus.RUNNING, phases.PhaseStatus.FAILED),
    (phases.PhaseStatus.RUNNING, phases.PhaseStatus.NOT_STARTED),      # heal reset
    (phases.PhaseStatus.DONE, phases.PhaseStatus.RESTARTING),
    (phases.PhaseStatus.DONE, phases.PhaseStatus.RUNNING),             # rerun
    (phases.PhaseStatus.DONE, phases.PhaseStatus.NOT_STARTED),         # heal reset
    (phases.PhaseStatus.FAILED, phases.PhaseStatus.RUNNING),           # retry
    (phases.PhaseStatus.SKIPPED, phases.PhaseStatus.RUNNING),
    (phases.PhaseStatus.QUEUED, phases.PhaseStatus.RUNNING),
]

ILLEGAL_TRANSITIONS = [
    (phases.PhaseStatus.DONE, phases.PhaseStatus.SKIPPED),    # bypass without rerun
    (phases.PhaseStatus.DONE, phases.PhaseStatus.FAILED),     # ditto
    (phases.PhaseStatus.SKIPPED, phases.PhaseStatus.DONE),    # silent promotion
    (phases.PhaseStatus.FAILED, phases.PhaseStatus.DONE),     # silent promotion
    (phases.PhaseStatus.FAILED, phases.PhaseStatus.SKIPPED),
]


@pytest.mark.parametrize("a,b", LEGAL_TRANSITIONS)
def test_legal_transitions(a, b):
    assert phases.is_transition_allowed(a, b)


@pytest.mark.parametrize("a,b", ILLEGAL_TRANSITIONS)
def test_illegal_transitions(a, b):
    assert not phases.is_transition_allowed(a, b)


def test_string_inputs_are_tolerated():
    assert phases.is_transition_allowed("not_started", "running")
    assert phases.is_transition_allowed("done", "restarting")
    assert not phases.is_transition_allowed("done", "skipped")


def test_unknown_status_is_tolerant_true():
    """Unknown statuses (typos, future values) shouldn't block anything."""
    assert phases.is_transition_allowed("garbage", "running") is True
    assert phases.is_transition_allowed("done", "garbage") is True


# ---------------------------------------------------------------------------
# set_image_phase_status guard
# ---------------------------------------------------------------------------

class _FakeTx:
    """Minimal transaction that records executed SQL and lets us seed query results."""

    def __init__(self, *, existing_status=None, folder_id=42, parent_chain=None):
        self._existing_status = existing_status
        self._folder_id = folder_id
        self._parent_chain = parent_chain or {42: None}
        self.executed_sql: list[tuple[str, tuple]] = []
        self._next_image_lookup = True  # first SELECT image_phase_status, second folder_id

    def query_one(self, sql, params=None):
        s = sql.upper()
        if "FROM IMAGE_PHASE_STATUS" in s and "WHERE IMAGE_ID" in s:
            if self._existing_status is None:
                return None
            return {"id": 1, "status": self._existing_status, "attempt_count": 0}
        if "FROM IMAGES WHERE ID" in s:
            return {"folder_id": self._folder_id}
        if "FROM FOLDERS WHERE ID" in s:
            current = params[0]
            return {"parent_id": self._parent_chain.get(current)}
        return None

    def execute(self, sql, params=None):
        self.executed_sql.append((sql, tuple(params) if params else ()))
        return 1


class _FakeConnector:
    def __init__(self, tx: _FakeTx):
        self._tx = tx

    def run_transaction(self, fn):
        return fn(self._tx)

    def query_one(self, *a, **kw):
        return None


def _patch_db_for_set(monkeypatch, tx: _FakeTx):
    from modules import db
    monkeypatch.setattr(db, "get_phase_id", lambda code: 3)
    monkeypatch.setattr(db, "get_connector", lambda: _FakeConnector(tx))
    monkeypatch.setattr(db, "_get_db_engine", lambda: "sqlite")  # disables postgres-only side-effect
    # No-op the post-commit event/incident emissions.
    monkeypatch.setattr(db, "record_pipeline_event", lambda *a, **kw: None, raising=False)
    monkeypatch.setattr(db, "record_image_incident", lambda *a, **kw: None, raising=False)


def test_set_status_warns_on_illegal_transition(monkeypatch, caplog):
    tx = _FakeTx(existing_status="done")
    _patch_db_for_set(monkeypatch, tx)
    from modules import db
    with caplog.at_level(logging.WARNING):
        db.set_image_phase_status(image_id=1, phase_code="scoring", status="skipped")
    # Update still happened (warn-only by default).
    update_sqls = [s for s, _ in tx.executed_sql if "UPDATE IMAGE_PHASE_STATUS" in s.upper()]
    assert update_sqls, "expected the UPDATE to proceed in non-strict mode"
    assert any("illegal transition" in rec.message for rec in caplog.records)


def test_set_status_strict_raises_on_illegal_transition(monkeypatch):
    tx = _FakeTx(existing_status="done")
    _patch_db_for_set(monkeypatch, tx)
    from modules import db
    monkeypatch.setattr(
        "modules.config.get_config_value",
        lambda key, default=None: True if key == "database.strict_phase_transitions" else default,
    )
    with pytest.raises(Exception):
        db.set_image_phase_status(image_id=1, phase_code="scoring", status="skipped")


def test_set_status_invalidates_folder_aggregate_in_tx(monkeypatch):
    """Folder + ancestors should be flipped to phase_agg_dirty=1 in the same tx."""
    parent_chain = {42: 7, 7: None}  # folder 42 has parent 7 (root)
    tx = _FakeTx(existing_status="not_started", folder_id=42, parent_chain=parent_chain)
    _patch_db_for_set(monkeypatch, tx)
    from modules import db
    db.set_image_phase_status(image_id=1, phase_code="scoring", status="running")
    upd = [
        (s, p) for s, p in tx.executed_sql
        if "UPDATE FOLDERS" in s.upper() and "PHASE_AGG_DIRTY" in s.upper()
    ]
    assert upd, "expected aggregate UPDATE inside the transaction"
    sql, params = upd[0]
    # Both 42 and 7 should be in the IN(...) param list.
    assert 42 in params and 7 in params, params


def test_set_status_legal_transition_no_warning(monkeypatch, caplog):
    tx = _FakeTx(existing_status="not_started")
    _patch_db_for_set(monkeypatch, tx)
    from modules import db
    with caplog.at_level(logging.WARNING):
        db.set_image_phase_status(image_id=1, phase_code="scoring", status="running")
    assert not any("illegal transition" in rec.message for rec in caplog.records)
