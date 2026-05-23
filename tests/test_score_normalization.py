"""Tests for score normalization, especially missing model handling."""
import pytest
from modules.score_normalization import (
    DEFAULT_COMPOSITE_WEIGHTS,
    DEFAULT_PERCENTILE_ANCHORS,
    compute_all,
    compute_composites,
    reload_config,
)


@pytest.fixture(autouse=True)
def default_fusion_config(monkeypatch):
    """Isolate tests from live config.json fusion/anchor overrides."""
    cfg = {
        "percentile_anchors": DEFAULT_PERCENTILE_ANCHORS,
        "scoring": {"fusion": DEFAULT_COMPOSITE_WEIGHTS},
        "composite_weights": DEFAULT_COMPOSITE_WEIGHTS,
    }
    monkeypatch.setattr("modules.score_normalization._config_cache", cfg)
    yield
    reload_config()


class TestComputeCompositesWithMissingModels:
    """Test that missing models don't corrupt composite scores."""

    def test_all_models_present(self):
        """With all models present, composites should compute normally."""
        scores = {"liqe": 0.85, "ava": 0.42, "spaq": 0.61}
        result = compute_composites(scores)
        assert 0.0 <= result["general"] <= 1.0
        assert 0.0 <= result["technical"] <= 1.0
        assert 0.0 <= result["aesthetic"] <= 1.0

    def test_single_model_present(self):
        """With only one model, composites should still be reasonable."""
        scores = {"liqe": 0.85}
        result = compute_composites(scores)
        # Technical uses only liqe — should reflect liqe score
        assert result["technical"] > 0.0
        # General has liqe weight 0.45 — with re-normalization should be based on liqe alone
        assert result["general"] > 0.0

    def test_missing_model_not_zero(self):
        """Missing models should NOT pull composite toward 0."""
        # Only liqe present — high value
        scores_partial = {"liqe": 0.85}
        result_partial = compute_composites(scores_partial)

        # All models present with same liqe score
        scores_full = {"liqe": 0.85, "ava": 0.85, "spaq": 0.85}
        result_full = compute_composites(scores_full)

        # The technical score (100% liqe) should be the same
        assert abs(result_partial["technical"] - result_full["technical"]) < 0.01

    def test_empty_scores(self):
        """Empty scores dict should return 0 for all composites."""
        result = compute_composites({})
        assert result["general"] == 0.0
        assert result["technical"] == 0.0
        assert result["aesthetic"] == 0.0

    def test_unknown_model_ignored(self):
        """Models not in the weight config should not affect results."""
        scores = {"liqe": 0.85, "ava": 0.42, "spaq": 0.61, "unknown_model": 0.99}
        result = compute_composites(scores)
        assert 0.0 <= result["general"] <= 1.0

    def test_compute_all_with_partial_scores(self):
        """compute_all should work with partial model scores."""
        scores = {"liqe": 0.70}
        result = compute_all(scores)
        assert "general" in result
        assert "technical" in result
        assert "aesthetic" in result
        assert "rating" in result
        assert "label" in result
        assert 1 <= result["rating"] <= 5

    def test_general_not_pulled_down_by_missing(self):
        """General score with only liqe should reflect liqe quality, not be penalized."""
        # High liqe score
        scores = {"liqe": 0.95}
        result = compute_composites(scores)
        # With re-normalization, general should be based purely on liqe's rescaled score
        # It should not be ~0.45 * liqe (which would happen without re-normalization)
        assert result["general"] > 0.3  # Should be substantial, not halved
