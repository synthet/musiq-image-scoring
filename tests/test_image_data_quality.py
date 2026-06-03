"""Unit tests for compute_image_data_quality_flags_batch (pure logic, fake connector)."""

from __future__ import annotations

import modules.config as cfg
from modules import db_legacy


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    def query(self, _sql, _params=None):
        return self._rows


def _patch(monkeypatch, rows, *, captions: bool):
    monkeypatch.setattr(db_legacy, "get_connector", lambda: _FakeConn(rows))
    monkeypatch.setattr(cfg, "get_config_section", lambda section: {"captions_default": captions})


def test_batch_flags_keywords_and_scoring_gaps(monkeypatch):
    rows = [
        # done keywords, no tags / no rows -> keywords gap
        {"id": 1, "keywords": "", "title": "t", "description": "d", "score_general": 0.9,
         "kw_count": 0, "kw_status": "done", "sc_status": "done"},
        # done keywords with real tags + title/desc -> complete (no gap)
        {"id": 2, "keywords": "nature", "title": "t", "description": "d", "score_general": 0.9,
         "kw_count": 0, "kw_status": "done", "sc_status": "done"},
        # scoring done but score missing -> scoring gap
        {"id": 3, "keywords": "nature", "title": "t", "description": "d", "score_general": None,
         "kw_count": 1, "kw_status": "done", "sc_status": "done"},
        # nothing terminal -> no flags
        {"id": 4, "keywords": "", "title": "", "description": "", "score_general": 0.5,
         "kw_count": 0, "kw_status": "not_started", "sc_status": "done"},
    ]
    _patch(monkeypatch, rows, captions=True)

    out = db_legacy.compute_image_data_quality_flags_batch([1, 2, 3, 4])

    assert out.get(1) == {"keywords_data_gap": True}
    assert 2 not in out  # complete -> omitted
    assert out.get(3) == {"scoring_data_gap": True}
    assert 4 not in out


def test_batch_flags_caption_requirement_toggle(monkeypatch):
    # Real tags present but no title/description.
    rows = [
        {"id": 7, "keywords": "nature", "title": "", "description": "", "score_general": 0.9,
         "kw_count": 0, "kw_status": "done", "sc_status": "done"},
    ]

    _patch(monkeypatch, rows, captions=True)
    assert db_legacy.compute_image_data_quality_flags_batch([7]).get(7) == {"keywords_data_gap": True}

    _patch(monkeypatch, rows, captions=False)
    # Captions not required -> tags alone are complete -> no gap.
    assert 7 not in db_legacy.compute_image_data_quality_flags_batch([7])


def test_batch_flags_empty_and_invalid_ids(monkeypatch):
    _patch(monkeypatch, [], captions=True)
    assert db_legacy.compute_image_data_quality_flags_batch([]) == {}
    assert db_legacy.compute_image_data_quality_flags_batch([None, "x"]) == {}
