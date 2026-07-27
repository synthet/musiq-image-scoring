"""Test doubles for engine interfaces — no TensorFlow / heavy ML imports."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable, Iterator
from typing import Any

from modules.engines.base import (
    IClusteringEngine,
    ILiqeScorer,
    IScoringEngine,
    ITaggingEngine,
)


class MockScoringEngine(IScoringEngine):
    """Returns valid score payloads for ResultWorker / snorm without GPU."""

    VERSION = "mock-9.9.9"

    def is_raw_file(self, file_path: str) -> bool:
        ext = os.path.splitext(file_path)[1].lower()
        return ext in {".nef", ".nrw", ".cr2", ".cr3", ".arw", ".dng"}

    def preprocess_image(
        self,
        file_path: str,
        output_dir: str | None = None,
        resolution_override: int | None = None,
    ) -> str | None:
        if not file_path or not os.path.isfile(file_path):
            return None
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            base = os.path.basename(file_path)
            dest = os.path.join(output_dir, base)
            try:
                shutil.copy2(file_path, dest)
                return dest
            except OSError:
                return file_path
        return file_path

    def run_all_models(
        self,
        image_path: str,
        external_scores: dict[str, Any] | None = None,
        logger: Callable[..., Any] = print,
        write_metadata: bool = True,
    ) -> dict[str, Any]:
        ext_scores = external_scores or {}
        models: dict[str, Any] = {}
        if "liqe" in ext_scores and isinstance(ext_scores["liqe"], dict):
            liqe = ext_scores["liqe"]
            models["liqe"] = {
                "status": "success" if liqe.get("status") != "failed" else "failed",
                "normalized_score": float(liqe.get("score", 0.5)),
            }
        else:
            models["liqe"] = {"status": "success", "normalized_score": 0.5}
        models["ava"] = {"status": "success", "normalized_score": 0.45}
        models["spaq"] = {"status": "success", "normalized_score": 0.55}
        n_ok = sum(1 for m in models.values() if m.get("status") == "success")
        return {
            "version": self.VERSION,
            "image_path": image_path.replace("\\", "/"),
            "image_name": os.path.basename(image_path),
            "device": "mock",
            "gpu_available": False,
            "models": models,
            "summary": {
                "total_models": len(models),
                "successful_predictions": n_ok,
                "failed_predictions": len(models) - n_ok,
            },
        }


class MockLiqeScorer(ILiqeScorer):
    def predict(self, image_path: str) -> dict[str, Any]:
        return {"score": 0.5, "status": "success"}


class MockTaggingEngine(ITaggingEngine):
    def __init__(self, keywords: list[str] | None = None, caption: str = ""):
        self._keywords = keywords or ["mock", "test"]
        self._caption = caption

    def predict_keywords(self, image_path: str, custom_keywords: list[str] | None = None) -> list[str]:
        if custom_keywords:
            return list(custom_keywords)[:3]
        return list(self._keywords)

    def generate_caption(self, image_path: str) -> str:
        return self._caption or "Mock caption."


class MockClusteringEngine(IClusteringEngine):
    def cluster_images(
        self,
        distance_threshold=None,
        time_gap_seconds=None,
        force_rescan=None,
        target_folder=None,
        job_id=None,
        target_image_ids=None,
        progress_log=None,
    ) -> Iterator:
        if progress_log:
            progress_log("Mock clustering: no-op")
        yield ("Mock clustering complete", 0, 0)
