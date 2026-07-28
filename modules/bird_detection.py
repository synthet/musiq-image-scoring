"""
Bird detection (localization) using the Ultralytics YOLO model ``synthet/bird-detect-v0``.

Provides ``BirdDetector`` — a lazily-loaded YOLO detector that finds the bird in an
image and returns / crops the highest-confidence bounding box. This runs as a
preprocessing step before BioCLIP species classification (see ``modules/bird_species.py``)
so the classifier sees a tight crop of the bird rather than the whole frame.

Heavy imports (``ultralytics``, ``huggingface_hub``) are lazy so importing this module is
cheap. When they are unavailable the detector fails open (callers fall back to the whole
image), mirroring the ``open_clip`` handling in ``bird_species.py``.

Defaults mirror the canonical detector contract in the sibling model repo
`synthet/image-scoring-model <https://github.com/synthet/image-scoring-model>`_
(``src/eye_quality/localization/bird_detector.py``: weights ``bird_detect_v0.pt``,
``predict(conf=0.25, max_det=10)``, ``imgsz=640``, single class ``{0: bird}``, highest-confidence
box wins) and its ``docs/architecture/BIRD_DETECTION.md`` (crop ``pad_frac = 0.10``).

Config section ``bird_detection`` (see ``config.example.json``):
    enabled     — master toggle (default true)
    model_repo  — HuggingFace repo id (default "synthet/bird-detect-v0")
    model_file  — weight filename within the repo (default "bird_detect_v0.pt")
    local_path  — optional local .pt path; used instead of downloading when set and present.
                  Point this at the sibling checkout's ``models/bird_detect_v0.pt`` to share one
                  weights file with the model repo instead of downloading a second copy.
    confidence  — YOLO detection confidence threshold (default 0.25)
    padding     — fraction of box size to expand the crop by (default 0.10)
    imgsz       — YOLO inference image size (default 640)
    max_det     — maximum detections per image (default 10)
    device      — "auto" | "cpu" | "cuda" (default "auto")
    fail_open   — on load/inference error, fall back to whole image (default true)
"""

import logging
import os
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

_DEFAULT_MODEL_REPO = "synthet/bird-detect-v0"
_DEFAULT_MODEL_FILE = "bird_detect_v0.pt"
_DEFAULT_CONFIDENCE = 0.25
_DEFAULT_PADDING = 0.10
_DEFAULT_IMGSZ = 640
_DEFAULT_MAX_DET = 10

#: Stored in ``images.bird_bbox`` when the detector ran and found no bird, so
#: backfills and reruns can tell "no bird here" apart from "never scanned" (NULL).
#: Deliberately omits ``img_w``/``img_h`` so UI overlay checks treat it as undrawable.
BBOX_NOT_DETECTED = {"detected": False}


def select_best_box(boxes: List[dict]) -> Optional[dict]:
    """Return the highest-confidence box from a list of ``{"xyxy", "conf"}`` dicts.

    Pure helper (no ultralytics dependency) so it is unit-testable in isolation.
    ``boxes`` is a list of dicts each with keys ``xyxy`` (``(x1, y1, x2, y2)``) and
    ``conf`` (float). Returns ``None`` for an empty list.
    """
    if not boxes:
        return None
    return max(boxes, key=lambda b: b.get("conf", 0.0))


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


