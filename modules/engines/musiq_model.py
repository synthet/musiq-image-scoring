"""IScoringModel wrappers for the MUSIQ-family TF models (SPAQ, AVA, KONIQ, ...).

Each wrapper is a thin adapter over `MultiModelMUSIQ` from
`scripts/python/run_all_musiq_models.py` — it holds a reference to a shared
backend instance (so all MUSIQ-family models share one TF session and one set
of GPU resources) and delegates `load_model` / `predict_quality` calls.

The wrappers do not replace `MultiModelMUSIQ.run_all_models()` — that lives in
`MultiModelHost` (modules/engines/host.py). Wrappers only expose per-model
load / predict / normalize so the registry can iterate them generically.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from modules.engines.base import IScoringModel

logger = logging.getLogger(__name__)


# Native score ranges, mirroring `MultiModelMUSIQ.model_ranges` so we don't
# couple to import-time TF loading. Source of truth remains the backend.
_MUSIQ_RANGES: Dict[str, Tuple[float, float]] = {
    "spaq": (0.0, 100.0),
    "ava": (1.0, 10.0),
    "koniq": (0.0, 100.0),
    "paq2piq": (0.0, 100.0),
    "vila": (0.0, 1.0),
}

# MUSIQ-family variants retired from the live registry. The ranges above are
# kept so historical `image_model_scores` rows still normalize, but these are
# no longer wired into scoring: `make_musiq_wrappers` refuses to build them and
# logs a deprecation warning if a config still requests them. `vila` was
# deprecated earlier (see docs/technical/MODELS_SUMMARY.md).
_DEPRECATED_MUSIQ: frozenset = frozenset({"koniq", "paq2piq", "vila"})


class MusiqModelWrapper(IScoringModel):
    """One scoring model from the MUSIQ family (SPAQ, AVA, KONIQ, PAQ2PIQ, VILA).

    The wrapper does not own GPU/TF state. It delegates to a shared backend
    object that exposes:
        - load_model(name: str) -> bool
        - predict_quality(image_path: str, name: str) -> Optional[float]

    `MultiModelMUSIQ` from scripts/python/run_all_musiq_models.py is the
    production backend; tests can pass any duck-typed stand-in.
    """

    framework = "tf"

    def __init__(self, name: str, backend: Any, version: str = "musiq-1") -> None:
        if name not in _MUSIQ_RANGES:
            raise ValueError(f"Unknown MUSIQ model name: {name!r}")
        self.name = name
        self.version = version
        self.score_range = _MUSIQ_RANGES[name]
        self._backend = backend
        self._loaded = False

    def load(self) -> bool:
        if self._loaded:
            return True
        try:
            ok = bool(self._backend.load_model(self.name))
        except Exception as exc:
            logger.error("MUSIQ %s load_model raised: %s", self.name, exc)
            self.load_status = "failed"
            return False
        self._loaded = ok
        self.load_status = "loaded" if ok else "failed"
        return ok

    def predict(self, image_path: str) -> Dict[str, Any]:
        if not self._loaded:
            return {"score": None, "status": "not_loaded", "error": "Model not loaded"}
        try:
            score = self._backend.predict_quality(image_path, self.name)
        except Exception as exc:
            logger.error("MUSIQ %s predict_quality raised: %s", self.name, exc)
            return {"score": None, "status": "failed", "error": str(exc)}
        if score is None:
            return {"score": None, "status": "failed", "error": "Prediction failed"}
        return {"score": float(score), "status": "success", "error": None}


def make_musiq_wrappers(backend: Any, names: Optional[list[str]] = None) -> list[MusiqModelWrapper]:
    """Build wrappers for the requested MUSIQ models, sharing one backend.

    Defaults to the production set (`spaq`, `ava`). Deprecated variants
    (`koniq`, `paq2piq`, `vila`) are skipped with a warning even if requested.
    """
    wanted = names if names is not None else ["spaq", "ava"]
    out: list[MusiqModelWrapper] = []
    for name in wanted:
        if name not in _MUSIQ_RANGES:
            logger.warning("Skipping unknown MUSIQ model %r", name)
            continue
        if name in _DEPRECATED_MUSIQ:
            logger.warning(
                "MUSIQ model %r is deprecated and no longer wired; skipping. "
                "Remove it from the scoring config.",
                name,
            )
            continue
        out.append(MusiqModelWrapper(name=name, backend=backend))
    return out


__all__ = ["MusiqModelWrapper", "make_musiq_wrappers"]
