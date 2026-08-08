"""Algorithmic blur / focus / noise scoring — no model, no GPU, no training.

Why this module exists
----------------------
``modules/technical_failures/classical_metrics.py`` scored blur as
``1 - laplacian_variance / 500`` on the whole frame. Two measurements from the
bird-crop study (``docs/reports/BIRD_CROP_FOCUS_MEASURES_2026-08-03.md``) show why
that cannot work:

1. **Noise masquerades as sharpness.** On a smooth (defocused) region, adding
   sigma=15 Gaussian noise moved Laplacian variance from **0.019 to 4435** — five
   orders of magnitude. A high-ISO blurred frame therefore scores as tack sharp.
2. **A fixed divisor is not a threshold.** Laplacian variance scales with subject
   texture, contrast and resolution, so ``/500`` means something different for
   every image.

This module fixes both. Noise is *estimated* and *subtracted* rather than ignored,
and the headline blur figure is a bounded perceptual metric that is a ratio, so it
carries no absolute scale to calibrate.

The algorithms, and why these ones
----------------------------------
``estimate_noise_sigma`` — **Immerkaer (1996)**. Convolves with a 3x3 mask that is
the difference of two Laplacians. That mask annihilates any intensity surface up
to quadratic, so its response is dominated by noise rather than by image content —
which is exactly the property a noise estimator needs and a plain Laplacian lacks.
O(n), one pass.

``perceptual_blur`` — **Crete et al. (2007), "The blur effect"**. Blurs the image
again and measures how much neighbour-to-neighbour variation that destroys. An
already-blurred image has little left to lose, so it scores high. Because it is a
*ratio* of variation before and after, it is bounded in [0, 1] and needs no
per-image calibration.

It is **not** inherently noise-robust, contrary to how it is often described:
measured here, grain inverts it outright (a defocused ramp at sigma=15 scored
0.1053, *below* sharp texture at 0.1139). A median pre-filter sized from the
estimated sigma restores the ordering, and past ``NOISE_HIGH`` the verdict stops
trusting sharpness altogether and says ``noisy``.

``sharpness`` — noise-corrected Laplacian variance. For a kernel ``k`` and white
noise of variance ``s^2``, the filtered variance gains exactly ``s^2 * sum(k^2)``;
for the 3x3 Laplacian that is ``20 * s^2``. Subtracting it recovers the structural
component. Unbounded, so it is used only inside ratios where scale cancels.

``focus_ratio`` — subject sharpness over background sharpness. This is the measure
a bounding box makes possible and the one that actually answers "did the camera
focus on *this*": being a ratio, it cancels the global factors (ISO, lens, light,
scene texture) that defeat absolute thresholds. Above 1 the subject is sharper
than its surroundings.

What this module does **not** claim
-----------------------------------
Phase 4 measured classical focus measures against real camera misses and found
every blur-responsive one at chance (best AUC 0.5295). So this scores *blur* and
*noise*, which are physically well-defined, and reports ``focus_ratio`` as a
relative observation. It does not claim to detect misfocus, and the verdict
thresholds below are engineering defaults, not validated cut-offs — see
``reports/bird-crop/labels/label_set.csv`` for the outstanding validation gate.
"""

from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass
from typing import Optional, Sequence

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover - cv2 ships with the app venv
    cv2 = None

logger = logging.getLogger(__name__)

#: Immerkaer's mask: the difference of two Laplacians. Annihilates intensity
#: surfaces up to quadratic, leaving noise.
_IMMERKAER = np.array([[1.0, -2.0, 1.0], [-2.0, 4.0, -2.0], [1.0, -2.0, 1.0]])

#: Sum of squared coefficients of the 3x3 Laplacian [[0,1,0],[1,-4,1],[0,1,0]].
#: White noise of variance s^2 inflates the filtered variance by exactly this
#: much, which is what makes the correction principled rather than a fudge.
_LAPLACIAN_NOISE_GAIN = 20.0

