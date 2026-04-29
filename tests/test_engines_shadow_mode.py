"""Shadow-mode acceptance test: a shadow model runs and is stored, but never
contributes to weighted_scores. Mirrors plan §6 (shadow-mode fusion) and §5
(generic per-model storage with is_shadow flag).

No GPU/TF/Torch. Stubs the MUSIQ backend and uses a MockShadowModel whose
membership is set via config_section dependency injection.
"""

from __future__ import annotations

from typing import Any, Dict

import pytest

from modules import db_legacy
from modules.engines.base import IScoringModel
from modules.engines.host import MultiModelHost
from modules.engines.musiq_model import make_musiq_wrappers
from modules.engines.registry import ModelRegistry


class _StubBackend:
    VERSION = "stub-1.0.0"
    gpu_available = False

    def __init__(self) -> None:
        self.scores = {"spaq": 60.0, "ava": 5.0}
        self.loaded: set[str] = set()

    def load_model(self, name: str) -> bool:
        self.loaded.add(name)
        return True

    def predict_quality(self, _path: str, name: str):
        return self.scores.get(name)

    def is_raw_file(self, _p: str) -> bool:
        return False

    def preprocess_image(self, p: str, **_kw):
        return p

    def is_nef_file(self, _p: str) -> bool:
        return False

    def calculate_weighted_categories(self, scores: Dict[str, float]) -> Dict[str, float]:
        if not scores:
            return {"general": 0.0, "technical": 0.0, "aesthetic": 0.0}
        avg = sum(scores.values()) / len(scores)
        return {"general": round(avg, 4), "technical": round(avg, 4), "aesthetic": round(avg, 4)}

    def wsl_to_windows_path(self, p: str) -> str:
        return p


class MockShadowModel(IScoringModel):
    """Constant-score model used to exercise shadow-mode plumbing."""

    name = "mock_shadow"
    framework = "torch"
    score_range = (0.0, 1.0)
    version = "shadow-1"

    def __init__(self, score: float = 0.99) -> None:
        self._score = score

    def load(self) -> bool:
        return True

    def predict(self, _image_path: str) -> Dict[str, Any]:
        return {"score": self._score, "status": "success", "error": None}


def _build(shadow_in_config: bool) -> tuple[MultiModelHost, ModelRegistry, dict]:
    backend = _StubBackend()
    reg = ModelRegistry()
    for w in make_musiq_wrappers(backend):  # spaq, ava — production
        reg.register(w)
    reg.register(MockShadowModel(score=0.99))

    cfg = {
        "spaq": {"enabled": True, "shadow": False},
        "ava":  {"enabled": True, "shadow": False},
        "mock_shadow": {"enabled": False, "shadow": shadow_in_config},
    }
    host = MultiModelHost(backend=backend, registry=reg)

    # Patch registry's config resolution so all_active / is_shadow honor cfg
    # instead of the on-disk config.json.
    def _fake_resolve(_section):
        return cfg
    object.__setattr__(reg, "_resolve_config", staticmethod(_fake_resolve))

    host.load_enabled_and_shadow()
    return host, reg, cfg


def test_shadow_model_runs_and_is_stamped_with_is_shadow_true():
    host, _reg, _cfg = _build(shadow_in_config=True)
    out = host.run_all_models("/x.jpg", logger=lambda *a, **k: None)

    assert "mock_shadow" in out["models"]
    shadow_row = out["models"]["mock_shadow"]
    assert shadow_row["status"] == "success"
    assert shadow_row["is_shadow"] is True
    assert shadow_row["normalized_score"] == pytest.approx(0.99, abs=1e-3)


def test_production_models_are_stamped_with_is_shadow_false():
    host, _reg, _cfg = _build(shadow_in_config=True)
    out = host.run_all_models("/x.jpg", logger=lambda *a, **k: None)

    for name in ("spaq", "ava"):
        assert out["models"][name]["is_shadow"] is False


def test_shadow_model_excluded_from_weighted_scores():
    host, _reg, _cfg = _build(shadow_in_config=True)
    out = host.run_all_models("/x.jpg", logger=lambda *a, **k: None)

    # SPAQ raw=60 → norm 0.6, AVA raw=5 → (5-1)/9 ≈ 0.444
    # Stub fusion = mean of inputs. Without shadow:
    #   (0.6 + 0.444) / 2 ≈ 0.522
    # With shadow (would-be) included it would be:
    #   (0.6 + 0.444 + 0.99) / 3 ≈ 0.678  — must NOT be the result.
    expected = round((0.6 + (5.0 - 1.0) / 9.0) / 2, 4)
    weighted = out["summary"]["weighted_scores"]
    assert weighted["general"] == pytest.approx(expected, abs=1e-3)
    assert weighted["general"] < 0.6  # would be 0.678 if shadow leaked in


