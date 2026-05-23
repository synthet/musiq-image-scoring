"""`MultiModelHost` — registry-driven scoring engine.

Composes:
- A `ModelRegistry` of `IScoringModel` wrappers (see registry.py).
- A backend that owns model-agnostic concerns: RAW handling, image
  preprocessing, NEF metadata writes, weighted-score computation. The
  production backend is `MultiModelMUSIQ` from
  `scripts/python/run_all_musiq_models.py`; tests pass a duck-typed stub.

Produces the same output shape as `MultiModelMUSIQ.run_all_models()` so it
can be swapped in without changing `ScoringWorker`/`ResultWorker`.

Production wiring: ``modules/engines/factory.create_production_scoring_host()``
is used by ``ScoringRunner`` as the live scorer (see ``modules/scoring.py``).
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional

from modules.engines.base import IScoringEngine, IScoringModel
from modules.engines.registry import ModelRegistry, get_registry

logger = logging.getLogger(__name__)


class MultiModelHost(IScoringEngine):
    """Registry-driven host implementing `IScoringEngine`."""

    def __init__(
        self,
        backend: Any,
        registry: Optional[ModelRegistry] = None,
        version: Optional[str] = None,
    ) -> None:
        self._backend = backend
        self._registry = registry or get_registry()
        self.VERSION = version or getattr(backend, "VERSION", "host-0")

    @property
    def registry(self) -> ModelRegistry:
        return self._registry

    @property
    def backend(self) -> Any:
        return self._backend

    @property
    def model_sources(self) -> Dict[str, Any]:
        """Delegate to the MUSIQ backend for pipeline legacy-skip checks."""
        return getattr(self._backend, "model_sources", {}) or {}

    def is_raw_file(self, file_path: str) -> bool:
        return bool(self._backend.is_raw_file(file_path))

    def preprocess_image(
        self,
        file_path: str,
        output_dir: Optional[str] = None,
        resolution_override: Optional[int] = None,
    ) -> Optional[str]:
        return self._backend.preprocess_image(
            file_path,
            output_dir=output_dir,
            resolution_override=resolution_override,
        )

    def load_enabled_and_shadow(self) -> Dict[str, bool]:
        """Load every model the registry says is active. Returns {name: ok}."""
        results: Dict[str, bool] = {}
        for model in self._registry.all_active():
            try:
                ok = bool(model.load())
            except Exception as exc:
                logger.error("Model %s load() raised: %s", model.name, exc)
                ok = False
            results[model.name] = ok
        return results

    def run_all_models(
        self,
        image_path: str,
        external_scores: Optional[Dict[str, Any]] = None,
        logger: Callable[..., Any] = print,  # noqa: A002 — kept to match IScoringEngine
        write_metadata: bool = True,
    ) -> Dict[str, Any]:
        log = logger
        active = self._registry.all_active()
        is_raw = self.is_raw_file(image_path)
        processing_path = self._resolve_processing_path(image_path, is_raw, log)

        if processing_path is None:
            return self._raw_failure_result(image_path)

        results = self._init_result(image_path, is_raw, processing_path, active)
        normalized: Dict[str, float] = {}

        if external_scores:
            self._merge_external_scores(external_scores, results, normalized, log)

        for model in active:
            if model.name in results["models"]:
                continue
            self._run_one(model, processing_path, results, normalized, log)

        self._finalize_summary(results, normalized, image_path, write_metadata)
        return results

    def _resolve_processing_path(self, image_path: str, is_raw: bool, log: Callable[..., Any]) -> Optional[str]:
        if is_raw:
            log(f"RAW file detected: {image_path}")
            return self.preprocess_image(image_path)
        # Non-RAW: trust caller; PrepWorker may have preprocessed already.
        return image_path

    def _raw_failure_result(self, image_path: str) -> Dict[str, Any]:
        return {
            "version": self.VERSION,
            "image_path": self._wsl_to_windows(image_path),
            "image_name": os.path.basename(image_path),
            "device": "GPU" if getattr(self._backend, "gpu_available", False) else "CPU",
            "gpu_available": bool(getattr(self._backend, "gpu_available", False)),
            "models": {},
            "summary": {
                "total_models": 0,
                "successful_predictions": 0,
                "failed_predictions": 0,
                "average_normalized_score": None,
                "error": "RAW/Image preprocessing failed",
            },
            "raw_conversion": {
                "original_raw": image_path,
                "temp_jpeg": None,
                "conversion_success": False,
            },
        }

    def _init_result(
        self,
        image_path: str,
        is_raw: bool,
        processing_path: str,
        active: List[IScoringModel],
    ) -> Dict[str, Any]:
        gpu = bool(getattr(self._backend, "gpu_available", False))
        out: Dict[str, Any] = {
            "version": self.VERSION,
            "image_path": self._wsl_to_windows(image_path),
            "image_name": os.path.basename(image_path),
            "device": "GPU" if gpu else "CPU",
            "gpu_available": gpu,
            "models": {},
            "summary": {
                "total_models": len(active),
                "successful_predictions": 0,
                "failed_predictions": 0,
            },
        }
        if is_raw:
            out["raw_conversion"] = {
                "original_raw": image_path,
                "temp_jpeg": processing_path,
                "conversion_success": True,
            }
        return out

    def _merge_external_scores(
        self,
        external: Dict[str, Any],
        results: Dict[str, Any],
        normalized: Dict[str, float],
        log: Callable[..., Any],
    ) -> None:
        for name, payload in external.items():
            if not isinstance(payload, dict):
                continue
            results["models"][name] = dict(payload)
            is_shadow = self._registry.is_shadow(name)
            results["models"][name]["is_shadow"] = is_shadow
            if payload.get("status") != "success":
                results["summary"]["failed_predictions"] += 1
                log(f"  {name.upper()} model: FAILED (external)")
                continue
            norm = payload.get("normalized_score")
            if norm is None:
                model = self._registry.get(name)
                raw = payload.get("score")
                if model is not None and raw is not None:
                    norm = model.normalize(float(raw))
                    results["models"][name]["normalized_score"] = round(norm, 3)
                    lo, hi = model.score_range
                    results["models"][name]["score_range"] = f"{lo}-{hi}"
            if norm is not None:
                if not is_shadow:
                    normalized[name] = float(norm)
                results["summary"]["successful_predictions"] += 1
            else:
                results["summary"]["failed_predictions"] += 1

    def _run_one(
        self,
        model: IScoringModel,
        processing_path: str,
        results: Dict[str, Any],
        normalized: Dict[str, float],
        log: Callable[..., Any],
    ) -> None:
        start = time.time()
        try:
            payload = model.predict(processing_path)
        except Exception as exc:
            logger.error("Model %s.predict raised: %s", model.name, exc)
            payload = {"score": None, "status": "failed", "error": str(exc)}
        elapsed = round(time.time() - start, 3)

        is_shadow = self._registry.is_shadow(model.name)
        status = payload.get("status", "failed")
        if status == "success" and payload.get("score") is not None:
            raw = float(payload["score"])
            norm = model.normalize(raw)
            lo, hi = model.score_range
            results["models"][model.name] = {
                "score": round(raw, 2),
                "score_range": f"{lo}-{hi}",
                "normalized_score": round(norm, 3),
                "inference_time_seconds": elapsed,
                "status": "success",
                "is_shadow": is_shadow,
            }
            # Carry an optional multi-dimensional rubric (e.g. LLM-judge engines
            # like `cursor`/`claude`) through to `scores_json`. Inert for models
            # that don't return one. Only the overall `score` above is fused or
            # written to `image_model_scores`.
            subscores = payload.get("subscores")
            if isinstance(subscores, dict) and subscores:
                results["models"][model.name]["subscores"] = subscores
            if not is_shadow:
                normalized[model.name] = norm
            results["summary"]["successful_predictions"] += 1
            tag = " [shadow]" if is_shadow else ""
            log(f"  {model.name.upper()} score: {raw:.2f} (range: {lo}-{hi}) [{elapsed:.3f}s]{tag}")
        elif status == "not_loaded":
            results["models"][model.name] = {
                "score": None,
                "error": payload.get("error") or "Model not loaded",
                "status": "not_loaded",
                "is_shadow": is_shadow,
            }
            results["summary"]["failed_predictions"] += 1
            log(f"  {model.name.upper()} model: NOT LOADED")
        else:
            results["models"][model.name] = {
                "score": None,
                "error": payload.get("error") or "Prediction failed",
                "inference_time_seconds": elapsed,
                "status": "failed",
                "is_shadow": is_shadow,
            }
            results["summary"]["failed_predictions"] += 1
            log(f"  {model.name.upper()} model: FAILED [{elapsed:.3f}s]")

    def _finalize_summary(
        self,
        results: Dict[str, Any],
        normalized: Dict[str, float],
        image_path: str,
        write_metadata: bool,
    ) -> None:
        model_times = {
            name: r["inference_time_seconds"]
            for name, r in results["models"].items()
            if "inference_time_seconds" in r
        }
        if model_times:
            total = sum(model_times.values())
            results["summary"]["performance"] = {
                "total_inference_time_seconds": round(total, 3),
                "average_inference_time_seconds": round(total / len(model_times), 3),
                "model_times": model_times,
            }

        if not normalized:
            return

        weighted = self._backend.calculate_weighted_categories(normalized)
        results["summary"]["weighted_scores"] = weighted
        avg = weighted.get("general")
        results["summary"]["average_normalized_score"] = avg

        if not write_metadata or avg is None:
            return
        if not getattr(self._backend, "is_nef_file", lambda _p: False)(image_path):
            return
        try:
            rating = self._backend.score_to_rating(avg)
            label = self._backend.determine_lightroom_label(normalized)
            ok = self._backend.write_metadata_to_nef(image_path, rating, label)
            results["summary"]["nef_metadata"] = {
                "rating": rating,
                "label": label,
                "write_success": ok,
                "score_mapping": f"{avg:.3f} -> {rating}/5, {label}",
            }
        except Exception as exc:
            logger.error("NEF metadata write failed: %s", exc)

    def _wsl_to_windows(self, image_path: str) -> str:
        fn = getattr(self._backend, "wsl_to_windows_path", None)
        if callable(fn):
            try:
                return fn(image_path)
            except Exception:
                pass
        return image_path


__all__ = ["MultiModelHost"]
