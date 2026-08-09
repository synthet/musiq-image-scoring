"""Student proxy engine tests (AC-8, AC-9, AC-10)."""

from __future__ import annotations

import json

import pytest

from modules.engines.host import MultiModelHost
from modules.engines.registry import ModelRegistry
from modules.engines.student_model import (
    PROXY_SPECS,
    STUDENT_NAMESPACE,
    StudentProxyWrapper,
    make_student_proxies,
)
from modules.student_scoring import ALL_VECTOR_KEYS, reset_student_service
from modules.score_normalization import DEFAULT_COMPOSITE_WEIGHTS, DEFAULT_PERCENTILE_ANCHORS


@pytest.fixture(autouse=True)
def _reset(monkeypatch, tmp_path):
    reset_student_service()
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "weights_placeholder.json").write_text("{}", encoding="utf-8")
    meta = {
        "weights_sha256": "placeholder",
        "manifest_id": "msm_engine",
        "protocol_id": "ssp_engine",
        "bundle_id": "bundle_engine",
        "fusion": DEFAULT_COMPOSITE_WEIGHTS,
        "percentile_anchors": DEFAULT_PERCENTILE_ANCHORS,
        "mock_vector": {k: 0.55 for k in ALL_VECTOR_KEYS},
        "preprocessing_fingerprint": "fp",
        "architecture": {"backbone": "convnext_tiny", "input_size": 512},
    }
    (bundle / "bundle.meta.json").write_text(json.dumps(meta), encoding="utf-8")
    monkeypatch.setenv("VEXLUM_STUDENT_BUNDLE", str(bundle))
    yield
    reset_student_service()


class _StubBackend:
    VERSION = "stub"
    gpu_available = False

    def load_model(self, name: str) -> bool:
        return True

    def predict_quality(self, _path: str, name: str):
        return 0.5

    def is_raw_file(self, _p: str) -> bool:
        return False

    def preprocess_image(self, p: str, **_kw):
        return p

    def is_nef_file(self, _p: str) -> bool:
        return False

    def calculate_weighted_categories(self, scores):
        avg = sum(scores.values()) / len(scores) if scores else 0.0
        return {"general": avg, "technical": avg, "aesthetic": avg}

    def wsl_to_windows_path(self, p: str) -> str:
        return p


def test_all_proxy_wrappers_share_one_backbone_call(tmp_path):
    from modules.student_scoring import get_student_service

    proxies = make_student_proxies()
    for p in proxies:
        assert p.load()
    img = tmp_path / "x.jpg"
    img.write_bytes(b"x")
    svc = get_student_service()
    before = svc.predict_calls
    for p in proxies:
        out = p.predict(str(img))
        assert out["status"] == "success"
    assert svc.predict_calls == before + 1


def test_proxy_names_never_equal_teacher_names():
    names = {n for n, _ in PROXY_SPECS}
    for teacher in ("spaq", "ava", "liqe", "topiq", "arniqa"):
        assert teacher not in names
        assert any(teacher in n for n in names)
    with pytest.raises(ValueError, match="teacher name"):
        StudentProxyWrapper("spaq", "spaq")


def test_shadow_proxies_are_excluded_from_host_summary_fusion():
    reg = ModelRegistry()
    proxies = make_student_proxies()
    for p in proxies:
        reg.register(p)
        assert p.load()

    cfg = {
        name: {"enabled": False, "shadow": True}
        for name, _ in PROXY_SPECS
    }
    # Also register a production stub
    from modules.engines.base import IScoringModel

    class Prod(IScoringModel):
        name = "spaq"
        framework = "tf"
        score_range = (0.0, 100.0)
        version = "t"

        def load(self):
            return True

        def predict(self, _p):
            return {"score": 50.0, "status": "success", "error": None}

    reg.register(Prod())
    cfg["spaq"] = {"enabled": True, "shadow": False}

    backend = _StubBackend()
    host = MultiModelHost(backend=backend, registry=reg)

    def _fake_resolve(_section):
        return cfg

    object.__setattr__(reg, "_resolve_config", staticmethod(_fake_resolve))
    host.load_enabled_and_shadow()
    out = host.run_all_models("/x.jpg", logger=lambda *a, **k: None)
    # Shadow student scores present
    student_keys = [k for k in out["models"] if k.startswith(STUDENT_NAMESPACE)]
    assert student_keys
    for k in student_keys:
        assert out["models"][k].get("is_shadow") is True
    # Fusion summary must not include shadow student keys as production
    weighted = out.get("weighted_scores") or out.get("summary", {}).get("weighted_scores") or {}
    assert not [k for k in weighted if k.startswith(STUDENT_NAMESPACE)]
    # Host may expose weighted via backend calculate — ensure shadow not required for avg
    assert "spaq" in out["models"]


def test_shadow_true_is_active_when_enabled_false():
    reg = ModelRegistry()
    proxies = make_student_proxies()
    for p in proxies:
        reg.register(p)
    cfg = {name: {"enabled": False, "shadow": True} for name, _ in PROXY_SPECS}
    object.__setattr__(reg, "_resolve_config", staticmethod(lambda _s: cfg))
    active = {m.name for m in reg.all_active()}
    shadow = {m.name for m in reg.shadow()}
    enabled = {m.name for m in reg.enabled()}
    assert active == {n for n, _ in PROXY_SPECS}
    assert shadow == active
    assert enabled == set()
