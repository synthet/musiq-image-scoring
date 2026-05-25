"""Unit tests for production MultiModelHost factory (no GPU/TF)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from modules.engines.factory import (
    create_production_scoring_host,
    ensure_production_registry,
    load_production_models,
)
from modules.engines.host import MultiModelHost
from modules.engines.registry import ModelRegistry, reset_registry


class _StubMusiqBackend:
    VERSION = "stub-musiq"
    model_sources = {"spaq": {}, "ava": {}}

    def load_model(self, name: str) -> bool:
        return name in ("spaq", "ava")

    def predict_quality(self, image_path: str, name: str):
        return 70.0 if name == "spaq" else 5.0

    def is_raw_file(self, file_path: str) -> bool:
        return False

    def preprocess_image(self, file_path: str, **kwargs):
        return file_path

    def calculate_weighted_categories(self, normalized):
        return {"general": 0.5, "technical": 0.5, "aesthetic": 0.5}


@pytest.fixture(autouse=True)
def _clean_registry():
    reset_registry()
    yield
    reset_registry()


def test_ensure_production_registry_registers_musiq_and_liqe():
    reg = ModelRegistry()
    ensure_production_registry(_StubMusiqBackend(), registry=reg)
    names = {m.name for m in reg.all_registered()}
    assert {"spaq", "ava", "liqe"}.issubset(names)


def test_create_production_scoring_host_returns_host(monkeypatch):
    import importlib

    ram = importlib.import_module("scripts.python.run_all_musiq_models")
    monkeypatch.setattr(ram, "MultiModelMUSIQ", _StubMusiqBackend)
    host = create_production_scoring_host(registry=ModelRegistry())
    assert isinstance(host, MultiModelHost)
    assert host.backend.VERSION == "stub-musiq"


def test_load_production_models_fails_when_enabled_model_missing():
    reg = ModelRegistry()

    class _FailSpaq(_StubMusiqBackend):
        def load_model(self, name: str) -> bool:
            return name != "spaq"

    backend = _FailSpaq()
    ensure_production_registry(backend, registry=reg)
    host = MultiModelHost(backend=backend, registry=reg)
    ok, msg = load_production_models(host)
    assert ok is False
    assert "spaq" in msg


def test_load_production_models_allows_shadow_only_failure():
    from modules.engines.topiq_model import TopiqModelWrapper

    reg = ModelRegistry()
    ensure_production_registry(_StubMusiqBackend(), registry=reg)
    reg.register(TopiqModelWrapper(scorer=MagicMock(available=False)))

    object.__setattr__(
        reg,
        "_resolve_config",
        staticmethod(
            lambda _s: {
                "spaq": {"enabled": True, "shadow": False},
                "ava": {"enabled": True, "shadow": False},
                "liqe": {"enabled": True, "shadow": False},
                "topiq": {"enabled": False, "shadow": True},
            }
        ),
    )
    host = MultiModelHost(backend=_StubMusiqBackend(), registry=reg)
    ok, _msg = load_production_models(host)
    assert ok is True
