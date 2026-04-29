"""Unit tests for IScoringModel + ModelRegistry. No GPU/DB/ML deps."""

from __future__ import annotations

from typing import Any, Dict

import pytest

from modules.engines.base import IScoringModel
from modules.engines.registry import ModelRegistry, get_registry, reset_registry


class _StubModel(IScoringModel):
    def __init__(self, name: str, score_range=(0.0, 100.0), framework: str = "tf") -> None:
        self.name = name
        self.version = "test-1"
        self.framework = framework
        self.score_range = score_range
        self.loaded = False

    def load(self) -> bool:
        self.loaded = True
        return True

    def predict(self, image_path: str) -> Dict[str, Any]:
        return {"score": 50.0, "status": "success", "error": None}


def test_default_normalize_is_linear_over_range():
    m = _StubModel("liqe-like", score_range=(1.0, 5.0))
    assert m.normalize(1.0) == pytest.approx(0.0)
    assert m.normalize(3.0) == pytest.approx(0.5)
    assert m.normalize(5.0) == pytest.approx(1.0)


def test_normalize_clamps_out_of_range():
    m = _StubModel("spaq-like", score_range=(0.0, 100.0))
    assert m.normalize(-10.0) == 0.0
    assert m.normalize(150.0) == 1.0


def test_normalize_degenerate_range_returns_zero():
    m = _StubModel("bad", score_range=(5.0, 5.0))
    assert m.normalize(5.0) == 0.0


def test_register_requires_name():
    reg = ModelRegistry()
    bad = _StubModel(name="")
    with pytest.raises(ValueError):
        reg.register(bad)


def test_register_and_lookup():
    reg = ModelRegistry()
    a = _StubModel("a")
    reg.register(a)
    assert reg.get("a") is a
    assert reg.get("missing") is None
    assert reg.all_registered() == [a]


def test_unregistered_models_default_to_enabled():
    """A registered model absent from config must run as production."""
    reg = ModelRegistry()
    spaq = _StubModel("spaq")
    reg.register(spaq)
    assert reg.enabled(config_section={}) == [spaq]
    assert reg.shadow(config_section={}) == []
    assert reg.all_active(config_section={}) == [spaq]


def test_disabled_model_is_skipped():
    reg = ModelRegistry()
    spaq = _StubModel("spaq")
    reg.register(spaq)
    cfg = {"spaq": {"enabled": False, "shadow": False}}
    assert reg.enabled(config_section=cfg) == []
    assert reg.all_active(config_section=cfg) == []


def test_shadow_flag_excludes_from_enabled_but_keeps_active():
    reg = ModelRegistry()
    qpt = _StubModel("qpt_v2")
    reg.register(qpt)
    cfg = {"qpt_v2": {"enabled": False, "shadow": True}}
    assert reg.enabled(config_section=cfg) == []
    assert reg.shadow(config_section=cfg) == [qpt]
    assert reg.all_active(config_section=cfg) == [qpt]
    assert reg.is_shadow("qpt_v2", config_section=cfg) is True


def test_shadow_wins_over_enabled():
    """If both flags are true, shadow takes precedence — fusion must not see it."""
    reg = ModelRegistry()
    m = _StubModel("dual")
    reg.register(m)
    cfg = {"dual": {"enabled": True, "shadow": True}}
    assert m not in reg.enabled(config_section=cfg)
    assert m in reg.shadow(config_section=cfg)
    assert m in reg.all_active(config_section=cfg)


def test_re_registration_replaces():
    reg = ModelRegistry()
    a1 = _StubModel("a")
    a2 = _StubModel("a")
    reg.register(a1)
    reg.register(a2)
    assert reg.get("a") is a2
    assert reg.all_registered() == [a2]


def test_singleton_get_registry_is_idempotent():
    reset_registry()
    try:
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2
    finally:
        reset_registry()


def test_reset_registry_clears_singleton():
    reset_registry()
    r1 = get_registry()
    r1.register(_StubModel("ephemeral"))
    reset_registry()
    r2 = get_registry()
    assert r2 is not r1
    assert r2.get("ephemeral") is None
