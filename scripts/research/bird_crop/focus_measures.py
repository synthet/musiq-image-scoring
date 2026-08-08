"""Classical, zero-inference focus measures — higher means sharper.

Why these exist alongside the learned IQA scorers
-------------------------------------------------
Phase 2b established that a bbox crop is 2.42x-17.51x more sensitive to
subject-only degradation than the whole frame, but it measured that only with
LIQE / TOPIQ / ARNIQA, each of which costs a GPU pass. These measures cost a
handful of convolutions on a small crop, so if one of them tracks subject blur
comparably it can decide bird-crop focus without a model.

``laplacian_variance`` deliberately mirrors the incumbent at
``modules/technical_failures/classical_metrics.py:32`` (``cv2.Laplacian(...).var()``),
so the study can state whether moving that *existing* metric from the whole frame
onto the crop changes its behaviour.

Known failure mode, measured rather than hidden
-----------------------------------------------
Every derivative-based measure here is **fooled by noise**: noise adds
high-frequency energy, so blurring an image lowers the score (correct) while
adding noise *raises* it (wrong). The degradation harness reports that as a
positive Spearman on the noise ladder. It is a property of the measure, not a bug
to paper over with an absolute value — see ``tests/test_bird_crop_focus_measures.py``.

Pure functions only — no DB, no GPU, no file IO — so this module unit-tests in
isolation, mirroring ``bbox.py``.
"""

from __future__ import annotations

import logging
from typing import Callable

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover - cv2 is present in ~/.venvs/tf
    cv2 = None

logger = logging.getLogger("bird_crop.focus_measures")


def _as_gray_f64(img: np.ndarray) -> np.ndarray:
    """Coerce to a 2-D float64 array. Accepts grayscale or RGB/RGBA."""
    arr = np.asarray(img)
    if arr.ndim == 3:
        # Rec. 601 luma, matching cv2.COLOR_RGB2GRAY.
        arr = arr[..., :3] @ np.array([0.299, 0.587, 0.114])
    elif arr.ndim != 2:
        raise ValueError(f"expected a 2-D or 3-D image, got shape {arr.shape}")
    return arr.astype(np.float64)


def laplacian_variance(img: np.ndarray) -> float:
    """Variance of the Laplacian — the classic sharpness metric.

    Variance is already an intensive statistic (a per-pixel second moment), so it
    needs no size normalization: a crop and a downscale of the same content give
    comparable values.
    """
    gray = _as_gray_f64(img)
    if gray.size < 9:
        return 0.0
    if cv2 is not None:
        lap = cv2.Laplacian(gray, cv2.CV_64F)
    else:
        # 4-neighbour Laplacian via slices, matching classical_metrics.py's fallback.
        c = gray[1:-1, 1:-1]
        lap = -4.0 * c + gray[:-2, 1:-1] + gray[2:, 1:-1] + gray[1:-1, :-2] + gray[1:-1, 2:]
    return float(np.var(lap))


def tenengrad(img: np.ndarray) -> float:
    """Mean squared Sobel gradient magnitude.

    First-order, so less noise-amplifying than the Laplacian, but it needs real
    contrast to register. Divided by pixel count so crops of different sizes stay
    comparable — the raw Tenengrad sum scales with area.
    """
    gray = _as_gray_f64(img)
    if gray.size < 9:
        return 0.0
    if cv2 is not None:
        gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    else:
        gx = np.gradient(gray, axis=1)
        gy = np.gradient(gray, axis=0)
    return float(np.mean(gx * gx + gy * gy))


def dog_energy(img: np.ndarray, sigma_narrow: float = 1.0, sigma_wide: float = 2.0) -> float:
    """Mean absolute Difference-of-Gaussians response — a band-pass sharpness proxy.

    The two sigmas set which blur radius the measure is most sensitive to; the
    defaults target the few-pixel defocus that separates a sharp bird from a soft
    one at typical crop scales.
    """
    gray = _as_gray_f64(img)
    if gray.size < 9:
        return 0.0
    if cv2 is None:
        return 0.0
    narrow = cv2.GaussianBlur(gray, (0, 0), sigma_narrow)
    wide = cv2.GaussianBlur(gray, (0, 0), sigma_wide)
    return float(np.mean(np.abs(narrow - wide)))


