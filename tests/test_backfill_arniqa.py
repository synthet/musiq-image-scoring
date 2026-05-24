"""Unit tests for scripts/maintenance/backfill_arniqa.py (no GPU/DB)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from modules.engines.arniqa_model import ArniqaModelWrapper

from scripts.maintenance import backfill_arniqa as backfill


def test_build_write_result_shape_shadow_true():
    wrapper = ArniqaModelWrapper(scorer=MagicMock(available=True, VERSION="arniqa-1"))
    result = backfill._build_write_result(wrapper, 0.58, is_shadow=True)
    assert "models" in result
    arniqa = result["models"]["arniqa"]
    assert arniqa["status"] == "success"
    assert arniqa["is_shadow"] is True
    assert arniqa["score"] == 0.58
    assert arniqa["normalized_score"] == 0.58


def test_build_write_result_respects_is_shadow_false():
    wrapper = ArniqaModelWrapper(scorer=MagicMock(available=True, VERSION="arniqa-1"))
    result = backfill._build_write_result(wrapper, 0.42, is_shadow=False)
    assert result["models"]["arniqa"]["is_shadow"] is False


def test_is_shadow_from_config_uses_registry():
    with patch.object(backfill, "get_registry") as mock_get:
        mock_get.return_value.is_shadow.return_value = True
        assert backfill._is_shadow_from_config() is True
        mock_get.return_value.is_shadow.assert_called_once_with("arniqa")


def test_is_shadow_from_config_defaults_true_on_error():
    with patch.object(backfill, "get_registry", side_effect=RuntimeError("no config")):
        assert backfill._is_shadow_from_config() is True


def test_model_name_constant():
    assert backfill._MODEL_NAME == "arniqa"
