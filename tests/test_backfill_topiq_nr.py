"""Unit tests for scripts/maintenance/backfill_topiq_nr.py (no GPU/DB)."""

from __future__ import annotations

from unittest.mock import MagicMock

from modules.engines.topiq_model import TopiqModelWrapper

from scripts.maintenance import backfill_topiq_nr as backfill


def test_build_write_result_shape():
    wrapper = TopiqModelWrapper(scorer=MagicMock(available=True, VERSION="topiq-nr-1"))
    result = backfill._build_write_result(wrapper, 0.72)
    assert "models" in result
    topiq = result["models"]["topiq"]
    assert topiq["status"] == "success"
    assert topiq["is_shadow"] is False
    assert topiq["score"] == 0.72
    assert topiq["normalized_score"] == 0.72


def test_model_name_constant():
    assert backfill._MODEL_NAME == "topiq"