def haar_energy(img: np.ndarray, levels: int = 3) -> float:
    """Mean high-frequency energy of a multi-level Haar decomposition.

    Hand-rolled rather than taking a PyWavelets dependency for a research spike:
    a single Haar level is just sums and differences of 2x2 blocks, and the
    detail bands are what a wavelet focus measure (Pertuz's WAV1 family) reads.
    Averaged per coefficient so deeper levels and smaller crops stay comparable.
    """
    gray = _as_gray_f64(img)
    energies: list[float] = []
    cur = gray
    for _ in range(max(1, levels)):
        h, w = cur.shape
        if h < 2 or w < 2:
            break
        cur = cur[: h - h % 2, : w - w % 2]
        a = cur[0::2, 0::2]
        b = cur[0::2, 1::2]
        c = cur[1::2, 0::2]
        d = cur[1::2, 1::2]
        # Detail bands: horizontal, vertical, diagonal.
        energies.append(float(np.mean(np.abs(a - b + c - d))))  # LH
        energies.append(float(np.mean(np.abs(a + b - c - d))))  # HL
        energies.append(float(np.mean(np.abs(a - b - c + d))))  # HH
        cur = (a + b + c + d) / 4.0  # LL, carried to the next level
    return float(np.mean(energies)) if energies else 0.0


def local_entropy(img: np.ndarray, bins: int = 256) -> float:
    """Shannon entropy of the intensity histogram, in bits.

    Included because the research doc lists it, and because it is expected to
    *fail*: entropy measures how much tonal variety a region has, which blur
    barely changes. Reporting a measure that does not work is the point of a
    comparison.
    """
    gray = _as_gray_f64(img)
    if gray.size == 0:
        return 0.0
    hist, _ = np.histogram(gray, bins=bins, range=(0.0, 255.0))
    total = hist.sum()
    if total == 0:
        return 0.0
    p = hist[hist > 0] / total
    return float(-np.sum(p * np.log2(p)))


def canny_edge_density(img: np.ndarray, low: int = 50, high: int = 150) -> float:
    """Fraction of pixels Canny calls an edge.

    Stands in for the doc's "edge spread" family: defocus both weakens and widens
    edges, so a soft subject yields fewer pixels surviving non-maximum suppression.
    Already a fraction, so size-independent.

    **Not monotonic at low blur.** Canny smooths internally before
    differentiating, so mild defocus can remove aliasing jitter and yield
    *cleaner* edges: measured on a checkerboard, density rises from 0.2499 at
    sigma 0.5 to 0.2608 at sigma 1.0 before collapsing to 0.027 at sigma 2.0.
    That disqualifies it as a threshold signal for slightly-soft subjects, which
    is the case that matters most here. Pinned by
    ``test_canny_is_not_monotonic_at_low_blur``.
    """
    gray = _as_gray_f64(img)
    if cv2 is None or gray.size == 0:
        return 0.0
    edges = cv2.Canny(np.clip(gray, 0, 255).astype(np.uint8), low, high)
    return float(np.count_nonzero(edges) / edges.size)


#: Registry so evaluators iterate rather than hard-code. Keys double as the
#: ``--models`` names accepted by ``degradation_eval``.
MEASURES: dict[str, Callable[[np.ndarray], float]] = {
    "laplacian_variance": laplacian_variance,
    "tenengrad": tenengrad,
    "dog_energy": dog_energy,
    "haar_energy": haar_energy,
    "local_entropy": local_entropy,
    "canny_edge_density": canny_edge_density,
}

#: Measures whose response to *noise* runs backwards (noise adds high-frequency
#: energy). Recorded here so reports can flag the cell rather than silently
#: presenting a nonsensical sensitivity ratio.
#:
#: Measured on a smooth ramp — i.e. a defocused region, where this matters most —
#: with sigma=15 Gaussian noise: laplacian_variance 0.019 -> 4435, tenengrad
#: 28 -> 5225, dog_energy 0.018 -> 2.23, haar_energy 1.4 -> 13.9,
#: canny_edge_density 0.0 -> 0.31. A noisy *blurred* region therefore scores as
#: far "sharper" than a clean blurred one, which is the trap any threshold rule
#: built on these measures has to handle. ``local_entropy`` moved only +1.5% and
#: is excluded — its weakness is that it barely tracks blur at all.
NOISE_FOOLED = (
    "laplacian_variance",
    "tenengrad",
    "dog_energy",
    "haar_energy",
    "canny_edge_density",
)

#: Measures that actually fall when detail is destroyed. ``local_entropy`` is
#: excluded because it moves the *wrong way* — blurring a two-level pattern
#: creates intermediate grey levels and raises entropy
#: (``test_entropy_does_not_track_blur``).
#:
#: Consumers use this to qualify a result: a measure outside this set may
#: separate two populations for reasons that have nothing to do with focus
#: (scene complexity, subject size, contrast), so a good AUC from it is not
#: evidence about sharpness.
TRACKS_BLUR = (
    "laplacian_variance",
    "tenengrad",
    "dog_energy",
    "haar_energy",
    "canny_edge_density",
)


def compute_all(img: np.ndarray) -> dict[str, float]:
    """Every measure for one image. A failing measure yields ``nan``, not a crash."""
    out: dict[str, float] = {}
    for name, fn in MEASURES.items():
        try:
            out[name] = float(fn(img))
        except Exception as exc:  # noqa: BLE001 — one bad measure must not kill a sweep
            logger.warning("focus measure %s failed: %s", name, exc)
            out[name] = float("nan")
    return out
