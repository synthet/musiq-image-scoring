"""Unit tests for the Cursor-SDK LLM-judge engine.

Hardware-free: no network, no cursor-sdk install, no API key. Uses a fake SDK
module and a tiny in-memory image, plus the shared `MultiModelHost` to verify
the rubric `subscores` pass-through added in host.py.
"""

from __future__ import annotations

import types
from typing import Any, Dict

import pytest

from modules.cursor_scorer import CursorScorer, parse_rubric
from modules.engines.base import IScoringModel
from modules.engines.cursor_model import CursorModelWrapper
from modules.engines.host import MultiModelHost
from modules.engines.registry import ModelRegistry

_GOOD_JSON = (
    '{"composition": 80, "exposure": 70, "sharpness": 90, '
    '"subject": 85, "overall": 82}'
)


@pytest.fixture
def sample_image(tmp_path):
    from PIL import Image

    path = tmp_path / "img.jpg"
    Image.new("RGB", (64, 48), (120, 130, 140)).save(path, "JPEG")
    return str(path)


def _fake_cursor_sdk(text: str) -> types.SimpleNamespace:
    class FakeRun:
        def text(self) -> str:
            return text

    class FakeAgent:
        @staticmethod
        def prompt(message, options):  # noqa: ANN001
            return FakeRun()

    class FakeSDKImage:
        @staticmethod
        def from_file(path):  # noqa: ANN001
            return ("image", path)

    return types.SimpleNamespace(
        AgentOptions=lambda **kw: kw,
        LocalAgentOptions=lambda **kw: kw,
        UserMessage=lambda **kw: kw,
        SDKImage=FakeSDKImage,
        Agent=FakeAgent,
    )


# --- parse_rubric ---------------------------------------------------------

def test_parse_rubric_from_dict():
    out = parse_rubric({"composition": 1, "exposure": 2, "sharpness": 3, "subject": 4, "overall": 5})
    assert out == {"composition": 1.0, "exposure": 2.0, "sharpness": 3.0, "subject": 4.0, "overall": 5.0}


def test_parse_rubric_from_text_with_prose():
    out = parse_rubric("Here is my rating:\n" + _GOOD_JSON + "\nThanks!")
    assert out["overall"] == 82.0


def test_parse_rubric_clamps_to_range():
    out = parse_rubric({"composition": -10, "exposure": 150, "sharpness": 50, "subject": 50, "overall": 50})
    assert out["composition"] == 0.0
    assert out["exposure"] == 100.0


def test_parse_rubric_missing_field_returns_none():
    assert parse_rubric({"composition": 1, "exposure": 2, "sharpness": 3, "overall": 5}) is None


def test_parse_rubric_non_json_returns_none():
    assert parse_rubric("no json here") is None
    assert parse_rubric(None) is None


# --- CursorScorer backend -------------------------------------------------

def test_scorer_disabled_without_api_key(monkeypatch):
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    monkeypatch.setattr("modules.cursor_scorer.config.get_secret", lambda _s: None)
    scorer = CursorScorer()
    assert scorer.available is False
    assert scorer.predict("/whatever.jpg")["status"] == "failed"


def test_scorer_predict_success(sample_image):
    scorer = CursorScorer(api_key="x")  # avoids the secrets lookup
    # Inject a fake SDK and force-enable (real cursor-sdk not installed in CI).
    scorer._sdk = _fake_cursor_sdk(_GOOD_JSON)
    scorer.available = True

    result = scorer.predict(sample_image)
    assert result["status"] == "success"
    assert result["score"] == 82.0
    assert result["subscores"] == {"composition": 80.0, "exposure": 70.0, "sharpness": 90.0, "subject": 85.0}
    assert result["score_range"] == "0.0-100.0"


def test_scorer_predict_unparseable_response(sample_image):
    scorer = CursorScorer(api_key="x")
    scorer._sdk = _fake_cursor_sdk("the image looks nice")
    scorer.available = True
    assert scorer.predict(sample_image)["status"] == "failed"


# --- CursorModelWrapper ---------------------------------------------------

class _FakeScorer:
    VERSION = "cursor-judge-test"
    available = True

    def __init__(self, result: Dict[str, Any]) -> None:
        self._result = result

    def predict(self, _path: str) -> Dict[str, Any]:
        return self._result


def test_wrapper_carries_subscores():
    scorer = _FakeScorer({
        "score": 82.0,
        "subscores": {"composition": 80, "exposure": 70, "sharpness": 90, "subject": 85},
        "status": "success",
    })
    wrapper = CursorModelWrapper(scorer=scorer)
    assert wrapper.load() is True
    out = wrapper.predict("/x.jpg")
    assert out["status"] == "success"
    assert out["score"] == 82.0
    assert out["subscores"]["sharpness"] == 90


def test_wrapper_failed_status_maps_to_failed():
    wrapper = CursorModelWrapper(scorer=_FakeScorer({"status": "failed", "error": "boom"}))
    out = wrapper.predict("/x.jpg")
    assert out["status"] == "failed"
    assert out["error"] == "boom"


def test_wrapper_not_loaded():
    wrapper = CursorModelWrapper(scorer=None)
    out = wrapper.predict("/x.jpg")
    assert out["status"] == "not_loaded"


# --- host subscores pass-through -----------------------------------------

class _StubBackend:
    VERSION = "stub-1.0.0"
    gpu_available = False

    def is_raw_file(self, _p: str) -> bool:
        return False

    def preprocess_image(self, p: str, **_kw):
        return p

    def calculate_weighted_categories(self, scores: Dict[str, float]) -> Dict[str, float]:
        avg = round(sum(scores.values()) / len(scores), 4) if scores else 0.0
        return {"general": avg, "technical": avg, "aesthetic": avg}


class _RubricModel(IScoringModel):
    name = "cursor"
    framework = "cursor-sdk"
    score_range = (0.0, 100.0)

    def load(self) -> bool:
        return True

    def predict(self, _path: str) -> Dict[str, Any]:
        return {
            "score": 82.0,
            "subscores": {"composition": 80, "exposure": 70, "sharpness": 90, "subject": 85},
            "status": "success",
            "error": None,
        }


class _NoSubscoreModel(IScoringModel):
    name = "plain"
    framework = "x"
    score_range = (0.0, 100.0)

    def load(self) -> bool:
        return True

    def predict(self, _path: str) -> Dict[str, Any]:
        return {"score": 50.0, "status": "success", "error": None}


def test_host_carries_subscores_into_model_result():
    reg = ModelRegistry()
    reg.register(_RubricModel())
    reg.register(_NoSubscoreModel())
    object.__setattr__(reg, "_resolve_config", staticmethod(lambda _s: {}))
    host = MultiModelHost(backend=_StubBackend(), registry=reg)

    out = host.run_all_models("/x.jpg", logger=lambda *a, **k: None)

    assert out["models"]["cursor"]["subscores"]["sharpness"] == 90
    assert out["models"]["cursor"]["score"] == 82.0
    # Inert for models that don't return a rubric.
    assert "subscores" not in out["models"]["plain"]
