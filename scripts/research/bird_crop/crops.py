"""PIL-level crop loading for the bird-crop study.

Wraps the production decode chain so a crop produced here is byte-for-byte what
``modules/bird_species.py`` would produce, and records the resampling ratio the
analysis needs to control for.

Decode order is not negotiable — it must match ``bird_species.py:217-240`` exactly,
because the stored box coordinates are in *that* space:

    open_image_for_ml -> .convert("RGB") -> bake_orientation -> crop

``open_image_for_ml`` neither converts nor bakes orientation itself, so skipping
either step silently misaligns the box.

Crop variants
-------------
Variant tokens must contain **no underscore**: the harness recovers
``(model_key, source, long_edge)`` from NPZ filenames with ``stem.rsplit("_", 2)``
(``input_size_eval.discover_npz_runs``), so an underscore in the source token would
be parsed as part of the model key.

===========================  ==========================================
``full``                     whole frame (baseline, no crop)
``crop``                     pad 10% — reproduces production exactly
``croppad25`` / ``croppad50``  fixed fractional padding
``cropctx10`` / ``cropctx15`` / ``cropctx20``  computed: expand until the crop's
                             long side reaches k x the model input, so nothing is
                             ever upscaled
===========================  ==========================================
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

from scripts.research.bird_crop.bbox import BirdBox, padded_box, parse_bbox

logger = logging.getLogger("bird_crop.crops")

FULL = "full"

#: ``cropctx<k*10>`` — e.g. ``cropctx15`` means k=1.5.
_CTX_RE = re.compile(r"^cropctx(\d+)$")
#: ``croppad<pct>`` — e.g. ``croppad25`` means pad=0.25.
_PAD_RE = re.compile(r"^croppad(\d+)$")


@dataclass(frozen=True)
class CropSpec:
    """A parsed crop variant."""

    token: str
    pad: float = 0.0
    ctx_k: float = 0.0

    @property
    def is_full_frame(self) -> bool:
        return self.token == FULL


def parse_variant(token: str) -> CropSpec:
    """Parse a source token into a :class:`CropSpec`.

    Raises ``ValueError`` on an unknown token so a typo fails at CLI-parse time
    rather than silently producing full-frame runs mislabelled as crops.
    """
    token = token.strip().lower()
    if token == FULL:
        return CropSpec(token=FULL)
    if token == "crop":
        return CropSpec(token=token, pad=0.10)
    if m := _PAD_RE.match(token):
        return CropSpec(token=token, pad=int(m.group(1)) / 100.0)
    if m := _CTX_RE.match(token):
        return CropSpec(token=token, pad=0.10, ctx_k=int(m.group(1)) / 10.0)
    raise ValueError(
        f"Unknown crop variant {token!r}. Expected 'full', 'crop', "
        "'croppad<pct>' (e.g. croppad25), or 'cropctx<k*10>' (e.g. cropctx15)."
    )


@dataclass
class CropResult:
    """A cropped image plus the provenance the analysis must control for."""

    image: Any
    #: Native crop long side / model input long edge. <1 means the crop had to be
    #: upscaled to reach the model input — a known IQA confound, so it is recorded
    #: rather than hidden.
    crop_scale_factor: float
    #: Crop long side / short side. >1 means MUSIQ will add black padding.
    aspect: float
    crop_w: int
    crop_h: int
    variant: str


def load_oriented(read_path: str):
    """Decode to an EXIF-oriented RGB PIL image, exactly as bird_species does."""
    from modules.thumbnails import bake_orientation, open_image_for_ml

    img = open_image_for_ml(read_path).convert("RGB")
    return bake_orientation(img, read_path)


def rescale_box(box: BirdBox, img_w: int, img_h: int) -> BirdBox:
    """Rescale a box into an actual decode of size ``img_w`` x ``img_h``.

    The stored ``img_w``/``img_h`` reflect whichever RAW decode branch won when the
    detector ran (embedded JPEG >=1000px, rawpy, or ImageMagick 2048px). A later
    decode can pick a different branch and yield a different size, so coordinates
    must be scaled by ratio rather than trusted as absolute pixels.
    """
    if img_w == box.img_w and img_h == box.img_h:
        return box
    if box.img_w <= 0 or box.img_h <= 0:
        return box
    sx, sy = img_w / box.img_w, img_h / box.img_h
    return BirdBox(
        x1=max(0, min(img_w, int(round(box.x1 * sx)))),
        y1=max(0, min(img_h, int(round(box.y1 * sy)))),
        x2=max(0, min(img_w, int(round(box.x2 * sx)))),
        y2=max(0, min(img_h, int(round(box.y2 * sy)))),
        img_w=img_w,
        img_h=img_h,
        conf=box.conf,
    )


def crop_for_variant(
    img,
    bbox_value: Any,
    spec: CropSpec,
    *,
    long_edge: Optional[int] = None,
) -> Optional[CropResult]:
    """Crop an already-oriented PIL image for *spec*.

    Returns ``None`` when there is no usable box, so callers **skip** the image
    rather than silently substituting a full frame — which would make a "crop" run
    and a "full" run cover different populations and quietly bias the comparison.
    ``full`` is the one variant that returns a result without a box.
    """
    from PIL import Image

    img_w, img_h = img.size

    if spec.is_full_frame:
        long_px = float(max(img_w, img_h))
        short_px = float(min(img_w, img_h))
        return CropResult(
            image=img,
            crop_scale_factor=(long_px / long_edge) if long_edge else 1.0,
            aspect=(long_px / short_px) if short_px else 0.0,
            crop_w=img_w,
            crop_h=img_h,
            variant=spec.token,
        )

    box = parse_bbox(bbox_value)
    if box is None:
        return None
    box = rescale_box(box, img_w, img_h)

    min_long_px = 0
    if spec.ctx_k and long_edge:
        min_long_px = int(round(spec.ctx_k * long_edge))

    left, top, right, bottom = padded_box(box, pad=spec.pad, min_long_px=min_long_px)
    cropped = img.crop((left, top, right, bottom))

    crop_w, crop_h = cropped.size
    long_px = float(max(crop_w, crop_h))
    short_px = float(min(crop_w, crop_h))
    if not isinstance(cropped, Image.Image):  # pragma: no cover - defensive
        return None

    return CropResult(
        image=cropped,
        crop_scale_factor=(long_px / long_edge) if long_edge else 1.0,
        aspect=(long_px / short_px) if short_px else 0.0,
        crop_w=crop_w,
        crop_h=crop_h,
        variant=spec.token,
    )


def resize_to_long_edge(img, long_edge: Optional[int]):
    """Downscale so ``max(w, h) <= long_edge`` (LANCZOS); never upscale.

    Matches ``clip_culling.common.load_pil_resized`` so crop and full-frame runs
    are resized identically and the only difference is the framing.
    """
    from PIL import Image

    if not long_edge or long_edge <= 0:
        return img
    w, h = img.size
    m = max(w, h)
    if m <= long_edge:
        return img
    ratio = long_edge / m
    return img.resize((max(1, int(w * ratio)), max(1, int(h * ratio))), Image.LANCZOS)


def load_variant(
    read_path: str,
    bbox_value: Any,
    variant: str,
    *,
    long_edge: Optional[int] = None,
) -> Optional[CropResult]:
    """Decode *read_path*, crop for *variant*, then resize to *long_edge*."""
    spec = parse_variant(variant)
    img = load_oriented(read_path)
    result = crop_for_variant(img, bbox_value, spec, long_edge=long_edge)
    if result is None:
        return None
    result.image = resize_to_long_edge(result.image, long_edge)
    return result
