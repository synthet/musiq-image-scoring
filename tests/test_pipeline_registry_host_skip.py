"""ScoringWorker skips legacy registry injection when scorer is MultiModelHost."""

from __future__ import annotations

import queue
import threading

from modules.engines.host import MultiModelHost
from modules.engines.registry import ModelRegistry
from modules.pipeline import ScoringWorker


class _FakeModel:
    name = "topiq"
    score_range = (0.0, 1.0)

    def load(self) -> bool:
        return True

    def predict(self, _path):
        return {"score": 0.5, "status": "success"}

    def normalize(self, raw: float) -> float:
        return raw


def test_run_registry_models_noop_for_host(monkeypatch):
    reg = ModelRegistry()
    reg.register(_FakeModel())
    backend = type("B", (), {"model_sources": {}})()
    host = MultiModelHost(backend=backend, registry=reg)
    worker = ScoringWorker(queue.Queue(), queue.Queue(), threading.Event(), host)
    external = {}
    worker._run_registry_models(external, "/x.jpg", lambda *a, **k: None)
    assert external == {}
