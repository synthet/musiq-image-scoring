"""Tests for the registry-driven MCP get_model_status helper.

`_registry_model_status()` must report every registered scoring model with its
enabled/shadow flags resolved from config — not the legacy hardcoded MUSIQ list.
GPU-free; no DB.
"""

from modules.engines.base import IScoringModel
from modules.engines.registry import get_registry, reset_registry
from modules.mcp_server import _registry_model_status


class _Stub(IScoringModel):
    def __init__(self, name, version, framework, score_range):
        self.name = name
        self.version = version
        self.framework = framework
        self.score_range = score_range
        self.load_status = "loaded"

    def load(self):
        return True

    def predict(self, image_path):
        return {"score": 0.0, "status": "success", "error": None}


def test_registry_model_status_empty_registry():
    reset_registry()
    assert _registry_model_status() == {}


def test_registry_model_status_reflects_enabled_and_shadow(monkeypatch):
    reset_registry()
    reg = get_registry()
    reg.register(_Stub("spaq", "musiq-1", "tf", (0.0, 100.0)))
    reg.register(_Stub("topiq", "topiq-1", "torch", (0.0, 1.0)))
    reg.register(_Stub("cursor", "cursor-1", "api", (0.0, 1.0)))

    monkeypatch.setattr(
        "modules.engines.registry.ModelRegistry._resolve_config",
        staticmethod(lambda cfg=None: {
            "spaq": {"enabled": True, "shadow": False},
            "topiq": {"enabled": True, "shadow": False},
            "cursor": {"enabled": False, "shadow": True},
        }),
    )

    status = _registry_model_status()

    # Registry models surface — not the legacy koniq/paq2piq hardcoded list.
    assert set(status) == {"spaq", "topiq", "cursor"}

    assert status["spaq"] == {
        "enabled": True,
        "shadow": False,
        "framework": "tf",
        "version": "musiq-1",
        "score_range": [0.0, 100.0],
        "load_status": "loaded",
    }
    # topiq is a fused production model under the moderate profile.
    assert status["topiq"]["enabled"] is True
    assert status["topiq"]["shadow"] is False
    # cursor runs in shadow only.
    assert status["cursor"]["enabled"] is False
    assert status["cursor"]["shadow"] is True
