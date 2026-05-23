"""Persistent QPT V2 scorer (custom PyTorch, HiViT-T backbone).

QPT V2 (Quality-aware Pre-Training V2) is a no-reference IQA/IAA model
based on masked image modeling (ACM MM 2024). Checkpoint source:
    KeiChiTse/QPT-V2 — https://github.com/KeiChiTse/QPT-V2

Unlike TOPIQ-NR and LIQE, QPT V2 is not available via pyiqa. The scorer
requires:
  1. The QPT V2 package installed:
         pip install git+https://github.com/KeiChiTse/QPT-V2
  2. The HiViT-T checkpoint placed at the path given by
     ``scoring.qpt_v2.checkpoint_path`` in config.json
     (default: ``models/qpt_v2.pth`` relative to BASE_DIR).

If either prerequisite is missing the scorer sets ``available = False`` and
logs a warning; all engine machinery (registration, shadow scoring, DB writes)
continues normally.

The matching ``IScoringModel`` adapter is ``modules.engines.qpt_v2_model``.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from PIL import Image

logger = logging.getLogger(__name__)

try:
    import torch

    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

try:
    import torchvision.transforms as T
    from torchvision.transforms import functional as TF

    TORCHVISION_AVAILABLE = True
except ImportError:
    TORCHVISION_AVAILABLE = False

# ImageNet mean/std used by most ViT-family models including HiViT-T.
_IMAGENET_MEAN = [0.485, 0.456, 0.406]
_IMAGENET_STD = [0.229, 0.224, 0.225]


class QptV2Scorer:
    """Persistent QPT V2 scorer to avoid re-loading the model per image.

    On construction the HiViT-T checkpoint is loaded from
    ``scoring.qpt_v2.checkpoint_path`` (config) or ``models/qpt_v2.pth``.
    If the qpt_v2 package or checkpoint is unavailable ``self.available``
    is ``False`` and ``predict()`` returns a ``"failed"`` status.
    """

    DEFAULT_MAX_DIM = 1024
    VERSION = "qpt-v2-1"
    SCORE_RANGE = "0.0-1.0"

    def __init__(self, device: str = "cuda", max_dimension: Optional[int] = None) -> None:
        self.device = device
        self.available = False
        self._model = None
        self._normalize_transform = None
        self.max_dimension = (
            int(max_dimension) if max_dimension is not None else self._load_max_dimension()
        )

        if not TORCH_AVAILABLE:
            logger.warning("QPT V2: PyTorch not installed. QPT V2 scoring will be unavailable.")
            return

        if not TORCHVISION_AVAILABLE:
            logger.warning(
                "QPT V2: torchvision not installed. QPT V2 scoring will be unavailable."
            )
            return

        if self.device == "cuda" and not torch.cuda.is_available():
            logger.info("QPT V2: CUDA not available, falling back to CPU")
            self.device = "cpu"

        checkpoint_path = self._load_checkpoint_path()
        if not checkpoint_path or not os.path.isfile(checkpoint_path):
            logger.warning(
                "QPT V2: checkpoint not found at '%s'. "
                "Download from https://github.com/KeiChiTse/QPT-V2 and set "
                "scoring.qpt_v2.checkpoint_path in config.json.",
                checkpoint_path or "<unset>",
            )
            return

        self._load_model(checkpoint_path)

    # ------------------------------------------------------------------
    # Config helpers
    # ------------------------------------------------------------------

    def _load_checkpoint_path(self) -> str:
        """Return checkpoint path from config or the repo-relative default."""
        try:
            from modules.config import get_config_value

            v = get_config_value("scoring.qpt_v2.checkpoint_path")
            if v:
                return str(v)
        except Exception:
            pass
        try:
            from modules.config import BASE_DIR

            return os.path.join(BASE_DIR, "models", "qpt_v2.pth")
        except Exception:
            return os.path.join(os.path.dirname(__file__), "..", "models", "qpt_v2.pth")

    def _load_max_dimension(self) -> int:
        """Read QPT V2 max dimension from config (``scoring.qpt_v2.max_dimension``)."""
        try:
            from modules.config import get_config_value

            v = get_config_value("scoring.qpt_v2.max_dimension")
            if v is not None:
                return max(224, min(2048, int(v)))
        except Exception:
            pass
        return self.DEFAULT_MAX_DIM

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def _load_model(self, checkpoint_path: str) -> None:
        """Load the HiViT-T model from *checkpoint_path*.

        Requires the qpt_v2 package:
            pip install git+https://github.com/KeiChiTse/QPT-V2

        Once the QPT V2 repository releases inference code the import path
        below (``from qpt_v2.models import build_model``) should be verified
        against the published API and updated if needed.
        """
        try:
            from qpt_v2.models import build_model  # type: ignore[import]
        except ImportError:
            logger.warning(
                "QPT V2: package not installed. "
                "Install with: pip install git+https://github.com/KeiChiTse/QPT-V2"
            )
            return

        try:
            checkpoint = torch.load(checkpoint_path, map_location=self.device)
            state_dict = checkpoint.get("model", checkpoint)
            self._model = build_model()
            self._model.load_state_dict(state_dict)
            self._model.eval()
            self._model.to(self.device)
            self._normalize_transform = T.Normalize(_IMAGENET_MEAN, _IMAGENET_STD)
            self.available = True
            logger.info("QPT V2 model loaded on %s from %s", self.device, checkpoint_path)
        except Exception as exc:
            logger.error("QPT V2: failed to load model from %s: %s", checkpoint_path, exc)

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def _preprocess(self, img: Image.Image) -> "torch.Tensor":
        """PIL image → float tensor on device, resized to ≤ max_dimension."""
        if max(img.size) > self.max_dimension:
            ratio = self.max_dimension / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Image.BICUBIC)
        tensor = TF.to_tensor(img)
        tensor = self._normalize_transform(tensor)
        return tensor.unsqueeze(0).to(self.device)

    def predict(self, image_path: str) -> Dict[str, Any]:
        """Score a single image. Returns a dict with score/status/score_range."""
        if not self.available or self._model is None:
            return {"error": "Model not loaded", "status": "failed"}

        try:
            img = Image.open(image_path).convert("RGB")
            tensor = self._preprocess(img)

            with torch.no_grad():
                output = self._model(tensor)
                # Handle both scalar tensors and 1-element batch outputs.
                score = output.squeeze().item() if output.numel() > 1 else output.item()

            return {
                "score": float(score),
                "status": "success",
                "device": self.device,
                "score_range": self.SCORE_RANGE,
            }
        except Exception as exc:
            return {"error": str(exc), "status": "failed"}


__all__ = ["QptV2Scorer"]
