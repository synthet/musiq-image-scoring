"""Unit tests for modules.phantom_score_finalize.finalize_phantom_scores (no DB required).

Patches the connector + get_phase_incomplete_sql + set_image_phase_status so the
orchestration (candidate selection, composite backfill, phase flip, dry-run) is verified
without a live database. ``score_normalization.compute_all`` runs for real (pure function).
"""
from __future__ import annotations

from modules import phantom_score_finalize as psf


class _FakeConn:
    def __init__(self, candidate_rows, model_rows):
        self._candidates = candidate_rows
        self._models = model_rows
        self.executed = []

    def query(self, sql, params=None):
        # Route by SQL content: the model-score fetch is the only one hitting that table.
        if "image_model_scores" in sql:
            return self._models
        return self._candidates

    def execute(self, sql, params=None):
        self.executed.append((sql, params))


def _patch(monkeypatch, candidate_rows, model_rows):
    fake = _FakeConn(candidate_rows, model_rows)
    monkeypatch.setattr(psf.db, "get_connector", lambda: fake)
    monkeypatch.setattr(psf.db, "get_phase_incomplete_sql", lambda code, alias="": "1=0")
    flips = []
    monkeypatch.setattr(psf.db, "set_image_phase_status", lambda iid, code, status: flips.append((iid, code, status)))
    return fake, flips


_MODEL_ROWS = [
    {"image_id": 1, "model_name": "liqe", "normalized": 0.55, "raw_score": 3.2},
    {"image_id": 1, "model_name": "spaq", "normalized": 0.52, "raw_score": 52.0},
    {"image_id": 1, "model_name": "ava", "normalized": 0.43, "raw_score": 4.9},
    {"image_id": 1, "model_name": "topiq", "normalized": 0.54, "raw_score": 0.54},
    {"image_id": 1, "model_name": "arniqa", "normalized": 0.63, "raw_score": 0.63},
]


def test_dry_run_computes_but_writes_nothing(monkeypatch):
    fake, flips = _patch(
        monkeypatch,
        candidate_rows=[{"id": 1, "score_general": None, "scoring_status": "not_started"}],
        model_rows=_MODEL_ROWS,
    )
    summary = psf.finalize_phantom_scores(scope_path="/mnt/d/x", dry_run=True)

    assert summary["candidates"] == 1
    assert summary["composites_backfilled"] == 1
    assert summary["phase_finalized"] == 1
    assert fake.executed == []      # no UPDATE in dry-run
    assert flips == []              # no phase flip in dry-run
    assert summary["samples"][0]["score_general"] is not None


def test_apply_backfills_composite_and_flips_phase(monkeypatch):
    fake, flips = _patch(
        monkeypatch,
        candidate_rows=[{"id": 1, "score_general": None, "scoring_status": "not_started"}],
        model_rows=_MODEL_ROWS,
    )
    summary = psf.finalize_phantom_scores(scope_path="/mnt/d/x", dry_run=False)

    assert summary["composites_backfilled"] == 1
    assert summary["phase_finalized"] == 1
    # One UPDATE images ... SET score_general=... and a phase flip to done.
    assert len(fake.executed) == 1
    update_sql, update_params = fake.executed[0]
    assert "UPDATE images" in update_sql and "score_general" in update_sql
    assert update_params[-1] == 1  # WHERE id = 1
    assert flips == [(1, "scoring", "done")]


def test_phase_flip_without_backfill_when_general_present(monkeypatch):
    """An image already carrying score_general (only the phase row is stale) is flipped,
    not re-backfilled."""
    fake, flips = _patch(
        monkeypatch,
        candidate_rows=[{"id": 1, "score_general": 0.71, "scoring_status": "not_started"}],
        model_rows=_MODEL_ROWS,
    )
    summary = psf.finalize_phantom_scores(scope_path="/mnt/d/x", dry_run=False)

    assert summary["composites_backfilled"] == 0
    assert summary["phase_finalized"] == 1
    assert fake.executed == []                      # no composite UPDATE
    assert flips == [(1, "scoring", "done")]


def test_no_candidates_is_noop(monkeypatch):
    fake, flips = _patch(monkeypatch, candidate_rows=[], model_rows=[])
    summary = psf.finalize_phantom_scores(scope_path="/mnt/d/x", dry_run=False)

    assert summary["candidates"] == 0
    assert summary["phase_finalized"] == 0
    assert fake.executed == []
    assert flips == []


def test_candidate_without_model_rows_is_skipped(monkeypatch):
    fake, flips = _patch(
        monkeypatch,
        candidate_rows=[{"id": 9, "score_general": None, "scoring_status": "failed"}],
        model_rows=[],  # no model scores for image 9
    )
    summary = psf.finalize_phantom_scores(scope_path="/mnt/d/x", dry_run=False)

    assert summary["no_model_scores"] == 1
    assert summary["phase_finalized"] == 0
    assert fake.executed == []
    assert flips == []