#: Cap for the **whole-frame** path only (no subject box). Blur over an entire
#: 45 MP frame is dominated by whatever happens to be in focus somewhere, so
#: paying full resolution for it buys nothing.
DEFAULT_WORK_LONG_EDGE = 1024

#: Cap for the **subject + context** path. Deliberately high so that in practice
#: nothing is resampled: measured on real files, scoring the subject at full
#: resolution raises the response to a sigma=3.0 blur from **+0.144 to +0.447**,
#: because downscaling low-passes away the very detail being measured. A bird at
#: 3-7% of an 8256 px frame yields a 480-1050 px crop, so a 3000 px context still
#: fits under this cap and runs native.
DEFAULT_SUBJECT_LONG_EDGE = 4096

#: Crete's low-pass length.
_BLUR_KERNEL = 9

#: How far to grow the subject box to sample its local background, as a multiple
#: of the box size. 1.0 means one box-width of surround on each side. The compare
#: is deliberately *local*: depth of field falls off with distance, so the far
#: corners of a frame say little about whether this subject is the focused plane.
DEFAULT_CONTEXT_PAD = 1.0

#: Noise is estimated per block and taken at a low percentile, because the mask
#: cannot annihilate step edges and busy regions would otherwise dominate.
_NOISE_BLOCK = 32
_NOISE_PERCENTILE = 10.0

#: Verdict thresholds. **Engineering defaults, not validated cut-offs.**
BLUR_SOFT = 0.55
BLUR_BLURRED = 0.72
NOISE_HIGH = 12.0
FOCUS_RATIO_SUBJECT_SOFT = 0.8


@dataclass(frozen=True)
class FocusQuality:
    """Blur, noise and focus for one image (optionally one subject within it)."""

    #: Estimated white-noise standard deviation, on the 0-255 intensity scale.
    noise_sigma: float
    #: Perceptual blur in [0, 1]; 0 is sharp, 1 is heavily blurred.
    blur: float
    #: Noise-corrected Laplacian variance. Unbounded; comparable only as a ratio.
    sharpness: float
    #: Sharpness inside the subject box, when one was supplied.
    subject_sharpness: Optional[float] = None
    #: Sharpness outside the subject box, when one was supplied.
    background_sharpness: Optional[float] = None
    #: subject / background. >1 means the subject is sharper than its surroundings.
    focus_ratio: Optional[float] = None
    #: Perceptual blur measured on the subject crop alone.
    subject_blur: Optional[float] = None
    #: Short side of the subject in the pixels actually measured. A small value
    #: means the reading rests on few pixels and deserves less weight.
    subject_px: Optional[int] = None
    #: Resampling applied before measuring; 1.0 means native resolution. Recorded
    #: because downscaling low-passes exactly the detail these metrics read, so a
    #: figure taken at 0.2 is not comparable with one taken at 1.0.
    scale_used: float = 1.0
    #: ``sharp`` | ``soft`` | ``blurred`` | ``noisy``.
    verdict: str = "sharp"

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------
def to_gray(image: np.ndarray) -> np.ndarray:
    """2-D float64 luma. Accepts grayscale, RGB or RGBA."""
    arr = np.asarray(image)
    if arr.ndim == 3:
        arr = arr[..., :3] @ np.array([0.299, 0.587, 0.114])
    elif arr.ndim != 2:
        raise ValueError(f"expected a 2-D or 3-D image, got shape {arr.shape}")
    return arr.astype(np.float64)


