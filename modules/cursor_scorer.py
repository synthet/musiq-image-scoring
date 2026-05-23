"""Cursor-SDK image-quality judge (LLM-as-judge).

Mirrors `modules/topiq.py` / `modules/liqe.py`: a long-lived object that holds
configuration + credentials and scores images on demand. Instead of a local ML
metric, it asks a vision-capable Cursor agent to rate an image against a fixed
rubric and return JSON.

The matching `IScoringModel` adapter is `modules.engines.cursor_model`.

This is a **shadow** engine: paid, network-bound, and slower than the local
metrics, so it is disabled by default (see `scoring.models.cursor` in
`config.json`). The `cursor-sdk` package is an optional dependency, lazily
imported here; if it is missing the scorer reports `available = False` and the
pipeline simply skips it.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import tempfile
from typing import Any, Dict, List, Optional

from PIL import Image

from modules import config

logger = logging.getLogger(__name__)

# Rubric dimensions the judge must score (0-100 each), in addition to `overall`.
RUBRIC_DIMENSIONS: List[str] = ["composition", "exposure", "sharpness", "subject"]

_RUBRIC_PROMPT = (
    "You are an expert photo-quality judge. Rate the attached image on a 0-100 "
    "scale (higher is better) for each dimension, then give an overall 0-100 "
    "quality score.\n"
    "Dimensions:\n"
    "- composition: framing, balance, use of space\n"
    "- exposure: brightness, dynamic range, no blown highlights / crushed shadows\n"
    "- sharpness: focus accuracy and absence of motion blur on the subject\n"
    "- subject: how interesting and clear the main subject is\n"
    "- overall: your holistic quality judgement\n"
    "Respond with ONLY a compact JSON object and nothing else, exactly:\n"
    '{"composition": <int>, "exposure": <int>, "sharpness": <int>, '
    '"subject": <int>, "overall": <int>}'
)


def parse_rubric(text: Any) -> Optional[Dict[str, float]]:
    """Parse a rubric out of an LLM response (dict or text).

    Returns a dict with all of ``RUBRIC_DIMENSIONS`` + ``overall`` clamped to
    ``[0, 100]``, or ``None`` if any field is missing / unparseable.
    """
    if isinstance(text, dict):
        data: Any = text
    elif isinstance(text, str):
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except (ValueError, TypeError):
            return None
    else:
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


def _extract_text(run: Any) -> Any:
    """Best-effort extraction of the final assistant text from a Cursor Run.

    The Cursor SDK exposes `run.text()` for the final text and `run.wait()` for
    a structured result; we try both so the call survives minor SDK drift.
    """
    text_fn = getattr(run, "text", None)
    if callable(text_fn):
        with contextlib.suppress(Exception):
            return text_fn()
    wait_fn = getattr(run, "wait", None)
    if callable(wait_fn):
        with contextlib.suppress(Exception):
            result = wait_fn()
            return getattr(result, "result", None) or getattr(result, "text", None)
    if isinstance(run, str):
        return run
    return str(run)


class CursorScorer:
    """Persistent Cursor-SDK judge to avoid re-reading config/credentials per image."""

    DEFAULT_MAX_DIM = 1024
    DEFAULT_MODEL = "composer-2.5"
    DEFAULT_TIMEOUT = 60
    VERSION = "cursor-judge-1"
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
            "scoring.cursor.model", default=self.DEFAULT_MODEL
        )
        self.max_dimension = (
            int(max_dimension)
            if max_dimension is not None
            else self._cfg_int("scoring.cursor.max_dimension", self.DEFAULT_MAX_DIM, 224, 2048)
        )
        self.timeout_seconds = (
            int(timeout_seconds)
            if timeout_seconds is not None
            else self._cfg_int("scoring.cursor.timeout_seconds", self.DEFAULT_TIMEOUT, 5, 600)
        )

        self._api_key = api_key or self._load_api_key()
        if not self._api_key:
            logger.warning(
                "Cursor: no API key (secrets.json 'cursor' or CURSOR_API_KEY). Scoring disabled."
            )
            return
        # The SDK reads CURSOR_API_KEY from the environment for one-shot prompts.
        os.environ.setdefault("CURSOR_API_KEY", self._api_key)

        try:
            import cursor_sdk  # type: ignore
        except Exception as exc:  # ImportError or transitive failure
            logger.warning("Cursor: cursor-sdk not installed (%s). Scoring disabled.", exc)
            return
        self._sdk = cursor_sdk
        self.available = True
        logger.info("Cursor judge ready (model=%s)", self.model)

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
    def _load_api_key() -> Optional[str]:
        secret = config.get_secret("cursor")
        if isinstance(secret, dict) and secret.get("api_key"):
            return str(secret["api_key"])
        return os.environ.get("CURSOR_API_KEY")

    def predict(self, image_path: str) -> Dict[str, Any]:
        """Score a single image. Returns score/subscores/status/score_range."""
        if not self.available:
            return {"error": "Model not loaded", "status": "failed"}

        tmp_path: Optional[str] = None
        try:
            tmp_path = self._downscale_to_temp_jpeg(image_path)
            text = self._run_agent(tmp_path)
            rubric = parse_rubric(text)
            if rubric is None:
                return {"error": "Could not parse rubric JSON from response", "status": "failed"}
            return {
                "score": rubric["overall"],
                "subscores": {k: rubric[k] for k in RUBRIC_DIMENSIONS},
                "status": "success",
                "score_range": self.SCORE_RANGE,
                "model": self.model,
            }
        except Exception as exc:
            logger.error("Cursor predict failed for %s: %s", image_path, exc)
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
        fd, tmp_path = tempfile.mkstemp(suffix=".jpg", prefix="cursor_judge_")
        os.close(fd)
        img.save(tmp_path, "JPEG", quality=90)
        return tmp_path

    def _run_agent(self, image_path: str) -> Any:
        sdk = self._sdk
        # Run in a throwaway working directory so the agent has no project files
        # to touch; the prompt constrains it to a JSON-only response.
        with tempfile.TemporaryDirectory(prefix="cursor_judge_ws_") as workspace:
            options = sdk.AgentOptions(
                model=self.model,
                local=sdk.LocalAgentOptions(cwd=workspace),
            )
            run = sdk.Agent.prompt(
                sdk.UserMessage(
                    text=_RUBRIC_PROMPT,
                    images=[sdk.SDKImage.from_file(image_path)],
                ),
                options,
            )
            return _extract_text(run)


__all__ = ["CursorScorer", "parse_rubric", "RUBRIC_DIMENSIONS"]
