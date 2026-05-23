"""Unit tests for the Claude Agent SDK LLM-judge engine.

Hardware-free: no network, no claude-agent-sdk install, no API key. Uses a fake
SDK module (async `query` yielding a `ResultMessage`) and a tiny in-memory image
to exercise the sync->async bridge and rubric parsing.
"""

from __future__ import annotations

import types
from typing import Any, Dict

import pytest

from modules.claude_scorer import ClaudeScorer, parse_rubric
from modules.engines.claude_model import ClaudeModelWrapper

_GOOD = {"composition": 80, "exposure": 70, "sharpness": 90, "subject": 85, "overall": 82}
_GOOD_JSON = (
    '{"composition": 80, "exposure": 70, "sharpness": 90, '
    '"subject": 85, "overall": 82}'
)


@pytest.fixture
def sample_image(tmp_path):
    from PIL import Image

    path = tmp_path / "img.jpg"
    Image.new("RGB", (64, 48), (90, 110, 130)).save(path, "JPEG")
    return str(path)


def _fake_claude_sdk(structured=None, result=None) -> types.SimpleNamespace:
    class FakeResultMessage:
        def __init__(self, structured_output=None, result=None) -> None:
            self.structured_output = structured_output
            self.result = result

    class FakeOptions:
        def __init__(self, **kw) -> None:
            self.kw = kw

    async def fake_query(prompt, options):  # noqa: ANN001
        yield FakeResultMessage(structured_output=structured, result=result)

    return types.SimpleNamespace(
        ClaudeAgentOptions=FakeOptions,
        ResultMessage=FakeResultMessage,
        query=fake_query,
    )


# --- parse_rubric ---------------------------------------------------------

def test_parse_rubric_from_structured_dict():
    assert parse_rubric(_GOOD)["overall"] == 82.0


def test_parse_rubric_from_text():
    assert parse_rubric("rating: " + _GOOD_JSON)["sharpness"] == 90.0


def test_parse_rubric_missing_field_returns_none():
    assert parse_rubric({"composition": 1}) is None


# --- ClaudeScorer backend -------------------------------------------------

def test_scorer_disabled_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("modules.claude_scorer.config.get_secret", lambda _s: None)
    scorer = ClaudeScorer()
    assert scorer.available is False
    assert scorer.predict("/whatever.jpg")["status"] == "failed"


def test_scorer_predict_structured_output(sample_image):
    scorer = ClaudeScorer(api_key="x")
    scorer._sdk = _fake_claude_sdk(structured=_GOOD)
    scorer.available = True

    result = scorer.predict(sample_image)
    assert result["status"] == "success"
    assert result["score"] == 82.0
    assert result["subscores"] == {
        "composition": 80.0, "exposure": 70.0, "sharpness": 90.0, "subject": 85.0,
    }


def test_scorer_predict_text_fallback(sample_image):
    scorer = ClaudeScorer(api_key="x")
    scorer._sdk = _fake_claude_sdk(structured=None, result=_GOOD_JSON)
    scorer.available = True
    assert scorer.predict(sample_image)["status"] == "success"


def test_scorer_predict_unparseable(sample_image):
    scorer = ClaudeScorer(api_key="x")
    scorer._sdk = _fake_claude_sdk(structured=None, result="looks fine")
    scorer.available = True
    assert scorer.predict(sample_image)["status"] == "failed"


# --- ClaudeModelWrapper ---------------------------------------------------

class _FakeScorer:
    VERSION = "claude-judge-test"
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
    wrapper = ClaudeModelWrapper(scorer=scorer)
    assert wrapper.load() is True
    out = wrapper.predict("/x.jpg")
    assert out["status"] == "success"
    assert out["score"] == 82.0
    assert out["subscores"]["composition"] == 80


def test_wrapper_failed_status():
    wrapper = ClaudeModelWrapper(scorer=_FakeScorer({"status": "failed", "error": "boom"}))
    out = wrapper.predict("/x.jpg")
    assert out["status"] == "failed"
    assert out["error"] == "boom"


def test_wrapper_not_loaded():
    out = ClaudeModelWrapper(scorer=None).predict("/x.jpg")
    assert out["status"] == "not_loaded"
