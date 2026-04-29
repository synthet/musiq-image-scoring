"""Verify get_composite_weights() resolution order: scoring.fusion > legacy > default."""

from __future__ import annotations

from unittest.mock import patch

from modules import score_normalization as sn


def _with_config(cfg: dict):
    """Patch _load_config and bust the module cache for the duration of one call."""
    sn.reload_config()
    return patch.object(sn, "_load_config", return_value=cfg)


def test_default_when_no_config():
    with _with_config({}):
        assert sn.get_composite_weights() == sn.DEFAULT_COMPOSITE_WEIGHTS


def test_legacy_top_level_composite_weights_used_when_present():
    legacy = {
        "general":   {"liqe": 0.5, "ava": 0.5},
        "technical": {"liqe": 1.0},
        "aesthetic": {"ava": 1.0},
    }
    with _with_config({"composite_weights": legacy}):
        assert sn.get_composite_weights() == legacy


def test_scoring_fusion_takes_precedence_over_legacy():
    canonical = {
        "general":   {"qpt_v2": 0.55, "topiq_nr": 0.30, "liqe": 0.15},
        "technical": {"topiq_nr": 0.65, "qpt_v2": 0.35},
        "aesthetic": {"qpt_v2": 0.75, "liqe": 0.25},
    }
    legacy = {"general": {"liqe": 1.0}, "technical": {"liqe": 1.0}, "aesthetic": {"liqe": 1.0}}
    with _with_config({"composite_weights": legacy, "scoring": {"fusion": canonical}}):
        assert sn.get_composite_weights() == canonical


def test_empty_scoring_fusion_falls_through():
    """Empty dict at scoring.fusion must not shadow legacy/default."""
    legacy = {"general": {"liqe": 1.0}, "technical": {"liqe": 1.0}, "aesthetic": {"liqe": 1.0}}
    with _with_config({"scoring": {"fusion": {}}, "composite_weights": legacy}):
        assert sn.get_composite_weights() == legacy

    with _with_config({"scoring": {"fusion": {}}}):
        assert sn.get_composite_weights() == sn.DEFAULT_COMPOSITE_WEIGHTS


def test_non_dict_scoring_fusion_falls_through():
    with _with_config({"scoring": {"fusion": "not a dict"}}):
        assert sn.get_composite_weights() == sn.DEFAULT_COMPOSITE_WEIGHTS


def test_compute_composites_uses_canonical_weights():
    canonical = {
        "general":   {"liqe": 1.0},   # everything weighted to liqe
        "technical": {"liqe": 1.0},
        "aesthetic": {"liqe": 1.0},
    }
    # rescale_percentile turns liqe=0.998 → 1.0 (top anchor); other models absent.
    with _with_config({"scoring": {"fusion": canonical}}):
        out = sn.compute_composites({"liqe": 0.998})
    assert out["general"] == 1.0
    assert out["technical"] == 1.0
    assert out["aesthetic"] == 1.0
