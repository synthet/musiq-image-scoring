"""Claude Agent SDK image-quality judge (LLM-as-judge).

Mirrors `modules/cursor_scorer.py`: a long-lived object that holds configuration
+ credentials and scores images on demand by asking Claude (vision-capable) to
rate an image against a fixed rubric. Uses the `claude-agent-sdk` Python package
with a base64 image content block and JSON-schema structured output, so the
agent makes a pure vision call with no tools (`allowed_tools=[]`) and never
touches the filesystem.

The matching `IScoringModel` adapter is `modules.engines.claude_model`.

This is a **shadow** engine: paid, network-bound, and slower than the local
metrics, so it is disabled by default (see `scoring.models.claude` in
`config.json`). `claude-agent-sdk` is an optional dependency and requires the
Claude Code CLI on PATH as its runtime; if either is missing the scorer reports
`available = False` and the pipeline simply skips it.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
import os
import tempfile
import threading
from typing import Any, Dict, List, Optional

from PIL import Image

from modules import config

logger = logging.getLogger(__name__)

# Rubric dimensions the judge must score (0-100 each), in addition to `overall`.
RUBRIC_DIMENSIONS: List[str] = ["composition", "exposure", "sharpness", "subject"]

_SYSTEM_PROMPT = (
    "You are an expert photo-quality judge. You rate images objectively and "
    "respond only with the requested structured rubric."
)

_RUBRIC_PROMPT = (
    "Rate the attached image on a 0-100 scale (higher is better) for each "
    "dimension, then give an overall 0-100 quality score.\n"
    "- composition: framing, balance, use of space\n"
    "- exposure: brightness, dynamic range, no blown highlights / crushed shadows\n"
    "- sharpness: focus accuracy and absence of motion blur on the subject\n"
    "- subject: how interesting and clear the main subject is\n"
    "- overall: your holistic quality judgement"
)

_RUBRIC_SCHEMA = {
    "type": "object",
    "properties": {
        "composition": {"type": "integer", "minimum": 0, "maximum": 100},
        "exposure": {"type": "integer", "minimum": 0, "maximum": 100},
        "sharpness": {"type": "integer", "minimum": 0, "maximum": 100},
        "subject": {"type": "integer", "minimum": 0, "maximum": 100},
        "overall": {"type": "integer", "minimum": 0, "maximum": 100},
    },
    "required": ["composition", "exposure", "sharpness", "subject", "overall"],
    "additionalProperties": False,
}


def parse_rubric(data: Any) -> Optional[Dict[str, float]]:
    """Parse a rubric out of structured output (dict) or a JSON text response.

    Returns a dict with all of ``RUBRIC_DIMENSIONS`` + ``overall`` clamped to
    ``[0, 100]``, or ``None`` if any field is missing / unparseable.
    """
    if isinstance(data, str):
        import json
        import re

        match = re.search(r"\{.*\}", data, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except (ValueError, TypeError):
            return None

    if not isinstance(data, dict):
        return None

    out: Dict[str, float] = {}
    for key in (*RUBRIC_DIMENSIONS, "overall"):
        value = data.get(key)
        if value is None:
            return None
        try:
            out[key] = max(0.0, min(100.0, float(value)))
        except (ValueError, TypeError):
            return None
    return out


class ClaudeScorer:
    """Persistent Claude Agent SDK judge to avoid re-reading config per image."""

    DEFAULT_MAX_DIM = 1024
    DEFAULT_MODEL = "claude-opus-4-7"
    DEFAULT_TIMEOUT = 90
    VERSION = "claude-judge-1"
    SCORE_RANGE = "0.0-100.0"

    def __init__(
        self,
        model: Optional[str] = None,
        max_dimension: Optional[int] = None,
        timeout_seconds: Optional[int] = None,
        api_key: Optional[str] = None,
    ) -> None:
        self.available = False
        self._sdk: Any = None
        self.model = model or config.get_config_value(
            "scoring.claude.model", default=self.DEFAULT_MODEL
        )
        self.max_dimension = (
            int(max_dimension)
            if max_dimension is not None
            else self._cfg_int("scoring.claude.max_dimension", self.DEFAULT_MAX_DIM, 224, 2048)
        )
        self.timeout_seconds = (
            int(timeout_seconds)
            if timeout_seconds is not None
            else self._cfg_int("scoring.claude.timeout_seconds", self.DEFAULT_TIMEOUT, 5, 600)
        )

        if not (api_key or self._ensure_api_key()):
            logger.warning(
                "Claude: no API key (secrets.json 'anthropic' or ANTHROPIC_API_KEY). "
                "Scoring disabled."
            )
            return
        if api_key:
            os.environ.setdefault("ANTHROPIC_API_KEY", api_key)

        try:
            import claude_agent_sdk  # type: ignore
        except Exception as exc:  # ImportError or transitive failure
            logger.warning(
                "Claude: claude-agent-sdk not installed (%s). Scoring disabled.", exc
            )
            return
        self._sdk = claude_agent_sdk
        self.available = True
        logger.info("Claude judge ready (model=%s)", self.model)

    @staticmethod
    def _cfg_int(key: str, default: int, lo: int, hi: int) -> int:
        try:
            value = config.get_config_value(key)
            if value is not None:
                return max(lo, min(hi, int(value)))
        except (ValueError, TypeError):
            pass
        return default

    @staticmethod
    def _ensure_api_key() -> Optional[str]:
        secret = config.get_secret("anthropic")
        key = secret.get("api_key") if isinstance(secret, dict) else None
        key = key or os.environ.get("ANTHROPIC_API_KEY")
        if key:
            # claude-agent-sdk reads ANTHROPIC_API_KEY from the environment.
            os.environ.setdefault("ANTHROPIC_API_KEY", key)
        return key

    def predict(self, image_path: str) -> Dict[str, Any]:
        """Score a single image. Returns score/subscores/status/score_range."""
        if not self.available:
            return {"error": "Model not loaded", "status": "failed"}

        tmp_path: Optional[str] = None
        try:
            tmp_path = self._downscale_to_temp_jpeg(image_path)
            with open(tmp_path, "rb") as fh:
                image_b64 = base64.standard_b64encode(fh.read()).decode("ascii")
            raw = self._run_query(image_b64)
            rubric = parse_rubric(raw)
            if rubric is None:
                return {"error": "Could not parse rubric from response", "status": "failed"}
            return {
                "score": rubric["overall"],
                "subscores": {k: rubric[k] for k in RUBRIC_DIMENSIONS},
                "status": "success",
                "score_range": self.SCORE_RANGE,
                "model": self.model,
            }
        except Exception as exc:
            logger.error("Claude predict failed for %s: %s", image_path, exc)
            return {"error": str(exc), "status": "failed"}
        finally:
            if tmp_path and os.path.exists(tmp_path):
                with contextlib.suppress(OSError):
                    os.remove(tmp_path)

    def _downscale_to_temp_jpeg(self, image_path: str) -> str:
        img = Image.open(image_path).convert("RGB")
        if max(img.size) > self.max_dimension:
            ratio = self.max_dimension / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Image.BICUBIC)
        fd, tmp_path = tempfile.mkstemp(suffix=".jpg", prefix="claude_judge_")
        os.close(fd)
        img.save(tmp_path, "JPEG", quality=90)
        return tmp_path

    def _run_query(self, image_b64: str) -> Any:
        """Drive the async SDK from a sync call site.

        The scoring pipeline calls `predict()` from a worker thread with no
        running event loop, so `asyncio.run` is the normal path. If we are ever
        called from inside a running loop, offload to a dedicated thread.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._score_bounded(image_b64))
        return self._run_in_thread(image_b64)

    async def _score_bounded(self, image_b64: str) -> Any:
        return await asyncio.wait_for(self._score_async(image_b64), self.timeout_seconds)

    def _run_in_thread(self, image_b64: str) -> Any:
        box: Dict[str, Any] = {}

        def runner() -> None:
            try:
                box["value"] = asyncio.run(self._score_bounded(image_b64))
            except Exception as exc:  # surfaced to caller below
                box["error"] = exc

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        thread.join(self.timeout_seconds + 30)
        if "error" in box:
            raise box["error"]
        return box.get("value")

    async def _score_async(self, image_b64: str) -> Any:
        sdk = self._sdk
        opt_kwargs: Dict[str, Any] = {
            "model": self.model,
            "system_prompt": _SYSTEM_PROMPT,
            "allowed_tools": [],
            "permission_mode": "dontAsk",
            "max_turns": 1,
        }
        # `output_format` gives schema-validated structured output; tolerate SDK
        # versions that predate the kwarg by falling back to text parsing.
        try:
            options = sdk.ClaudeAgentOptions(
                output_format={"type": "json_schema", "schema": _RUBRIC_SCHEMA},
                **opt_kwargs,
            )
        except TypeError:
            options = sdk.ClaudeAgentOptions(**opt_kwargs)

        prompt = [
            {"type": "text", "text": _RUBRIC_PROMPT},
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": image_b64,
                },
            },
        ]

        structured: Any = None
        text: Any = None
        async for message in sdk.query(prompt=prompt, options=options):
            if isinstance(message, sdk.ResultMessage):
                structured = getattr(message, "structured_output", None)
                text = getattr(message, "result", None)
        return structured if structured is not None else text


__all__ = ["ClaudeScorer", "parse_rubric", "RUBRIC_DIMENSIONS"]
