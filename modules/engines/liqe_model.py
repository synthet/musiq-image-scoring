"""IScoringModel wrapper around `LiqeScorer` (modules/liqe.py).

`LiqeScorer.predict()` already returns the dict shape we need:
    {"score": float, "status": "success"|"failed", "score_range": "1.0-5.0"}

The wrapper adapts that to the `IScoringModel` contract, lazy-loads the
backend, and reports score_range (1.0, 5.0).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from modules.engines.base import IScoringModel

logger = logging.getLogger(__name__)


class LiqeModelWrapper(IScoringModel):
    """LIQE (PyTorch via pyiqa). Score range: 1.0 – 5.0."""

    name = "liqe"
    framework = "torch"
    score_range = (1.0, 5.0)

    def __init__(self, scorer: Optional[Any] = None, device: str = "cuda") -> None:
        """`scorer` may be an existing `LiqeScorer` (or duck-typed mock) for
        sharing across the process; if `None`, the backend is constructed
        lazily on first `load()`.
        """
        self._scorer = scorer
        self._device = device
        self._loaded = scorer is not None and getattr(scorer, "available", False)
        if self._loaded:
            self.load_status = "loaded"
        self.version = getattr(scorer, "VERSION", None) or "liqe-1"

    def load(self) -> bool:
        if self._loaded:
            return True
        if self._scorer is None:
            try:
                from modules.liqe import LiqeScorer
            except Exception as exc:
                logger.error("Could not import LiqeScorer: %s", exc)
                self.load_status = "failed"
                return False
            try:
                self._scorer = LiqeScorer(device=self._device)
            except Exception as exc:
                logger.error("LiqeScorer construction failed: %s", exc)
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
            logger.error("LIQE predict raised: %s", exc)
            return {"score": None, "status": "failed", "error": str(exc)}

        if not isinstance(result, dict) or result.get("status") != "success":
            err = result.get("error") if isinstance(result, dict) else "unknown"
            return {"score": None, "status": "failed", "error": err}

        return {
            "score": float(result.get("score", 0.0)),
            "status": "success",
            "error": None,
        }

    @property
    def scorer(self) -> Optional[Any]:
        """Expose the underlying `LiqeScorer` (for sharing or shutdown)."""
        return self._scorer


__all__ = ["LiqeModelWrapper"]
