"""Parse ``images.bird_bbox`` and derive geometry features.

Pure functions only — no DB, no GPU, no PIL — so this module is unit-testable in
isolation (mirroring ``modules.bird_detection.select_best_box``).

``images.bird_bbox`` is **four**-state (see ``modules/bird_detection.py``:
``BBOX_NOT_DETECTED``, ``bbox_scan_failed``):

=====================================  ===========================================
``NULL``                               never scanned
``{"detected": false}``                detector ran, found no bird
``{"detected": false, "error": ...}``  scan attempted but failed (decode/IO)
xyxy object                            highest-confidence box
=====================================  ===========================================

The last two must not be conflated: "no bird in this frame" is evidence about the
photo, whereas "we could not read the file" is evidence about the pipeline. Only
the first is usable as a signal.

The xyxy object carries **absolute pixel** coordinates in the EXIF-*oriented*
space of whatever ``open_image_for_ml`` decoded, plus the ``img_w``/``img_h`` of
that decode. Because the RAW decode chain (embedded JPEG >=1000px -> rawpy ->
ImageMagick 2048px) can pick different branches across runs, **every consumer
must normalise by ``img_w``/``img_h``** rather than assume a pixel space.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional

#: Keys a real box must carry to be usable. ``area_frac`` is optional (older rows).
_REQUIRED_KEYS = ("x1", "y1", "x2", "y2", "img_w", "img_h")

#: Normalised positions of the rule-of-thirds intersections.
_THIRDS = ((1 / 3, 1 / 3), (2 / 3, 1 / 3), (1 / 3, 2 / 3), (2 / 3, 2 / 3))


@dataclass(frozen=True)
class BirdBox:
    """A validated bird box in absolute pixels plus the frame it was measured in."""

    x1: int
    y1: int
    x2: int
    y2: int
    img_w: int
    img_h: int
    conf: float

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1

    @property
    def area_frac(self) -> float:
        """Box area as a fraction of frame area (recomputed, not trusted from JSON)."""
        denom = float(self.img_w) * float(self.img_h)
        if denom <= 0:
            return 0.0
        return (self.width * self.height) / denom


def parse_bbox(value: Any) -> Optional[BirdBox]:
    """Return a :class:`BirdBox`, or ``None`` for *any* non-box value.

    ``None`` covers all three "no usable box" cases — SQL ``NULL``, the
    ``{"detected": false}`` sentinel, and a malformed/degenerate row — because
    every caller in this study treats them identically (skip the image). Callers
    that need to distinguish "never scanned" from "no bird" should test the raw
    value before calling this.
    """
    if not isinstance(value, dict):
        return None
    if any(k not in value for k in _REQUIRED_KEYS):
        return None
    try:
        x1, y1 = int(value["x1"]), int(value["y1"])
        x2, y2 = int(value["x2"]), int(value["y2"])
        img_w, img_h = int(value["img_w"]), int(value["img_h"])
        conf = float(value.get("conf", 0.0))
    except (TypeError, ValueError):
        return None
    # Normalise inverted coordinates rather than rejecting them.
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    if img_w <= 0 or img_h <= 0 or x2 <= x1 or y2 <= y1:
        return None
    return BirdBox(x1=x1, y1=y1, x2=x2, y2=y2, img_w=img_w, img_h=img_h, conf=conf)


def is_not_detected(value: Any) -> bool:
    """True when the detector ran cleanly and found no bird.

    Excludes scan failures: an unreadable file says nothing about whether a bird
    was present, so counting it as "no bird" would corrupt any statistic built on
    detection rate.
    """
    return (
        isinstance(value, dict)
        and value.get("detected") is False
        and not value.get("error")
    )


def is_scan_failed(value: Any) -> bool:
    """True for the ``{"detected": false, "error": ...}`` sentinel (decode/IO failure)."""
    return isinstance(value, dict) and bool(value.get("error"))


def geometry_features(box: BirdBox) -> dict[str, float]:
    """Derive composition features from a box. No inference required.

    All positional features are normalised so they are comparable across the
    mixed frame sizes in the library (Z6ii 6048px vs Z8 8256px).

    ``offset_center``  distance of the box centre from the frame centre, in units
                       of half-frame (0 = dead centre, 1 = frame edge/corner-ish).
    ``offset_thirds``  distance to the *nearest* rule-of-thirds intersection, in
                       the same units. Low = conventionally well composed.
    ``edges_touched``  how many frame edges the box abuts, i.e. the bird is
                       clipped by the frame.
    """
    w, h = float(box.img_w), float(box.img_h)
    cx = (box.x1 + box.x2) / 2.0 / w
    cy = (box.y1 + box.y2) / 2.0 / h

    # Half-frame units: (cx - 0.5) spans [-0.5, 0.5], so double it.
    dx, dy = (cx - 0.5) * 2.0, (cy - 0.5) * 2.0
    offset_center = math.hypot(dx, dy)
    offset_thirds = min(
        math.hypot((cx - tx) * 2.0, (cy - ty) * 2.0) for tx, ty in _THIRDS
    )

    long_px = float(max(box.width, box.height))
    short_px = float(min(box.width, box.height))

    return {
        "area_frac": box.area_frac,
        "box_long_px": long_px,
        "box_short_px": short_px,
        # >=1 always; 1.0 = square, higher = more elongated. Matters for MUSIQ,
        # which pads to a square with black borders.
        "aspect": (long_px / short_px) if short_px > 0 else 0.0,
        "cx_frac": cx,
        "cy_frac": cy,
        "offset_center": offset_center,
        "offset_thirds": offset_thirds,
        "edges_touched": float(count_edges_touched(box)),
        "conf": box.conf,
    }


def count_edges_touched(box: BirdBox, tol_px: int = 2) -> int:
    """Number of frame edges the box abuts within *tol_px* (bird clipped by frame)."""
    return sum(
        (
            box.x1 <= tol_px,
            box.y1 <= tol_px,
            box.x2 >= box.img_w - tol_px,
            box.y2 >= box.img_h - tol_px,
        )
    )


def subject_px_at_long_edge(box: BirdBox, long_edge: int) -> float:
    """Bird long side in pixels after the *whole frame* is resized to *long_edge*.

    This is the quantity the study is about: it is what a model actually sees of
    the subject when fed a downscaled full frame.
    """
    frame_long = max(box.img_w, box.img_h)
    if frame_long <= 0:
        return 0.0
    return max(box.width, box.height) * (float(long_edge) / float(frame_long))


def padded_box(
    box: BirdBox,
    *,
    pad: float = 0.10,
    min_long_px: int = 0,
) -> tuple[int, int, int, int]:
    """Return the crop rectangle ``(left, top, right, bottom)``, clamped to frame.

    Two independent expansions, applied in order:

    ``pad``          fraction of box width/height added on each side. Mirrors
                     ``modules.bird_detection.BirdDetector.crop_to_box`` so the
                     ``pad=0.10`` variant reproduces production exactly.
    ``min_long_px``  floor on the crop's long side. Expands the window
                     symmetrically until it is met (or the frame runs out), which
                     is how the computed ``cropctx`` policy avoids ever handing a
                     model an upscaled crop: small subjects gain context, large
                     subjects are untouched.

    Clamping can still yield a crop shorter than *min_long_px* when the box sits
    against a frame edge; that is intentional — never invent pixels.
    """
    left = box.x1 - int(round(box.width * pad))
    top = box.y1 - int(round(box.height * pad))
    right = box.x2 + int(round(box.width * pad))
    bottom = box.y2 + int(round(box.height * pad))

    if min_long_px > 0:
        # Grow the shortfall symmetrically around the current centre.
        deficit_x = min_long_px - (right - left)
        if deficit_x > 0:
            grow = deficit_x // 2
            left -= grow
            right += deficit_x - grow
        deficit_y = min_long_px - (bottom - top)
        if deficit_y > 0:
            grow = deficit_y // 2
            top -= grow
            bottom += deficit_y - grow

    # Shift a window that overhangs back inside the frame before clamping, so an
    # edge-adjacent subject keeps the requested size instead of losing context.
    if right - left <= box.img_w:
        if left < 0:
            right -= left
            left = 0
        if right > box.img_w:
            left -= right - box.img_w
            right = box.img_w
    if bottom - top <= box.img_h:
        if top < 0:
            bottom -= top
            top = 0
        if bottom > box.img_h:
            top -= bottom - box.img_h
            bottom = box.img_h

    left = max(0, min(left, box.img_w))
    top = max(0, min(top, box.img_h))
    right = max(0, min(right, box.img_w))
    bottom = max(0, min(bottom, box.img_h))

    # Degenerate result (a zero-area box after clamping) -> whole frame, matching
    # crop_to_box's guard rather than raising mid-sweep.
    if right <= left or bottom <= top:
        return 0, 0, box.img_w, box.img_h
    return left, top, right, bottom
