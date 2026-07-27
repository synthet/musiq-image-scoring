"""Persistent ARNIQA scorer (PyTorch via pyiqa).

Mirrors `modules/topiq.py` (`TopiqScorer`): a long-lived object that loads a
pyiqa ``arniqa`` metric once and scores images on demand. ARNIQA is a
no-reference, distortion-focused image-quality metric (blur, noise,
compression) whose output is normalized to roughly ``0.0 - 1.0`` (higher is
better). Source: Agnolucci et al., "ARNIQA: Learning Distortion Manifold for
Image Quality Assessment" (WACV 2024), Apache-2.0.

ARNIQA ships several dataset-specific regression heads (koniq, spaq, clive,
flive, …). The pyiqa default ``arniqa`` uses the KonIQ (in-the-wild) head,
which is the best fit for general photography; the head is configurable via
``scoring.arniqa.metric`` for the local-calibration phase.

POSTURE: ARNIQA runs in **shadow** first (``scoring.models.arniqa.shadow:
true``). Its scores are persisted to ``image_model_scores`` but excluded from
fusion until they are calibrated against the local corpus (#185, #220 phase 2).

The matching `IScoringModel` adapter is `modules.engines.arniqa_model`.
"""

from __future__ import annotations

import contextlib
import io
import logging
from typing import Any

from PIL import Image

logger = logging.getLogger(__name__)

try:
    import torch

    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

try:
    from torchvision.transforms import functional as TF
except ImportError:
    pass


class ArniqaScorer:
    """Persistent ARNIQA scorer to avoid re-loading the model per image."""

    # Default max dimension (longest edge) before downscaling; config can override.
    DEFAULT_MAX_DIM = 1024
    # Default pyiqa metric (KonIQ in-the-wild head). Override via config.
    DEFAULT_METRIC = "arniqa"
    VERSION = "arniqa-1"
    SCORE_RANGE = "0.0-1.0"

    def __init__(
        self,
        device: str = "cuda",
        max_dimension: int | None = None,
        metric_name: str | None = None,
    ) -> None:
        self.device = device
        self.available = False
        self.metric = None
        self.metric_name = metric_name or self._load_metric_name()
        self.max_dimension = (
            int(max_dimension) if max_dimension is not None else self._load_max_dimension()
        )
        # Reflect the active head in the version string so shadow rows in
        # `image_model_scores` stay traceable when the variant changes.
        if self.metric_name != self.DEFAULT_METRIC:
            self.VERSION = f"{self.metric_name}-1"

        if not TORCH_AVAILABLE:
            logger.warning("ARNIQA: PyTorch not installed. ARNIQA scoring will be unavailable.")
            return

        if self.device == "cuda" and not torch.cuda.is_available():
            logger.info("ARNIQA: CUDA not available, falling back to CPU")
            self.device = "cpu"

        try:
            import pyiqa

            # Suppress "Loading pretrained model..." output.
            with contextlib.redirect_stdout(io.StringIO()):
                self.metric = pyiqa.create_metric(self.metric_name, device=self.device)
            self.available = True
            logger.info("ARNIQA model '%s' loaded on %s", self.metric_name, self.device)
        except ImportError:
            logger.warning("ARNIQA: pyiqa not installed. Install with 'pip install pyiqa'")
        except Exception as exc:
            logger.error("ARNIQA: Failed to load model '%s': %s", self.metric_name, exc)

    def _load_metric_name(self) -> str:
        """Read the pyiqa metric/head from config (``scoring.arniqa.metric``)."""
        try:
            from modules.config import get_config_value

            v = get_config_value("scoring.arniqa.metric")
            if v:
                return str(v)
        except Exception:
            pass
        return self.DEFAULT_METRIC

    def _load_max_dimension(self) -> int:
        """Read the ARNIQA max dimension from config (``scoring.arniqa.max_dimension``)."""
        try:
            from modules.config import get_config_value

            v = get_config_value("scoring.arniqa.max_dimension")
            if v is not None:
                return max(224, min(2048, int(v)))
        except Exception:
            pass
        return self.DEFAULT_MAX_DIM

    def predict(self, image_path: str) -> dict[str, Any]:
        """Score a single image. Returns a dict with score/status/score_range."""
        if not self.available:
            return {"error": "Model not loaded", "status": "failed"}

        try:
            img = Image.open(image_path).convert("RGB")

            # Downscale very large images to bound memory/time.
            if max(img.size) > self.max_dimension:
                ratio = self.max_dimension / max(img.size)
                new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                img = img.resize(new_size, Image.BICUBIC)

            img_tensor = TF.to_tensor(img).unsqueeze(0).to(self.device)

            with torch.no_grad():
                score = self.metric(img_tensor).item()

            return {
                "score": score,
                "status": "success",
                "device": self.device,
                "score_range": self.SCORE_RANGE,
            }
        except Exception as exc:
            # Fallback: let pyiqa load the file directly if tensor prep failed.
            try:
                if self.metric is not None:
                    with torch.no_grad():
                        score = self.metric(image_path).item()
                    return {
                        "score": score,
                        "status": "success",
                        "device": self.device,
                        "note": "fallback_path",
                        "score_range": self.SCORE_RANGE,
                    }
            except Exception:
                pass

            return {"error": str(exc), "status": "failed"}


__all__ = ["ArniqaScorer"]