def _convolve(img: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    if cv2 is not None:
        return cv2.filter2D(img, -1, kernel, borderType=cv2.BORDER_REPLICATE)
    # Direct 3x3 fallback; only used if cv2 is unavailable.
    out = np.zeros_like(img)
    padded = np.pad(img, 1, mode="edge")
    for dy in range(3):
        for dx in range(3):
            out += kernel[dy, dx] * padded[dy : dy + img.shape[0], dx : dx + img.shape[1]]
    return out


def estimate_noise_sigma(
    image: np.ndarray, *, block: int = _NOISE_BLOCK, percentile: float = _NOISE_PERCENTILE
) -> float:
    """White-noise sigma by Immerkaer's method, on the 0-255 scale.

    ``sigma = sqrt(pi/2) / 6 * mean |I * M|``

    The ``sqrt(pi/2)`` converts a mean absolute response into a standard deviation
    (for a Gaussian, ``E|X| = sigma * sqrt(2/pi)``); the 6 is the mask's L2 norm,
    scaling the response back into the input's units.

    **Aggregated per block, then taken at a low percentile**, rather than averaged
    over the whole frame. Immerkaer's mask annihilates intensity surfaces up to
    quadratic, but a step edge is not such a surface, so detailed regions inflate
    the global mean badly — measured at **13.2 on a noiseless checkerboard**. Noise
    is the *floor* of local variation, so the quietest blocks carry it and busy
    ones do not. On a realistic frame (textured subject, smoother background) this
    cuts the error at sigma=0 from 2.16 to 0.00, and at sigma=10 from 11.81 to 9.45.

    The residual bias runs slightly *low*, which is the safe direction: this figure
    is subtracted from measured sharpness, and over-subtracting would erase real
    detail.
    """
    gray = to_gray(image)
    h, w = gray.shape
    if h < 3 or w < 3:
        return 0.0
    response = np.abs(_convolve(gray, _IMMERKAER))[1:-1, 1:-1]
    if response.size == 0:
        return 0.0

    scale = math.sqrt(math.pi / 2.0) / 6.0
    hh, ww = response.shape
    n_by, n_bx = hh // block, ww // block
    if n_by < 2 or n_bx < 2:
        # Too small to block up — fall back to the plain global mean.
        return float(response.mean() * scale)

    tiles = response[: n_by * block, : n_bx * block].reshape(n_by, block, n_bx, block)
    return float(np.percentile(tiles.mean(axis=(1, 3)), percentile) * scale)


def perceptual_blur(
    image: np.ndarray,
    kernel_size: int = _BLUR_KERNEL,
    *,
    noise_sigma: Optional[float] = None,
) -> float:
    """Crete et al. (2007) blur estimate in [0, 1]; higher is blurrier.

    Blur the image again and see how much neighbour variation that removes. A
    sharp image loses a lot (low score); an already-blurred one has little left
    to lose (high score). Being a ratio, it needs no per-image calibration — the
    property the old ``1 - lapvar/500`` most conspicuously lacked.

    **Noise inverts this metric, so noise is removed first.** Grain is
    high-frequency, so re-blurring destroys a great deal of it and a noisy
    *blurred* frame reads as sharp. Measured on a defocused ramp at sigma=15, the
    raw metric returned 0.1053 — *below* genuinely sharp texture at 0.1139, i.e.
    ranked backwards. A median pre-filter sized from the estimated sigma restores
    the ordering (0.1948 vs 0.1153).

    It restores the *ordering*, not the full magnitude: a heavily grained frame
    still scores well under ``BLUR_BLURRED``. That residue is why ``_verdict``
    tests noise before blur and reports ``noisy`` rather than guessing at
    sharpness it cannot measure.
    """
    gray = to_gray(image)
    if min(gray.shape) < kernel_size + 1:
        return 0.0

    if noise_sigma is None:
        noise_sigma = estimate_noise_sigma(gray)
    gray = _denoise_for_blur(gray, noise_sigma)

    ker = np.ones(kernel_size, dtype=np.float64) / kernel_size
    blurred_h = _apply_1d(gray, ker, axis=1)
    blurred_v = _apply_1d(gray, ker, axis=0)

    scores = []
    for axis, blurred in ((1, blurred_h), (0, blurred_v)):
        d_orig = np.abs(np.diff(gray, axis=axis))
        d_blur = np.abs(np.diff(blurred, axis=axis))
        # Variation the extra blur destroyed. Negative means the second blur
        # *increased* local variation, which is noise, not structure — clamp it.
        lost = np.maximum(0.0, d_orig - d_blur)
        total = float(d_orig.sum())
        if total <= 0.0:
            continue
        scores.append((total - float(lost.sum())) / total)

    if not scores:
        # A perfectly flat patch has no variation to lose. That is not "sharp";
        # it carries no evidence either way, so report the neutral maximum rather
        # than 0.0, which would read as tack sharp.
        return 1.0
    return float(min(1.0, max(0.0, max(scores))))


def _denoise_for_blur(gray: np.ndarray, noise_sigma: float) -> np.ndarray:
    """Median pre-filter sized from the estimated noise, or a pass-through.

    Median rather than Gaussian: it suppresses grain while leaving edges standing,
    and blurring the image before a blur metric would be self-defeating. Skipped
    entirely below sigma 1, where there is nothing to remove and filtering would
    only cost detail.
    """
    if noise_sigma < 1.0 or cv2 is None:
        return gray
    ksize = 3 if noise_sigma < 8.0 else 5
    smoothed = cv2.medianBlur(np.clip(gray, 0, 255).astype(np.uint8), ksize)
    return smoothed.astype(np.float64)


def _apply_1d(img: np.ndarray, kernel: np.ndarray, *, axis: int) -> np.ndarray:
    """Separable 1-D convolution along one axis, edges replicated."""
    if cv2 is not None:
        k = kernel.reshape(1, -1) if axis == 1 else kernel.reshape(-1, 1)
        return cv2.filter2D(img, -1, k, borderType=cv2.BORDER_REPLICATE)
    pad = len(kernel) // 2
    width = [(0, 0), (0, 0)]
    width[axis] = (pad, pad)
    padded = np.pad(img, width, mode="edge")
    out = np.zeros_like(img)
    for i, coeff in enumerate(kernel):
        sl = [slice(None), slice(None)]
        sl[axis] = slice(i, i + img.shape[axis])
        out += coeff * padded[tuple(sl)]
    return out


def laplacian_variance(image: np.ndarray) -> float:
    """Raw variance of the 3x3 Laplacian. Noise-inflated; see ``sharpness``."""
    gray = to_gray(image)
    if gray.size < 9:
        return 0.0
    if cv2 is not None:
        lap = cv2.Laplacian(gray, cv2.CV_64F)
    else:
        lap = _convolve(gray, np.array([[0.0, 1, 0], [1, -4, 1], [0, 1, 0]]))
    return float(np.var(lap))


def sharpness(image: np.ndarray, noise_sigma: Optional[float] = None) -> float:
    """Laplacian variance with the noise contribution removed.

    White noise of variance ``s^2`` inflates the Laplacian-filtered variance by
    exactly ``20 * s^2`` for the 3x3 kernel, so subtracting that recovers the
    structural part. Without this step a noisy defocused region outscores a clean
    sharp one — measured at 0.019 vs 4435 on a smooth ramp.
    """
    gray = to_gray(image)
    if noise_sigma is None:
        noise_sigma = estimate_noise_sigma(gray)
    return max(0.0, laplacian_variance(gray) - _LAPLACIAN_NOISE_GAIN * noise_sigma**2)


# ---------------------------------------------------------------------------
# Composite
# ---------------------------------------------------------------------------
def _resize_long_edge(gray: np.ndarray, long_edge: int) -> np.ndarray:
    h, w = gray.shape
    longest = max(h, w)
    if long_edge <= 0 or longest <= long_edge or cv2 is None:
        return gray
    scale = long_edge / longest
    return cv2.resize(
        gray, (max(1, round(w * scale)), max(1, round(h * scale))), interpolation=cv2.INTER_AREA
    )


def _clip_box(box: Sequence[float], w: int, h: int) -> Optional[tuple[int, int, int, int]]:
    x1, y1, x2, y2 = (int(round(v)) for v in box[:4])
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    if x2 - x1 < 8 or y2 - y1 < 8:
        return None
    return x1, y1, x2, y2


def analyze(
    image: np.ndarray,
    *,
    box: Optional[Sequence[float]] = None,
    work_long_edge: int = DEFAULT_WORK_LONG_EDGE,
    subject_long_edge: int = DEFAULT_SUBJECT_LONG_EDGE,
    context_pad: float = DEFAULT_CONTEXT_PAD,
) -> FocusQuality:
    """Score blur, noise and (given a box) subject focus for one image.

    ``box`` is ``(x1, y1, x2, y2)`` in the pixel space of *image*.

    **With a box, the subject is measured at native resolution.** Downscaling is a
    low-pass filter, so resizing the frame first and cropping afterwards would
    destroy the very high-frequency detail that separates a sharp bird from a soft
    one — and would average away the sensor noise too. On a 45 MP frame a bird
    occupying 11% of it survives as roughly 110 px at long-edge 1024, which is far
    too little to judge. Same reasoning as
    ``bird_species._resolve_inference_path`` and ``build_label_set``, which both
    decode the original rather than a thumbnail.

    The background arm is a **context ring** at that same native scale — a box
    grown by ``context_pad``, minus the subject — rather than the whole frame.
    Two reasons: ``focus_ratio`` is only meaningful if both arms share a pixel
    scale, and the *local* surround is the right comparison anyway, since
    depth-of-field falls off with distance from the subject.

    Without a box, only global figures are produced, and those may be computed on
    a frame downscaled to ``work_long_edge`` for cost.
    """
    gray_full = to_gray(image)
    if gray_full.size == 0:
        return FocusQuality(noise_sigma=0.0, blur=1.0, sharpness=0.0, verdict="blurred")

    subject_metrics = None
    if box is not None:
        # The subject path gets its own, far higher cap: this is the measurement
        # that must not be resampled.
        subject_metrics = _analyze_subject(
            gray_full, box, context_pad, subject_long_edge
        )

    if subject_metrics is not None:
        return subject_metrics

    gray = _resize_long_edge(gray_full, work_long_edge)
    noise = estimate_noise_sigma(gray)
    blur = perceptual_blur(gray, noise_sigma=noise)
    return FocusQuality(
        noise_sigma=round(noise, 4),
        blur=round(blur, 4),
        sharpness=round(sharpness(gray, noise_sigma=noise), 4),
        scale_used=round(gray.shape[1] / gray_full.shape[1], 4) if gray_full.shape[1] else 1.0,
        verdict=_verdict(blur, noise, None),
    )


def _analyze_subject(
    gray_full: np.ndarray,
    box: Sequence[float],
    context_pad: float,
    work_long_edge: int,
) -> Optional[FocusQuality]:
    """Subject and local background, both at one shared (normally native) scale."""
    h, w = gray_full.shape
    clipped = _clip_box(box, w, h)
    if clipped is None:
        logger.debug("subject box unusably small; falling back to whole-frame metrics")
        return None
    x1, y1, x2, y2 = clipped

    # Grow the box for context. When a large subject would push the context past
    # the cap, **shrink the surround rather than resample**: the amount of
    # background sampled is negotiable, the subject's resolution is not — that is
    # the whole point of measuring natively. Resampling is the last resort, used
    # only when the bare box alone exceeds the cap.
    bw, bh = x2 - x1, y2 - y1
    pad = context_pad
    if work_long_edge > 0:
        longest_box = max(bw, bh)
        if longest_box < work_long_edge:
            pad = min(pad, (work_long_edge - longest_box) / (2.0 * longest_box))
        else:
            pad = 0.0

    cx1 = max(0, int(x1 - bw * pad))
    cy1 = max(0, int(y1 - bh * pad))
    cx2 = min(w, int(x2 + bw * pad))
    cy2 = min(h, int(y2 + bh * pad))
    context = gray_full[cy1:cy2, cx1:cx2]

    # One scale factor for the whole context, so subject and background stay
    # directly comparable.
    scale = 1.0
    if work_long_edge > 0 and max(context.shape) > work_long_edge:
        scale = work_long_edge / max(context.shape)
        context = _resize_long_edge(context, work_long_edge)

    sx1, sy1 = int((x1 - cx1) * scale), int((y1 - cy1) * scale)
    sx2, sy2 = int((x2 - cx1) * scale), int((y2 - cy1) * scale)
    sub = _clip_box((sx1, sy1, sx2, sy2), context.shape[1], context.shape[0])
    if sub is None:
        return None
    sx1, sy1, sx2, sy2 = sub

    subject = context[sy1:sy2, sx1:sx2]
    # Noise is a sensor property, so estimate it on the context (more pixels, more
    # chance of a quiet block) and reuse it for both arms.
    noise = estimate_noise_sigma(context)
    subj_sharp = sharpness(subject, noise_sigma=noise)
    subj_blur = perceptual_blur(subject, noise_sigma=noise)

    mask = np.ones(context.shape, dtype=bool)
    mask[sy1:sy2, sx1:sx2] = False
    bg_sharp = _masked_sharpness(context, mask, noise)
    ratio = None
    if bg_sharp is not None:
        # +1 keeps the ratio finite when a smooth background legitimately has
        # near-zero structural energy.
        ratio = round((subj_sharp + 1.0) / (bg_sharp + 1.0), 4)

    return FocusQuality(
        noise_sigma=round(noise, 4),
        blur=round(subj_blur, 4),
        sharpness=round(subj_sharp, 4),
        subject_sharpness=round(subj_sharp, 4),
        background_sharpness=None if bg_sharp is None else round(bg_sharp, 4),
        focus_ratio=ratio,
        subject_blur=round(subj_blur, 4),
        subject_px=int(min(subject.shape)),
        scale_used=round(scale, 4),
        verdict=_verdict(subj_blur, noise, ratio),
    )


def _masked_sharpness(gray: np.ndarray, mask: np.ndarray, noise: float) -> Optional[float]:
    """Noise-corrected Laplacian variance over the masked-in pixels only.

    The Laplacian is computed on the whole plane first, so the subject's edges do
    not leak into the background statistic through the filter footprint; the mask
    is applied to the *response*, and a one-pixel border is dropped.
    """
    if cv2 is not None:
        lap = cv2.Laplacian(gray, cv2.CV_64F)
    else:
        lap = _convolve(gray, np.array([[0.0, 1, 0], [1, -4, 1], [0, 1, 0]]))
    inner = np.zeros_like(mask)
    inner[1:-1, 1:-1] = True
    values = lap[mask & inner]
    if values.size < 32:
        return None
    return max(0.0, float(np.var(values)) - _LAPLACIAN_NOISE_GAIN * noise**2)


def _verdict(blur: float, noise: float, focus_ratio: Optional[float]) -> str:
    """Single-word summary. Thresholds are engineering defaults, not validated.

    Noise is checked before blur because a noisy frame makes every sharpness
    reading unreliable — reporting "sharp" from a grainy image would be the same
    mistake the old metric made, in the opposite direction.
    """
    if noise >= NOISE_HIGH:
        return "noisy"
    if blur >= BLUR_BLURRED:
        return "blurred"
    if blur >= BLUR_SOFT:
        return "soft"
    if focus_ratio is not None and focus_ratio < FOCUS_RATIO_SUBJECT_SOFT:
        # The frame is sharp somewhere, but not where the subject is.
        return "soft"
    return "sharp"


def analyze_path(
    image_path: str,
    *,
    box: Optional[Sequence[float]] = None,
    work_long_edge: int = DEFAULT_WORK_LONG_EDGE,
) -> Optional[FocusQuality]:
    """Convenience wrapper for callers holding a path. ``None`` if unreadable."""
    try:
        if cv2 is not None:
            img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
            if img is None:
                raise OSError("decode returned None")
            arr = img.astype(np.float64)
        else:
            from PIL import Image

            with Image.open(image_path) as im:
                arr = np.asarray(im.convert("L"), dtype=np.float64)
    except Exception as exc:  # noqa: BLE001 — an unreadable file is a caller concern
        logger.warning("focus_quality could not read %s: %s", image_path, exc)
        return None
    return analyze(arr, box=box, work_long_edge=work_long_edge)
