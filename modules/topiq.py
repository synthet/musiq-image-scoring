"""Persistent TOPIQ-NR scorer (PyTorch via pyiqa).

Mirrors `modules/liqe.py` (`LiqeScorer`): a long-lived object that loads the
pyiqa ``topiq_nr`` metric once and scores images on demand. TOPIQ-NR is a
no-reference image-quality metric whose output is normalized to roughly
``0.0 - 1.0`` (higher is better).

The matching `IScoringModel` adapter is `modules.engines.topiq_model`.
"""

from __future__ import annotations

import contextlib
import io
import logging
from typing import Any, Dict, Optional

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


class TopiqScorer:
    """Persistent TOPIQ-NR scorer to avoid re-loading the model per image."""

    # Default max dimension (longest edge) before downscaling; config can override.
    DEFAULT_MAX_DIM = 1024
    VERSION = "topiq-nr-1"
    SCORE_RANGE = "0.0-1.0"

    def __init__(self, device: str = "cuda", max_dimension: Optional[int] = None) -> None:
        self.device = device
        self.available = False
        self.metric = None
        self.max_dimension = (
            int(max_dimension) if max_dimension is not None else self._load_max_dimension()
        )

        if not TORCH_AVAILABLE:
            logger.warning("TOPIQ: PyTorch not installed. TOPIQ-NR scoring will be unavailable.")
            return

        if self.device == "cuda" and not torch.cuda.is_available():
            logger.info("TOPIQ: CUDA not available, falling back to CPU")
            self.device = "cpu"

        try:
            import pyiqa

            # Suppress "Loading pretrained model..." output.
            with contextlib.redirect_stdout(io.StringIO()):
                self.metric = pyiqa.create_metric("topiq_nr", device=self.device)
            self.available = True
            logger.info("TOPIQ-NR model loaded on %s", self.device)
        except ImportError:
            logger.warning("TOPIQ: pyiqa not installed. Install with 'pip install pyiqa'")
        except Exception as exc:
            logger.error("TOPIQ: Failed to load model: %s", exc)

    def _load_max_dimension(self) -> int:
        """Read the TOPIQ max dimension from config (``scoring.topiq_max_dimension``)."""
        try:
            from modules.config import get_config_value

            v = get_config_value("scoring.topiq_max_dimension")
            if v is not None:
                return max(224, min(2048, int(v)))
        except Exception:
            pass
        return self.DEFAULT_MAX_DIM

    def predict(self, image_path: str) -> Dict[str, Any]:
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


__all__ = ["TopiqScorer"]
