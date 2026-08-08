"""Camera autofocus metadata: where the camera *tried* to focus.

Why this is worth reading
-------------------------
Every sharpness measure in this study is an inference from pixels. The AF area is
different in kind: it is the camera stating its intent. If the camera focused
somewhere other than the bird, the bird is probably soft — a conclusion no
image-based measure can reach on its own. That makes AF geometry an *independent*
cue, which is exactly what a cross-check needs.

Measured on this library (see ``focus_eval``): Z8 (61.1% of boxed images) and
Z6ii (24.5%) write full AF region geometry; the older D90/D300 (14.4%) write only
``FocusDistance``. On a 120-frame sample, the AF centre fell inside the detected
bird box **77.7%** of the time.

Coordinate spaces differ, and that is the whole difficulty
----------------------------------------------------------
``images.bird_bbox`` is stored in EXIF-**oriented** (display) space (``bbox.py``),
because ``modules/bird_detection.py`` bakes orientation before detecting. Nikon
writes AF coordinates in **sensor** space, relative to ``AFImageWidth/Height``.
For a rotated frame those two disagree by a 90-degree turn, so every AF box is
normalised and then rotated into display space before it is compared with a bird
box. Getting this wrong would silently destroy agreement on portrait frames.

The exiftool call is kept separate from the geometry so the geometry unit-tests
without touching a file.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from typing import Any, Iterable, Optional, Sequence

from scripts.research.bird_crop.bbox import BirdBox

logger = logging.getLogger("bird_crop.af_metadata")

#: exiftool tags that carry AF intent. ``-n`` yields numeric values, so
#: ``FocusDistance`` arrives as metres rather than the string "3.43 m".
AF_TAGS = (
    "AFAreaXPosition",
    "AFAreaYPosition",
    "AFAreaWidth",
    "AFAreaHeight",
    "AFImageWidth",
    "AFImageHeight",
    "AFAreaMode",
    "FocusDistance",
    "FocusMode",
    "Orientation",
    "ImageWidth",
    "ImageHeight",
    "Model",
)

#: Files per exiftool invocation. Process startup dominates for small batches, and
#: an unbounded argv would overflow the command line on large sweeps.
_BATCH = 200


@dataclass(frozen=True)
class AFArea:
    """An AF region as a fraction of the **display**-oriented frame, 0..1."""

    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def cx(self) -> float:
        return (self.x1 + self.x2) / 2.0

    @property
    def cy(self) -> float:
        return (self.y1 + self.y2) / 2.0


def read_af_batch(paths: Sequence[str], *, timeout: Optional[int] = None) -> dict[str, dict]:
    """Read AF tags for many files. Returns ``{source_file: {tag: value}}``.

    Batched because the study reads hundreds of RAWs and one exiftool process per
    file would dominate the runtime. Reuses the app's exiftool discovery rather
    than re-deriving the binary path.
    """
    from modules.exif_extractor import _get_exiftool_path, get_exiftool_timeout_seconds

    exiftool = _get_exiftool_path()
    if not exiftool:
        logger.error("exiftool not found in PATH; AF metadata is unavailable.")
        return {}
    if timeout is None:
        timeout = get_exiftool_timeout_seconds(write=False)

    out: dict[str, dict] = {}
    paths = list(paths)
    for start in range(0, len(paths), _BATCH):
        chunk = paths[start : start + _BATCH]
        cmd = [exiftool, "-j", "-n"] + [f"-{t}" for t in AF_TAGS] + list(chunk)
        try:
            # Scale the timeout with the batch: one budget sized for a single file
            # would abort a 200-file read that is progressing normally.
            res = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout * max(1, len(chunk) // 10)
            )
        except subprocess.TimeoutExpired:
            logger.warning("exiftool timed out on a %d-file batch; skipping it.", len(chunk))
            continue
        if not res.stdout.strip():
            logger.warning("exiftool returned nothing for a %d-file batch.", len(chunk))
            continue
        try:
            for row in json.loads(res.stdout):
                out[row.get("SourceFile", "")] = row
        except json.JSONDecodeError as exc:
            logger.warning("exiftool JSON parse failed: %s", exc)
    logger.info("Read AF metadata for %d/%d file(s).", len(out), len(paths))
    return out


def _orient_point(x: float, y: float, orientation: int) -> tuple[float, float]:
    """Map a normalised sensor-space point into display space.

    EXIF orientation semantics (1..8). Anything outside that range is treated as
    "no transform", which is the safe default: an unknown orientation should leave
    coordinates alone rather than rotate them arbitrarily.
    """
    if orientation == 2:      # mirror horizontal
        return 1.0 - x, y
    if orientation == 3:      # rotate 180
        return 1.0 - x, 1.0 - y
    if orientation == 4:      # mirror vertical
        return x, 1.0 - y
    if orientation == 5:      # transpose (mirror h + rotate 270 CW)
        return y, x
    if orientation == 6:      # rotate 90 CW
        return 1.0 - y, x
    if orientation == 7:      # transverse (mirror h + rotate 90 CW)
        return 1.0 - y, 1.0 - x
    if orientation == 8:      # rotate 270 CW
        return y, 1.0 - x
    return x, y               # 1, 0, None, or anything unrecognised


def af_box_in_display_space(meta: dict[str, Any]) -> Optional[AFArea]:
    """Normalise a camera AF region into display-oriented 0..1 coordinates.

    Returns ``None`` when the camera wrote no AF region (D90/D300 in this
    library), so callers degrade explicitly instead of inventing a box.
    """
    x = meta.get("AFAreaXPosition")
    y = meta.get("AFAreaYPosition")
    if x is None or y is None:
        return None

    # AFImageWidth/Height is the frame the AF coordinates are expressed in. One
    # Z6ii file in the sample carried AF coords without it, so fall back to the
    # EXIF frame size rather than dropping an otherwise usable row.
    fw_raw = meta.get("AFImageWidth") or meta.get("ImageWidth")
    fh_raw = meta.get("AFImageHeight") or meta.get("ImageHeight")
    if fw_raw is None or fh_raw is None:
        return None
    try:
        fw, fh = float(fw_raw), float(fh_raw)
    except (TypeError, ValueError):
        return None
    if fw <= 0 or fh <= 0:
        return None

    w = float(meta.get("AFAreaWidth") or 0.0)
    h = float(meta.get("AFAreaHeight") or 0.0)
    nx1, ny1 = float(x) / fw, float(y) / fh
    nx2, ny2 = (float(x) + w) / fw, (float(y) + h) / fh

    orientation = meta.get("Orientation")
    try:
        orientation = int(orientation) if orientation is not None else 1
    except (TypeError, ValueError):
        orientation = 1

    # Transform both corners; a rotation can swap which is min and which is max.
    ax1, ay1 = _orient_point(nx1, ny1, orientation)
    ax2, ay2 = _orient_point(nx2, ny2, orientation)
    return AFArea(
        x1=max(0.0, min(ax1, ax2)),
        y1=max(0.0, min(ay1, ay2)),
        x2=min(1.0, max(ax1, ax2)),
        y2=min(1.0, max(ay1, ay2)),
    )


def af_bird_agreement(af: Optional[AFArea], box: Optional[BirdBox]) -> Optional[dict]:
    """Compare the camera's AF region with the detected bird box.

    Both are put in normalised display space first. ``None`` when either side is
    missing — an unmeasurable pair must not be scored as a disagreement, or the
    14.4% of the library without AF geometry would masquerade as misfocus.
    """
    if af is None or box is None:
        return None

    bx1, by1 = box.x1 / box.img_w, box.y1 / box.img_h
    bx2, by2 = box.x2 / box.img_w, box.y2 / box.img_h

    inter_w = max(0.0, min(af.x2, bx2) - max(af.x1, bx1))
    inter_h = max(0.0, min(af.y2, by2) - max(af.y1, by1))
    inter = inter_w * inter_h
    area_af = max(0.0, af.x2 - af.x1) * max(0.0, af.y2 - af.y1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_af + area_b - inter

    bcx, bcy = (bx1 + bx2) / 2.0, (by1 + by2) / 2.0
    return {
        "centre_inside": bool(bx1 <= af.cx <= bx2 and by1 <= af.cy <= by2),
        "iou": round(inter / union, 6) if union > 0 else 0.0,
        "centre_distance": round(((af.cx - bcx) ** 2 + (af.cy - bcy) ** 2) ** 0.5, 6),
        "af_area_frac": round(area_af, 6),
    }


def availability(metas: Iterable[dict]) -> dict:
    """Per-camera AF coverage, so a report can state who the conclusions cover."""
    per_model: dict[str, dict[str, int]] = {}
    for m in metas:
        model = str(m.get("Model") or "?")
        row = per_model.setdefault(model, {"n": 0, "af_area": 0, "focus_distance": 0})
        row["n"] += 1
        if m.get("AFAreaXPosition") is not None:
            row["af_area"] += 1
        if m.get("FocusDistance") is not None:
            row["focus_distance"] += 1
    return dict(sorted(per_model.items(), key=lambda kv: -kv[1]["n"]))
