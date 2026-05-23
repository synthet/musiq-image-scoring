"""IScoringModel wrapper around ``QptV2Scorer`` (modules/qpt_v2.py).

``QptV2Scorer.predict()`` returns the dict shape we need:
    {"score": float, "status": "success"|"failed", "score_range": "0.0-1.0"}

The wrapper adapts that to the ``IScoringModel`` contract, lazy-loads the
backend, and reports score_range (0.0, 1.0). It mirrors
``modules.engines.topiq_model.TopiqModelWrapper``.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from modules.engines.base import IScoringModel

logger = logging.getLogger(__name__)


class QptV2ModelWrapper(IScoringModel):
    """QPT V2 (HiViT-T, custom PyTorch). Score range: 0.0 – 1.0."""

    name = "qpt_v2"
    framework = "torch"
    score_range = (0.0, 1.0)

    def __init__(self, scorer: Optional[Any] = None, device: str = "cuda") -> None:
        """`scorer` may be an existing ``QptV2Scorer`` (or duck-typed mock) for
        sharing across the process; if ``None``, the backend is constructed
        lazily on first ``load()``.
        """
        self._scorer = scorer
        self._device = device
        self._loaded = scorer is not None and getattr(scorer, "available", False)
        if self._loaded:
            self.load_status = "loaded"
        self.version = getattr(scorer, "VERSION", None) or "qpt-v2-1"

    def load(self) -> bool:
        if self._loaded:
            return True
        if self._scorer is None:
            try:
                from modules.qpt_v2 import QptV2Scorer
            except Exception as exc:
                logger.error("Could not import QptV2Scorer: %s", exc)
                self.load_status = "failed"
                return False
            try:
                self._scorer = QptV2Scorer(device=self._device)
            except Exception as exc:
                logger.error("QptV2Scorer construction failed: %s", exc)
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
            logger.error("QPT V2 predict raised: %s", exc)
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
        """Expose the underlying ``QptV2Scorer`` (for sharing or shutdown)."""
        return self._scorer


__all__ = ["QptV2ModelWrapper"]
