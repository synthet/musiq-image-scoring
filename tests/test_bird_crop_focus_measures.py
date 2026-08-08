"""Unit tests for the classical focus measures (no GPU/DB, synthetic images).

Two things are pinned here. First, that each measure actually collapses under
blur — otherwise it cannot decide focus. Second, and just as important, the
**failure** modes: these measures are fooled by noise, and entropy barely tracks
blur at all. Those are documented properties, so a future change that silently
"fixes" them by taking absolute values would be a regression in honesty.
"""

from __future__ import annotations

import numpy as np
import pytest

from scripts.research.bird_crop.focus_measures import (
    MEASURES,
    NOISE_FOOLED,
    canny_edge_density,
    compute_all,
    haar_energy,
    laplacian_variance,
    local_entropy,
    tenengrad,
)

# Measures whose whole purpose is to fall when detail is destroyed. Entropy is
# excluded on purpose — see test_entropy_does_not_track_blur.
_DETAIL_MEASURES = [n for n in MEASURES if n != "local_entropy"]


def _checkerboard(size=(160, 200)) -> np.ndarray:
    """High-frequency pattern: blurring measurably destroys its detail."""
    h, w = size
    ys, xs = np.mgrid[0:h, 0:w]
    return ((xs // 4 + ys // 4) % 2 * 255).astype(np.float64)


def _smooth_ramp(size=(160, 200)) -> np.ndarray:
    """A defocused region — smooth, low-frequency, no real detail."""
    h, w = size
    ys, xs = np.mgrid[0:h, 0:w]
    return (xs * 0.6 + ys * 0.3).astype(np.float64)


def _blur(img: np.ndarray, sigma: float) -> np.ndarray:
    cv2 = pytest.importorskip("cv2")
    return cv2.GaussianBlur(img, (0, 0), sigma)


def _noisy(img: np.ndarray, sigma: float, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.clip(img + rng.normal(0, sigma, img.shape), 0, 255)


# --------------------------------------------------------------------------
# The core property: detail measures fall when detail is destroyed
# --------------------------------------------------------------------------
@pytest.mark.parametrize("name", _DETAIL_MEASURES)
def test_blur_reduces_every_detail_measure(name):
    sharp = _checkerboard()

    assert MEASURES[name](_blur(sharp, 3.0)) < MEASURES[name](sharp)


@pytest.mark.parametrize("name", [n for n in _DETAIL_MEASURES if n != "canny_edge_density"])
def test_response_is_monotonic_in_blur_strength(name):
    """More blur must never score as sharper than less blur."""
    sharp = _checkerboard()
    values = [MEASURES[name](_blur(sharp, s)) for s in (0.5, 1.0, 2.0, 4.0)]

    assert values == sorted(values, reverse=True), values


def test_canny_is_not_monotonic_at_low_blur():
    """Canny *rises* slightly from sigma 0.5 to 1.0 before collapsing.

    Canny smooths internally before differentiating, so mild blur can remove
    aliasing jitter and yield cleaner, better-connected edges. Pinned because it
    disqualifies edge density as a threshold signal for *mild* misfocus — which is
    precisely the case that matters for a slightly-soft bird.
    """
    sharp = _checkerboard()
    v05, v10, v40 = (canny_edge_density(_blur(sharp, s)) for s in (0.5, 1.0, 4.0))

    assert v10 > v05, (v05, v10)   # the non-monotonic bump
    assert v40 < v05               # but heavy blur still destroys it


@pytest.mark.parametrize("name", _DETAIL_MEASURES)
def test_detail_scores_above_smooth(name):
    """A textured region must outscore a featureless one."""
    assert MEASURES[name](_checkerboard()) > MEASURES[name](_smooth_ramp())


# --------------------------------------------------------------------------
# Documented failure mode: noise masquerades as sharpness
# --------------------------------------------------------------------------
@pytest.mark.parametrize("name", NOISE_FOOLED)
def test_noise_inflates_the_measures_we_say_it_inflates(name):
    """On a defocused region, noise must raise the score — that is the trap.

    Pinned so the NOISE_FOOLED list stays truthful: it is what reports use to
    flag a cell rather than present a nonsensical sensitivity ratio.
    """
    smooth = _smooth_ramp()

    assert MEASURES[name](_noisy(smooth, 15.0)) > MEASURES[name](smooth)


def test_entropy_is_not_in_the_noise_fooled_list():
    """Entropy moved only ~1.5% on the smooth-ramp probe, so it is excluded."""
    smooth = _smooth_ramp()
    clean, noisy = local_entropy(smooth), local_entropy(_noisy(smooth, 15.0))

    assert "local_entropy" not in NOISE_FOOLED
    assert noisy < clean * 1.05


def test_entropy_does_not_track_blur():
    """Entropy is included to be *shown* not to work, so pin that it doesn't.

    Blurring a two-level checkerboard creates intermediate grey levels, which
    *raises* entropy even though detail was destroyed.
    """
    sharp = _checkerboard()

    assert local_entropy(_blur(sharp, 3.0)) > local_entropy(sharp)


# --------------------------------------------------------------------------
# Scale handling — crops of different sizes must stay comparable
# --------------------------------------------------------------------------
@pytest.mark.parametrize("name", _DETAIL_MEASURES)
def test_measures_are_not_dominated_by_pixel_count(name):
    """Doubling the area of the same pattern must not double the score.

    The raw Tenengrad/Haar sums scale with pixel count; they are averaged for
    exactly this reason. Without it, a big crop would outscore a small sharp one.
    """
    small = _checkerboard((160, 200))
    large = _checkerboard((320, 400))

    v_small, v_large = MEASURES[name](small), MEASURES[name](large)

    assert v_large == pytest.approx(v_small, rel=0.35), (v_small, v_large)


# --------------------------------------------------------------------------
# Input handling
# --------------------------------------------------------------------------
def test_rgb_input_is_accepted_and_matches_luma():
    gray = _checkerboard()
    rgb = np.dstack([gray] * 3)

    assert laplacian_variance(rgb) == pytest.approx(laplacian_variance(gray), rel=1e-6)


def test_tiny_and_empty_images_do_not_raise():
    for shape in ((1, 1), (2, 2), (0, 0)):
        img = np.zeros(shape, dtype=np.float64)
        assert laplacian_variance(img) >= 0.0
        assert tenengrad(img) >= 0.0
        assert haar_energy(img) >= 0.0
        assert local_entropy(img) >= 0.0
        assert canny_edge_density(img) >= 0.0


def test_non_image_input_raises():
    with pytest.raises(ValueError):
        laplacian_variance(np.zeros((2, 2, 3, 4)))


def test_compute_all_returns_every_measure():
    out = compute_all(_checkerboard())

    assert set(out) == set(MEASURES)
    assert all(np.isfinite(v) for v in out.values())


def test_compute_all_survives_a_failing_measure(monkeypatch):
    """One broken measure must not kill a sweep — it yields nan."""
    def boom(_):
        raise RuntimeError("synthetic failure")

    monkeypatch.setitem(MEASURES, "tenengrad", boom)
    out = compute_all(_checkerboard())

    assert np.isnan(out["tenengrad"])
    assert np.isfinite(out["laplacian_variance"])
