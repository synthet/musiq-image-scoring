"""Tests for recalc_composite_scores helpers and topiq-inclusive fusion."""
import pytest

from modules.score_normalization import compute_composites, reload_config
from scripts.analysis.recalc_composite_scores import row_to_scores


MODERATE_FUSION = {
    "general": {"liqe": 0.38, "spaq": 0.32, "topiq": 0.15, "ava": 0.15},
    "technical": {"topiq": 0.35, "spaq": 0.30, "liqe": 0.35},
    "aesthetic": {"ava": 0.40, "spaq": 0.50, "liqe": 0.10},
}

MODERATE_ANCHORS = {
    "liqe": {"p02": 0.311, "p98": 0.998},
    "ava": {"p02": 0.301, "p98": 0.524},
    "spaq": {"p02": 0.257, "p98": 0.760},
    "topiq": {"p02": 0.390, "p98": 0.709},
}


@pytest.fixture
def moderate_config(monkeypatch):
    """Patch score_normalization config cache with moderate fusion profile."""
    cfg = {
        "percentile_anchors": MODERATE_ANCHORS,
        "scoring": {"fusion": MODERATE_FUSION},
    }
    monkeypatch.setattr(
        "modules.score_normalization._config_cache",
        cfg,
    )
    yield cfg
    reload_config()


class TestRowToScores:
    def test_legacy_columns(self):
        row = {"score_liqe": 0.8, "score_ava": 0.4, "score_spaq": 0.6}
        scores = row_to_scores(row)
        assert scores == {"liqe": 0.8, "ava": 0.4, "spaq": 0.6}

    def test_includes_topiq_from_flat_key(self):
        row = {"score_liqe": 0.8, "topiq": 0.55}
        scores = row_to_scores(row)
        assert scores["topiq"] == 0.55

    def test_skips_null_and_zero(self):
        row = {"score_liqe": 0.0, "score_ava": None, "score_spaq": 0.5}
        scores = row_to_scores(row)
        assert scores == {"spaq": 0.5}

    def test_empty_row(self):
        assert row_to_scores({}) == {}


class TestTopiqInclusiveFusion:
    def test_technical_differs_from_liqe_only(self, moderate_config):
        scores = {"liqe": 0.85, "spaq": 0.55, "topiq": 0.62}
        result = compute_composites(scores)
        liqe_only = compute_composites({"liqe": 0.85})
        assert abs(result["technical"] - liqe_only["technical"]) > 0.01

    def test_all_composites_in_range(self, moderate_config):
        scores = {"liqe": 0.70, "ava": 0.42, "spaq": 0.61, "topiq": 0.58}
        result = compute_composites(scores)
        for key in ("general", "technical", "aesthetic"):
            assert 0.0 <= result[key] <= 1.0

    def test_missing_topiq_renormalizes(self, moderate_config):
        full = compute_composites({"liqe": 0.75, "spaq": 0.60, "topiq": 0.55})
        partial = compute_composites({"liqe": 0.75, "spaq": 0.60})
        assert full["technical"] != partial["technical"] or full["general"] != partial["general"]
