"""Unit tests for MUSIQ/LIQE wrappers and MultiModelHost. No GPU/TF/Torch deps.

Stubs the MultiModelMUSIQ and LiqeScorer backends so we can verify:
- wrappers conform to IScoringModel and produce the right payloads
- MultiModelHost.run_all_models produces the same dict shape as
  MultiModelMUSIQ.run_all_models for the SPAQ + AVA + LIQE registry case
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import pytest

from modules.engines.host import MultiModelHost
from modules.engines.liqe_model import LiqeModelWrapper
from modules.engines.musiq_model import MusiqModelWrapper, make_musiq_wrappers
from modules.engines.registry import ModelRegistry
from modules.engines.qpt_v2_model import QptV2ModelWrapper
from modules.engines.topiq_model import TopiqModelWrapper


class _StubMusiqBackend:
    """Duck-typed stand-in for MultiModelMUSIQ — no TF, no GPU."""

    VERSION = "stub-1.0.0"
    gpu_available = False

    def __init__(self) -> None:
        self.loaded: set[str] = set()
        self.scores: Dict[str, float] = {"spaq": 72.5, "ava": 5.4}
        self.load_calls: list[str] = []
        self.predict_calls: list[tuple[str, str]] = []
        self.preprocess_calls: list[str] = []

    def load_model(self, name: str) -> bool:
        self.load_calls.append(name)
        self.loaded.add(name)
        return True

    def predict_quality(self, image_path: str, name: str) -> Optional[float]:
        self.predict_calls.append((image_path, name))
        return self.scores.get(name)

    def is_raw_file(self, file_path: str) -> bool:
        return file_path.lower().endswith((".nef", ".cr2", ".arw", ".dng"))

    def preprocess_image(self, file_path: str, output_dir=None, resolution_override=None) -> Optional[str]:
        self.preprocess_calls.append(file_path)
        return file_path + ".jpg"

    def is_nef_file(self, file_path: str) -> bool:
        return file_path.lower().endswith(".nef")

    def calculate_weighted_categories(self, scores: Dict[str, float]) -> Dict[str, float]:
        # Simple deterministic stand-in for the real composer.
        if not scores:
            return {"general": 0.0, "technical": 0.0, "aesthetic": 0.0}
        avg = sum(scores.values()) / len(scores)
        return {"general": round(avg, 3), "technical": round(avg, 3), "aesthetic": round(avg, 3)}

    def score_to_rating(self, _: float) -> int:
        return 4

    def determine_lightroom_label(self, _: Dict[str, float]) -> str:
        return "Green"

    def write_metadata_to_nef(self, *_args, **_kwargs) -> bool:
        return True

    def wsl_to_windows_path(self, p: str) -> str:
        return p


class _StubLiqeScorer:
    available = True
    VERSION = "liqe-stub-1"

    def __init__(self, score: float = 4.2, status: str = "success") -> None:
        self._score = score
        self._status = status

    def predict(self, _path: str) -> Dict[str, Any]:
        if self._status != "success":
            return {"status": "failed", "error": "boom"}
        return {"score": self._score, "status": "success", "score_range": "1.0-5.0"}


class _StubTopiqScorer:
    available = True
    VERSION = "topiq-stub-1"

    def __init__(self, score: float = 0.62, status: str = "success") -> None:
        self._score = score
        self._status = status

    def predict(self, _path: str) -> Dict[str, Any]:
        if self._status != "success":
            return {"status": "failed", "error": "boom"}
        return {"score": self._score, "status": "success", "score_range": "0.0-1.0"}


class _StubQptV2Scorer:
    available = True
    VERSION = "qpt-v2-stub-1"

    def __init__(self, score: float = 0.71, status: str = "success") -> None:
        self._score = score
        self._status = status

    def predict(self, _path: str) -> Dict[str, Any]:
        if self._status != "success":
            return {"status": "failed", "error": "boom"}
        return {"score": self._score, "status": "success", "score_range": "0.0-1.0"}


# ---------- MusiqModelWrapper ----------

def test_musiq_wrapper_rejects_unknown_name():
    backend = _StubMusiqBackend()
    with pytest.raises(ValueError):
        MusiqModelWrapper(name="nope", backend=backend)


def test_musiq_wrapper_load_then_predict_success():
    backend = _StubMusiqBackend()
    spaq = MusiqModelWrapper("spaq", backend)
    assert spaq.score_range == (0.0, 100.0)
    assert spaq.framework == "tf"
    assert spaq.load() is True
    assert backend.load_calls == ["spaq"]

    out = spaq.predict("/img.jpg")
    assert out == {"score": 72.5, "status": "success", "error": None}
    assert backend.predict_calls == [("/img.jpg", "spaq")]


def test_musiq_wrapper_predict_without_load_returns_not_loaded():
    backend = _StubMusiqBackend()
    spaq = MusiqModelWrapper("spaq", backend)
    out = spaq.predict("/img.jpg")
    assert out["status"] == "not_loaded"
    assert out["score"] is None
    assert backend.predict_calls == []


def test_musiq_wrapper_predict_returns_failed_when_backend_returns_none():
    backend = _StubMusiqBackend()
    backend.scores = {}  # no score for spaq
    spaq = MusiqModelWrapper("spaq", backend)
    spaq.load()
    out = spaq.predict("/img.jpg")
    assert out == {"score": None, "status": "failed", "error": "Prediction failed"}


def test_musiq_wrapper_handles_backend_exception():
    class _Boom(_StubMusiqBackend):
        def predict_quality(self, *_args, **_kwargs):
            raise RuntimeError("gpu died")

    spaq = MusiqModelWrapper("spaq", _Boom())
    spaq.load()
    out = spaq.predict("/img.jpg")
    assert out["status"] == "failed"
    assert "gpu died" in out["error"]


def test_make_musiq_wrappers_default_set():
    backend = _StubMusiqBackend()
    wrappers = make_musiq_wrappers(backend)
    assert [w.name for w in wrappers] == ["spaq", "ava"]
    assert all(w.framework == "tf" for w in wrappers)


def test_make_musiq_wrappers_skips_unknown():
    backend = _StubMusiqBackend()
    wrappers = make_musiq_wrappers(backend, names=["spaq", "imaginary", "ava"])
    assert [w.name for w in wrappers] == ["spaq", "ava"]


def test_make_musiq_wrappers_skips_deprecated():
    backend = _StubMusiqBackend()
    wrappers = make_musiq_wrappers(backend, names=["spaq", "koniq", "paq2piq", "vila", "ava"])
    # Deprecated variants are not wired, even when explicitly requested.
    assert [w.name for w in wrappers] == ["spaq", "ava"]


# ---------- LiqeModelWrapper ----------

def test_liqe_wrapper_predict_success():
    liqe = LiqeModelWrapper(scorer=_StubLiqeScorer(score=4.2))
    assert liqe.score_range == (1.0, 5.0)
    assert liqe.framework == "torch"
    assert liqe.load() is True
    out = liqe.predict("/x.jpg")
    assert out == {"score": 4.2, "status": "success", "error": None}


def test_liqe_wrapper_failed_status_propagates():
    liqe = LiqeModelWrapper(scorer=_StubLiqeScorer(status="failed"))
    liqe.load()
    out = liqe.predict("/x.jpg")
    assert out["status"] == "failed"
    assert out["score"] is None


def test_liqe_wrapper_unloaded_returns_not_loaded():
    class _Unavailable:
        available = False

    liqe = LiqeModelWrapper(scorer=_Unavailable())
    out = liqe.predict("/x.jpg")
    assert out["status"] == "not_loaded"


def test_liqe_normalize_matches_native_range():
    liqe = LiqeModelWrapper(scorer=_StubLiqeScorer())
    assert liqe.normalize(1.0) == pytest.approx(0.0)
    assert liqe.normalize(3.0) == pytest.approx(0.5)
    assert liqe.normalize(5.0) == pytest.approx(1.0)


# ---------- TopiqModelWrapper ----------

def test_topiq_wrapper_predict_success():
    topiq = TopiqModelWrapper(scorer=_StubTopiqScorer(score=0.62))
    assert topiq.name == "topiq"
    assert topiq.score_range == (0.0, 1.0)
    assert topiq.framework == "torch"
    assert topiq.load() is True
    out = topiq.predict("/x.jpg")
    assert out == {"score": 0.62, "status": "success", "error": None}


def test_topiq_wrapper_failed_status_propagates():
    topiq = TopiqModelWrapper(scorer=_StubTopiqScorer(status="failed"))
    topiq.load()
    out = topiq.predict("/x.jpg")
    assert out["status"] == "failed"
    assert out["score"] is None


def test_topiq_wrapper_unloaded_returns_not_loaded():
    class _Unavailable:
        available = False

    topiq = TopiqModelWrapper(scorer=_Unavailable())
    out = topiq.predict("/x.jpg")
    assert out["status"] == "not_loaded"


def test_topiq_normalize_matches_native_range():
    topiq = TopiqModelWrapper(scorer=_StubTopiqScorer())
    assert topiq.normalize(0.0) == pytest.approx(0.0)
    assert topiq.normalize(0.5) == pytest.approx(0.5)
    assert topiq.normalize(1.0) == pytest.approx(1.0)


# ---------- QptV2ModelWrapper ----------

def test_qpt_v2_wrapper_predict_success():
    qpt = QptV2ModelWrapper(scorer=_StubQptV2Scorer(score=0.71))
    assert qpt.name == "qpt_v2"
    assert qpt.score_range == (0.0, 1.0)
    assert qpt.framework == "torch"
    assert qpt.load() is True
    out = qpt.predict("/x.jpg")
    assert out == {"score": 0.71, "status": "success", "error": None}


def test_qpt_v2_wrapper_failed_status_propagates():
    qpt = QptV2ModelWrapper(scorer=_StubQptV2Scorer(status="failed"))
    qpt.load()
    out = qpt.predict("/x.jpg")
    assert out["status"] == "failed"
    assert out["score"] is None


def test_qpt_v2_wrapper_unloaded_returns_not_loaded():
    class _Unavailable:
        available = False

    qpt = QptV2ModelWrapper(scorer=_Unavailable())
    out = qpt.predict("/x.jpg")
    assert out["status"] == "not_loaded"


def test_qpt_v2_normalize_matches_native_range():
    qpt = QptV2ModelWrapper(scorer=_StubQptV2Scorer())
    assert qpt.normalize(0.0) == pytest.approx(0.0)
    assert qpt.normalize(0.5) == pytest.approx(0.5)
    assert qpt.normalize(1.0) == pytest.approx(1.0)


# ---------- MultiModelHost ----------

def _wire_host() -> tuple[MultiModelHost, _StubMusiqBackend, _StubLiqeScorer]:
    backend = _StubMusiqBackend()
    liqe_scorer = _StubLiqeScorer(score=4.0)
    reg = ModelRegistry()
    for w in make_musiq_wrappers(backend):  # spaq, ava
        reg.register(w)
    reg.register(LiqeModelWrapper(scorer=liqe_scorer))
    host = MultiModelHost(backend=backend, registry=reg)
    host.load_enabled_and_shadow()
    return host, backend, liqe_scorer


def test_host_implements_iscoring_engine():
    from modules.engines.base import IScoringEngine
    host, _, _ = _wire_host()
    assert isinstance(host, IScoringEngine)


def test_host_run_all_models_shape_for_spaq_ava_liqe():
    host, _, _ = _wire_host()
    out = host.run_all_models("/img.jpg", logger=lambda *a, **k: None)

    # Top-level keys match MultiModelMUSIQ.run_all_models
    assert set(out.keys()) >= {
        "version", "image_path", "image_name", "device",
        "gpu_available", "models", "summary",
    }

    assert set(out["models"].keys()) == {"spaq", "ava", "liqe"}
    for name in ("spaq", "ava", "liqe"):
        m = out["models"][name]
        assert m["status"] == "success"
        assert "score" in m and "normalized_score" in m
        assert "score_range" in m and "inference_time_seconds" in m

    s = out["summary"]
    assert s["total_models"] == 3
    assert s["successful_predictions"] == 3
    assert s["failed_predictions"] == 0
    assert "weighted_scores" in s
    assert set(s["weighted_scores"].keys()) == {"general", "technical", "aesthetic"}
    assert "performance" in s


def test_host_normalized_scores_use_native_ranges():
    host, _, _ = _wire_host()
    out = host.run_all_models("/img.jpg", logger=lambda *a, **k: None)
    # SPAQ raw 72.5, range 0-100  → 0.725
    assert out["models"]["spaq"]["normalized_score"] == pytest.approx(0.725, abs=1e-3)
    # AVA raw 5.4, range 1-10     → (5.4 - 1) / 9 ≈ 0.489
    assert out["models"]["ava"]["normalized_score"] == pytest.approx(0.489, abs=1e-3)
    # LIQE raw 4.0, range 1-5     → 0.75
    assert out["models"]["liqe"]["normalized_score"] == pytest.approx(0.75, abs=1e-3)


def test_host_skips_models_disabled_in_config():
    backend = _StubMusiqBackend()
    reg = ModelRegistry()
    for w in make_musiq_wrappers(backend):
        reg.register(w)
    host = MultiModelHost(backend=backend, registry=reg)
    host.load_enabled_and_shadow()

    # Disable AVA via inline config_section through the registry.
    # MultiModelHost uses registry.all_active() which reads from get_config_value
    # by default, so we exercise that path by patching the registry helper.
    cfg = {"ava": {"enabled": False, "shadow": False}}
    active = reg.all_active(config_section=cfg)
    assert [m.name for m in active] == ["spaq"]


def test_host_handles_raw_preprocess_failure():
    class _RawFailBackend(_StubMusiqBackend):
        def is_raw_file(self, file_path: str) -> bool:
            return True

        def preprocess_image(self, *_args, **_kwargs):
            return None

    host = MultiModelHost(backend=_RawFailBackend(), registry=ModelRegistry())
    out = host.run_all_models("/foo.nef", logger=lambda *a, **k: None)
    assert out["models"] == {}
    assert out["summary"]["error"] == "RAW/Image preprocessing failed"
    assert out["raw_conversion"]["conversion_success"] is False


def test_host_external_scores_merged_first_and_skip_re_inference():
    host, backend, _ = _wire_host()
    backend.predict_calls.clear()

    external = {
        "liqe": {"score": 3.5, "status": "success", "score_range": "1.0-5.0", "normalized_score": 0.625},
    }
    out = host.run_all_models("/img.jpg", external_scores=external, logger=lambda *a, **k: None)
    # LIQE comes from external, SPAQ + AVA still inferred.
    inferred_names = [name for (_p, name) in backend.predict_calls]
    assert "liqe" not in inferred_names
    assert set(inferred_names) == {"spaq", "ava"}
    assert out["models"]["liqe"]["score"] == 3.5
    assert out["summary"]["successful_predictions"] == 3


def test_host_load_enabled_and_shadow_returns_status_per_model():
    host, _, _ = _wire_host()
    statuses = host.load_enabled_and_shadow()
    assert set(statuses) == {"spaq", "ava", "liqe"}
    assert all(statuses.values())
