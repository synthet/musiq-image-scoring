"""Abstract engine interfaces for scoring, LIQE, tagging, and clustering."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple, Union


class IScoringModel(ABC):
    """Single scoring model (e.g. SPAQ, AVA, LIQE, QPT V2).

    Wrappers register one instance per model with `ModelRegistry`. The host
    iterates registered models per image; production vs. shadow membership is
    decided by config, not by the model itself.
    """

    name: str = ""
    version: str = "0.0.0"
    framework: str = ""
    score_range: Tuple[float, float] = (0.0, 1.0)

    @abstractmethod
    def load(self) -> bool:
        """Idempotent. Return True on success, False on failure (caller logs)."""
        ...

    @abstractmethod
    def predict(self, image_path: str) -> Dict[str, Any]:
        """Return {"score": float, "status": "success"|"failed", "error": str|None}.

        `score` is in the model's native range (`score_range`). Fusion uses
        `normalize(score)` to map into [0, 1].
        """
        ...

    def normalize(self, raw_score: float) -> float:
        """Map a raw score into [0, 1]. Default: linear over `score_range`."""
        lo, hi = self.score_range
        if hi <= lo:
            return 0.0
        return max(0.0, min(1.0, (raw_score - lo) / (hi - lo)))


class IScoringEngine(ABC):
    """MUSIQ / multi-model scorer surface used by PrepWorker, ScoringWorker, ResultWorker."""

    VERSION: str = "0.0.0"

    @abstractmethod
    def is_raw_file(self, file_path: str) -> bool:
        ...

    @abstractmethod
    def preprocess_image(
        self,
        file_path: str,
        output_dir: Optional[str] = None,
        resolution_override: Optional[int] = None,
    ) -> Optional[str]:
        ...

    @abstractmethod
    def run_all_models(
        self,
        image_path: str,
        external_scores: Optional[Dict[str, Any]] = None,
        logger: Callable[..., Any] = print,
        write_metadata: bool = True,
    ) -> Dict[str, Any]:
        ...


class ILiqeScorer(ABC):
    """LIQE-style scorer used in ScoringWorker (duck-typed: predict(path) -> dict)."""

    @abstractmethod
    def predict(self, image_path: str) -> Dict[str, Any]:
        ...


class ITaggingEngine(ABC):
    """Keyword + optional caption inference for TaggingRunner."""

    @abstractmethod
    def predict_keywords(self, image_path: str, custom_keywords: Optional[List[str]] = None) -> List[str]:
        ...

    def generate_caption(self, image_path: str) -> str:
        """Optional; default no caption."""
        return ""


class IClusteringEngine(ABC):
    """Yields progress tuples (message, current, total) like ClusteringEngine.cluster_images."""

    @abstractmethod
    def cluster_images(
        self,
        distance_threshold=None,
        time_gap_seconds=None,
        force_rescan=None,
        target_folder=None,
        job_id=None,
        target_image_ids=None,
        progress_log=None,
    ) -> Iterator[Union[str, Tuple[Any, ...]]]:
        ...
