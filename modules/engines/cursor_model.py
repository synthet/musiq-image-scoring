"""IScoringModel wrapper around `CursorScorer` (modules/cursor_scorer.py).

`CursorScorer.predict()` returns the dict shape we need:
    {"score": float, "subscores": {...}, "status": "success"|"failed",
     "score_range": "0.0-100.0"}

The wrapper adapts that to the `IScoringModel` contract, lazy-loads the backend,
reports score_range (0.0, 100.0), and carries the multi-dimensional rubric
through as `subscores` (stored in `scores_json` by `MultiModelHost`). It mirrors
`modules.engines.topiq_model.TopiqModelWrapper`.
"""

from __future__ import annotations

import logging
from typing import Any

from modules.engines.base import IScoringModel

logger = logging.getLogger(__name__)


class CursorModelWrapper(IScoringModel):
    """Cursor-SDK LLM-judge. Score range: 0.0 - 100.0 (shadow by default)."""

    name = "cursor"
    framework = "cursor-sdk"
    score_range = (0.0, 100.0)

    def __init__(self, scorer: Any | None = None) -> None:
        """`scorer` may be an existing `CursorScorer` (or duck-typed mock) for
        sharing across the process; if `None`, the backend is constructed lazily
        on first `load()`.
        """
        self._scorer = scorer
        self._loaded = scorer is not None and getattr(scorer, "available", False)
        if self._loaded:
            self.load_status = "loaded"
        self.version = getattr(scorer, "VERSION", None) or "cursor-judge-1"

    def load(self) -> bool:
        if self._loaded:
            return True
        if self._scorer is None:
            try:
                from modules.cursor_scorer import CursorScorer
            except Exception as exc:
                logger.error("Could not import CursorScorer: %s", exc)
                self.load_status = "failed"
                return False
            try:
                self._scorer = CursorScorer()
            except Exception as exc:
                logger.error("CursorScorer construction failed: %s", exc)
                self.load_status = "failed"
                return False
        self._loaded = bool(getattr(self._scorer, "available", False))
        self.load_status = "loaded" if self._loaded else "failed"
        return self._loaded

    def predict(self, image_path: str) -> dict[str, Any]:
        if not self._loaded or self._scorer is None:
            return {"score": None, "status": "not_loaded", "error": "Model not loaded"}
        try:
            result = self._scorer.predict(image_path)
        except Exception as exc:
            logger.error("Cursor predict raised: %s", exc)
            return {"score": None, "status": "failed", "error": str(exc)}

        if not isinstance(result, dict) or result.get("status") != "success":
            err = result.get("error") if isinstance(result, dict) else "unknown"
            return {"score": None, "status": "failed", "error": err}

        out: dict[str, Any] = {
            "score": float(result.get("score", 0.0)),
            "status": "success",
            "error": None,
        }
        subscores = result.get("subscores")
        if isinstance(subscores, dict) and subscores:
            out["subscores"] = subscores
        return out

    @property
    def scorer(self) -> Any | None:
        """Expose the underlying `CursorScorer` (for sharing or shutdown)."""
        return self._scorer


__all__ = ["CursorModelWrapper"]
