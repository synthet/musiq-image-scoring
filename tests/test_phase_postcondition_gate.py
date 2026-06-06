"""Phase 1 postcondition gate (issue #230) — prevent phantom CULLING ``done``.

Fast unit tests for ``modules.db_legacy._apply_done_postcondition_gate``: no DB,
no ML. The gate is exercised directly with the culling completeness predicates and
the ``phases.enforce_done_postconditions`` flag monkeypatched.
"""
from __future__ import annotations

import modules.config as config
import modules.db as db
import modules.db_legacy as dbl
from modules.phases import PhaseCode, PhaseStatus


def _set_flag(monkeypatch, enabled: bool) -> None:
    def _fake_get(key, default=None):
        if key == "phases.enforce_done_postconditions":
            return enabled
        return default

    monkeypatch.setattr(config, "get_config_value", _fake_get)


def _set_predicates(monkeypatch, *, complete: bool, artefacts_missing: bool) -> None:
    monkeypatch.setattr(db, "is_image_culling_complete", lambda image_id: complete, raising=False)
    monkeypatch.setattr(
        db, "is_image_culling_similarity_artefacts_missing",
        lambda image_id: artefacts_missing, raising=False,
    )


def test_flag_off_is_noop(monkeypatch):
    """Default (flag off): a phantom done is passed through unchanged — no behavior change."""
    _set_flag(monkeypatch, False)
    _set_predicates(monkeypatch, complete=True, artefacts_missing=True)
    status, error = dbl._apply_done_postcondition_gate(1, PhaseCode.CULLING, PhaseStatus.DONE, None)
    assert status == PhaseStatus.DONE
    assert error is None


def test_flag_on_blocks_phantom_done(monkeypatch):
    """Flag on + missing similarity artefacts: done is downgraded to failed."""
    _set_flag(monkeypatch, True)
    _set_predicates(monkeypatch, complete=True, artefacts_missing=True)
    status, error = dbl._apply_done_postcondition_gate(1, PhaseCode.CULLING, PhaseStatus.DONE, None)
    assert status == PhaseStatus.FAILED
    assert error == "postcondition_failed:missing_similarity_artefacts"


def test_flag_on_incomplete_blocks_done(monkeypatch):
    """Flag on + culling not complete: done is downgraded to failed."""
    _set_flag(monkeypatch, True)
    _set_predicates(monkeypatch, complete=False, artefacts_missing=False)
    status, error = dbl._apply_done_postcondition_gate(1, PhaseCode.CULLING, PhaseStatus.DONE, None)
    assert status == PhaseStatus.FAILED


def test_flag_on_legit_singleton_passes(monkeypatch):
    """Flag on + clustered with artefacts present (stack or singleton embedding): done stands."""
    _set_flag(monkeypatch, True)
    _set_predicates(monkeypatch, complete=True, artefacts_missing=False)
    status, error = dbl._apply_done_postcondition_gate(1, PhaseCode.CULLING, PhaseStatus.DONE, None)
    assert status == PhaseStatus.DONE
    assert error is None


def test_existing_error_preserved(monkeypatch):
    """An explicit error already supplied by the caller is not overwritten by the gate."""
    _set_flag(monkeypatch, True)
    _set_predicates(monkeypatch, complete=True, artefacts_missing=True)
    status, error = dbl._apply_done_postcondition_gate(
        1, PhaseCode.CULLING, PhaseStatus.DONE, "boom"
    )
    assert status == PhaseStatus.FAILED
    assert error == "boom"


def test_non_culling_phase_unaffected(monkeypatch):
    """Gate is scoped to CULLING in Phase 1: scoring done is never gated."""
    _set_flag(monkeypatch, True)
    _set_predicates(monkeypatch, complete=True, artefacts_missing=True)
    status, error = dbl._apply_done_postcondition_gate(1, PhaseCode.SCORING, PhaseStatus.DONE, None)
    assert status == PhaseStatus.DONE


def test_non_done_status_unaffected(monkeypatch):
    """Only transitions into done are gated; running passes straight through."""
    _set_flag(monkeypatch, True)
    _set_predicates(monkeypatch, complete=False, artefacts_missing=True)
    status, error = dbl._apply_done_postcondition_gate(
        1, PhaseCode.CULLING, PhaseStatus.RUNNING, None
    )
    assert status == PhaseStatus.RUNNING


def test_predicate_error_fails_open(monkeypatch):
    """A gate-internal error must never block legitimate progress (fail open)."""
    _set_flag(monkeypatch, True)

    def _boom(image_id):
        raise RuntimeError("db down")

    monkeypatch.setattr(db, "is_image_culling_complete", _boom, raising=False)
    status, error = dbl._apply_done_postcondition_gate(1, PhaseCode.CULLING, PhaseStatus.DONE, None)
    assert status == PhaseStatus.DONE
    assert error is None


def test_string_args_accepted(monkeypatch):
    """Helper accepts raw string phase/status (not just enums)."""
    _set_flag(monkeypatch, True)
    _set_predicates(monkeypatch, complete=True, artefacts_missing=True)
    status, error = dbl._apply_done_postcondition_gate(1, "culling", "done", None)
    assert status == PhaseStatus.FAILED