class BirdDetector:
    """Lazily-loaded YOLO bird detector.

    Usage:
        detector = BirdDetector()
        box = detector.detect_best_box(pil_image)   # dict or None
        crop = detector.crop_to_box(pil_image, box) # PIL.Image
    """

    def __init__(self, config: Optional[dict] = None, device: Optional[str] = None):
        if config is None:
            try:
                from modules import config as _cfg

                config = _cfg.get_config_section("bird_detection") or {}
            except Exception:  # noqa: BLE001 — config is best-effort
                config = {}

        self.enabled = bool(config.get("enabled", True))
        self.model_repo = config.get("model_repo") or _DEFAULT_MODEL_REPO
        self.model_file = config.get("model_file") or _DEFAULT_MODEL_FILE
        self.local_path = config.get("local_path") or ""
        self.confidence = float(config.get("confidence", _DEFAULT_CONFIDENCE))
        self.padding = float(config.get("padding", _DEFAULT_PADDING))
        self.imgsz = int(config.get("imgsz", _DEFAULT_IMGSZ))
        self.max_det = int(config.get("max_det", _DEFAULT_MAX_DET))
        self.fail_open = bool(config.get("fail_open", True))

        cfg_device = device or config.get("device") or "auto"
        if cfg_device == "auto":
            try:
                import torch

                cfg_device = "cuda" if torch.cuda.is_available() else "cpu"
            except Exception:  # noqa: BLE001 — torch optional at import time
                cfg_device = "cpu"
        self.device = cfg_device

        self.model = None

    def _resolve_weights_path(self) -> str:
        """Return a local path to the YOLO weights, downloading from HF if needed."""
        if self.local_path and os.path.exists(self.local_path):
            return self.local_path
        from huggingface_hub import hf_hub_download

        return hf_hub_download(repo_id=self.model_repo, filename=self.model_file)

    def load_model(self) -> None:
        """Lazily load the YOLO model. Call once before running a batch."""
        if self.model is not None:
            return
        from ultralytics import YOLO

        weights = self._resolve_weights_path()
        logger.info("Loading bird detector (%s) on %s...", weights, self.device)
        self.model = YOLO(weights)
        logger.info("Bird detector loaded.")

    def detect_best_box(self, image) -> Optional[dict]:
        """Detect birds in a PIL image; return the highest-confidence box or None.

        Returns a dict ``{"x1", "y1", "x2", "y2", "conf", "img_w", "img_h", "area_frac"}``
        with integer pixel coordinates, or ``None`` when nothing is detected.
        ``area_frac`` is the box area as a fraction of the image area (mirrors
        ``BirdBox.area_frac`` in the model repo).
        """
        self.load_model()
        results = self.model.predict(
            image,
            conf=self.confidence,
            imgsz=self.imgsz,
            max_det=self.max_det,
            verbose=False,
            device=self.device,
        )

        boxes: List[dict] = []
        for result in results:
            result_boxes = getattr(result, "boxes", None)
            if result_boxes is None:
                continue
            for box in result_boxes:
                xyxy = box.xyxy[0].tolist()
                conf = float(box.conf[0].item())
                boxes.append({"xyxy": tuple(xyxy), "conf": conf})

        best = select_best_box(boxes)
        if best is None:
            return None

        img_w, img_h = image.size
        x1, y1, x2, y2 = best["xyxy"]
        area_frac = 0.0
        if img_w and img_h:
            area_frac = abs(x2 - x1) * abs(y2 - y1) / float(img_w * img_h)
        return {
            "x1": int(round(x1)),
            "y1": int(round(y1)),
            "x2": int(round(x2)),
            "y2": int(round(y2)),
            "conf": round(best["conf"], 4),
            "img_w": int(img_w),
            "img_h": int(img_h),
            "area_frac": round(area_frac, 6),
        }

    def crop_to_box(self, image, box: dict, padding: Optional[float] = None):
        """Crop a PIL image to ``box``, expanded by ``padding`` and clamped to bounds."""
        if padding is None:
            padding = self.padding
        img_w, img_h = image.size
        x1, y1, x2, y2 = box["x1"], box["y1"], box["x2"], box["y2"]
        pad_x = int(round((x2 - x1) * padding))
        pad_y = int(round((y2 - y1) * padding))
        left = _clamp(x1 - pad_x, 0, img_w)
        top = _clamp(y1 - pad_y, 0, img_h)
        right = _clamp(x2 + pad_x, 0, img_w)
        bottom = _clamp(y2 + pad_y, 0, img_h)
        # Guard against a degenerate (zero-area) crop.
        if right <= left or bottom <= top:
            return image
        return image.crop((left, top, right, bottom))

    def detect_and_crop(self, image) -> Tuple["object", Optional[dict]]:
        """Return ``(cropped_or_original_image, box_or_None)``."""
        box = self.detect_best_box(image)
        if box is None:
            return image, None
        return self.crop_to_box(image, box), box