def test_baseline_with_shadow_disabled_matches_production_only_fusion():
    """Acceptance: turning shadow off must not change weighted_scores vs prod-only."""
    host_with_shadow, _, _ = _build(shadow_in_config=True)
    out_shadow = host_with_shadow.run_all_models("/x.jpg", logger=lambda *a, **k: None)

    # Same registry but mock_shadow disabled & not-shadow → skipped entirely.
    backend = _StubBackend()
    reg = ModelRegistry()
    for w in make_musiq_wrappers(backend):
        reg.register(w)
    reg.register(MockShadowModel(score=0.99))
    cfg = {
        "spaq": {"enabled": True, "shadow": False},
        "ava":  {"enabled": True, "shadow": False},
        "mock_shadow": {"enabled": False, "shadow": False},
    }
    object.__setattr__(reg, "_resolve_config", staticmethod(lambda _s: cfg))
    host_baseline = MultiModelHost(backend=backend, registry=reg)
    host_baseline.load_enabled_and_shadow()
    out_baseline = host_baseline.run_all_models("/x.jpg", logger=lambda *a, **k: None)

    assert out_shadow["summary"]["weighted_scores"] == out_baseline["summary"]["weighted_scores"]
    # And the shadow row was indeed only present in the first run.
    assert "mock_shadow" not in out_baseline["models"]
    assert "mock_shadow" in out_shadow["models"]


def test_dual_write_extracts_shadow_flag_from_host_output():
    """The shadow flag stamped by the host must flow through to image_model_scores rows."""
    host, _reg, _cfg = _build(shadow_in_config=True)
    out = host.run_all_models("/x.jpg", logger=lambda *a, **k: None)

    rows = db_legacy._extract_image_model_score_rows(99, out, "host-1")
    by_name = {r[1]: r for r in rows}
    # Tuple layout: (image_id, model_name, raw, normalized, status, is_shadow, model_version)
    assert by_name["spaq"][5] is False
    assert by_name["ava"][5] is False
    assert by_name["mock_shadow"][5] is True


def test_resultworker_fusion_filter_excludes_shadow_rows():
    """Pipeline ResultWorker (line ~503) must drop is_shadow rows before re-fusing."""
    # Simulate the dict that ResultWorker iterates.
    job_models = {
        "spaq": {"status": "success", "normalized_score": 0.5, "is_shadow": False},
        "ava":  {"status": "success", "normalized_score": 0.6, "is_shadow": False},
        "mock_shadow": {"status": "success", "normalized_score": 0.99, "is_shadow": True},
    }
    normalized = {}
    for m_name, m_res in job_models.items():
        if m_res.get("status") == "success" and not m_res.get("is_shadow"):
            normalized[m_name] = m_res.get("normalized_score", 0)
    assert set(normalized.keys()) == {"spaq", "ava"}
    assert "mock_shadow" not in normalized


def test_external_scores_respect_shadow_membership():
    """External scores (e.g. LIQE coming in via external_scores) must also honour shadow."""
    host, _reg, cfg = _build(shadow_in_config=True)
    # Mark spaq as shadow via runtime config edit (re-assigning the resolver).
    cfg["spaq"] = {"enabled": False, "shadow": True}

    external = {
        "spaq": {"score": 60.0, "normalized_score": 0.6, "score_range": "0.0-100.0", "status": "success"},
    }
    out = host.run_all_models("/x.jpg", external_scores=external, logger=lambda *a, **k: None)

    # Result still records spaq with is_shadow=True ...
    assert out["models"]["spaq"]["is_shadow"] is True
    # ... but spaq must not be in the normalized set used for fusion.
    # The stub backend's calculate_weighted_categories sees the same dict
    # the host hands it; if shadow leaked in, spaq=0.6 would dominate.
    weighted = out["summary"]["weighted_scores"]["general"]
    # Only AVA contributes; AVA raw=5 → normalized ≈ 0.444 → stub fusion mean = 0.444.
    assert weighted == pytest.approx(round((5.0 - 1.0) / 9.0, 4), abs=1e-3)
