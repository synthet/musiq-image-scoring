"""IScoringModel wrapper around `ClaudeScorer` (modules/claude_scorer.py).

`ClaudeScorer.predict()` returns the dict shape we need:
    {"score": float, "subscores": {...}, "status": "success"|"failed",
     "score_range": "0.0-100.0"}

The wrapper adapts that to the `IScoringModel` contract, lazy-loads the backend,
reports score_range (0.0, 100.0), and carries the multi-dimensional rubric
through as `subscores` (stored in `scores_json` by `MultiModelHost`). It mirrors
`modules.engines.cursor_model.CursorModelWrapper`.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from modules.engines.base import IScoringModel

logger = logging.getLogger(__name__)


class ClaudeModelWrapper(IScoringModel):
    """Claude Agent SDK LLM-judge. Score range: 0.0 - 100.0 (shadow by default)."""

    name = "claude"
    framework = "claude-agent-sdk"
    score_range = (0.0, 100.0)

    def __init__(self, scorer: Optional[Any] = None) -> None:
        """`scorer` may be an existing `ClaudeScorer` (or duck-typed mock) for
        sharing across the process; if `None`, the backend is constructed lazily
        on first `load()`.
        """
        self._scorer = scorer
        self._loaded = scorer is not None and getattr(scorer, "available", False)
        if self._loaded:
            self.load_status = "loaded"
        self.version = getattr(scorer, "VERSION", None) or "claude-judge-1"

    def load(self) -> bool:
        if self._loaded:
            return True
        if self._scorer is None:
            try:
                from modules.claude_scorer import ClaudeScorer
            except Exception as exc:
                logger.error("Could not import ClaudeScorer: %s", exc)
                self.load_status = "failed"
                return False
            try:
                self._scorer = ClaudeScorer()
            except Exception as exc:
                logger.error("ClaudeScorer construction failed: %s", exc)
                self.load_status = "failed"
                return False
        self._loaded = bool(getattr(self._scorer, "available", False))
        self.load_status = "loaded" if self._loaded else "failed"
        return self._loaded

    def predict(self, image_path: str) -> Dict[str, Any]:
        if not self._loaded or self._scorer is None:
            return {"score": None, "status": "not_loaded", "error": "Model not loaded"}
        try:
            result = self._scorer.predict(image_path)
        except Exception as exc:
            logger.error("Claude predict raised: %s", exc)
            return {"score": None, "status": "failed", "error": str(exc)}

        if not isinstance(result, dict) or result.get("status") != "success":
            err = result.get("error") if isinstance(result, dict) else "unknown"
            return {"score": None, "status": "failed", "error": err}

        out: Dict[str, Any] = {
            "score": float(result.get("score", 0.0)),
            "status": "success",
            "error": None,
        }
        subscores = result.get("subscores")
        if isinstance(subscores, dict) and subscores:
            out["subscores"] = subscores
        return out

    @property
    def scorer(self) -> Optional[Any]:
        """Expose the underlying `ClaudeScorer` (for sharing or shutdown)."""
        return self._scorer


__all__ = ["ClaudeModelWrapper"]
