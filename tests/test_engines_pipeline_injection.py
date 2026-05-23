"""Tests for registry-model injection in the scoring pipeline (Part 0).

Hardware-free: stubs the registry and models; never loads TF/Torch. Verifies
that ScoringWorker injects active registry models into `external_scores` with
the right shape (normalized, is_shadow, subscores) and skips models already
produced by the legacy backend.
"""

from __future__ import annotations

import queue
import threading
from typing import Any, Dict

from modules.pipeline import ScoringWorker


class _FakeModel:
    score_range = (0.0, 100.0)

    def __init__(self, name: str, result: Dict[str, Any], *, load_ok: bool = True) -> None:
        self.name = name
        self._result = result
        self._load_ok = load_ok

    def load(self) -> bool:
        return self._load_ok

    def predict(self, _path: str) -> Dict[str, Any]:
        if isinstance(self._result, Exception):
            raise self._result
        return self._result

    def normalize(self, raw: float) -> float:
        return max(0.0, min(1.0, raw / 100.0))


class _FakeRegistry:
    def __init__(self, models, shadow_names) -> None:
        self._models = models
        self._shadow = set(shadow_names)

    def all_active(self):
        return self._models

    def is_shadow(self, name: str) -> bool:
        return name in self._shadow


class _FakeScorer:
    model_sources = {"spaq": object(), "ava": object()}


def _worker() -> ScoringWorker:
    return ScoringWorker(queue.Queue(), queue.Queue(), threading.Event(), _FakeScorer())


def _patch_registry(monkeypatch, models, shadow_names) -> None:
    monkeypatch.setattr(
        "modules.engines.registry.get_registry",
        lambda: _FakeRegistry(models, shadow_names),
    )


# --- _format_registry_payload (pure) -------------------------------------

def test_format_success_with_subscores():
    model = _FakeModel("cursor", {})
    payload = {
        "score": 82.0,
        "status": "success",
        "subscores": {"composition": 80, "exposure": 70, "sharpness": 90, "subject": 85},
    }
    out = ScoringWorker._format_registry_payload(model, payload, is_shadow=True)
    assert out["score"] == 82.0
    assert out["normalized_score"] == 0.82
    assert out["score_range"] == "0.0-100.0"
    assert out["is_shadow"] is True
    assert out["subscores"]["sharpness"] == 90


def test_format_failed():
    out = ScoringWorker._format_registry_payload(_FakeModel("x", {}), {"status": "failed", "error": "boom"}, False)
    assert out["status"] == "failed"
    assert out["score"] is None
    assert out["error"] == "boom"


def test_format_not_loaded():
    out = ScoringWorker._format_registry_payload(_FakeModel("x", {}), {"status": "not_loaded"}, False)
    assert out["status"] == "not_loaded"


# --- _run_registry_models -------------------------------------------------

def test_injects_active_model(monkeypatch):
    model = _FakeModel("topiq", {"score": 60.0, "status": "success"})
    _patch_registry(monkeypatch, [model], shadow_names=set())
    external: Dict[str, Any] = {}
    _worker()._run_registry_models(external, "/x.jpg", lambda *a, **k: None)

    assert "topiq" in external
    assert external["topiq"]["status"] == "success"
    assert external["topiq"]["normalized_score"] == 0.6
    assert external["topiq"]["is_shadow"] is False


def test_shadow_model_stamped(monkeypatch):
    model = _FakeModel("claude", {"score": 90.0, "status": "success"})
    _patch_registry(monkeypatch, [model], shadow_names={"claude"})
    external: Dict[str, Any] = {}
    _worker()._run_registry_models(external, "/x.jpg", lambda *a, **k: None)
    assert external["claude"]["is_shadow"] is True


def test_skips_legacy_and_existing(monkeypatch):
    spaq = _FakeModel("spaq", {"score": 50.0, "status": "success"})  # in legacy model_sources
    liqe = _FakeModel("liqe", {"score": 4.0, "status": "success"})   # already in external
    topiq = _FakeModel("topiq", {"score": 60.0, "status": "success"})
    _patch_registry(monkeypatch, [spaq, liqe, topiq], shadow_names=set())
    external: Dict[str, Any] = {"liqe": {"status": "success", "score": 4.0}}
    _worker()._run_registry_models(external, "/x.jpg", lambda *a, **k: None)

    assert "spaq" not in external  # legacy backend produces it
    assert external["liqe"] == {"status": "success", "score": 4.0}  # untouched
    assert "topiq" in external


def test_load_failure_records_not_loaded(monkeypatch):
    model = _FakeModel("topiq", {"score": 60.0, "status": "success"}, load_ok=False)
    _patch_registry(monkeypatch, [model], shadow_names=set())
    external: Dict[str, Any] = {}
    _worker()._run_registry_models(external, "/x.jpg", lambda *a, **k: None)
    assert external["topiq"]["status"] == "not_loaded"


def test_predict_exception_records_failed(monkeypatch):
    model = _FakeModel("topiq", RuntimeError("kaboom"))
    _patch_registry(monkeypatch, [model], shadow_names=set())
    external: Dict[str, Any] = {}
    _worker()._run_registry_models(external, "/x.jpg", lambda *a, **k: None)
    assert external["topiq"]["status"] == "failed"
    assert "kaboom" in external["topiq"]["error"]
