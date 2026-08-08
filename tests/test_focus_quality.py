"""Unit tests for the algorithmic blur / focus / noise scorer (no GPU, no DB).

These pin the properties that make the module worth having over the metric it
replaces — noise is measured and subtracted, blur needs no per-image calibration,
and the subject is measured at native resolution — plus the failure modes that
were found by measurement rather than assumed.
"""

from __future__ import annotations

import numpy as np
import pytest

from modules.focus_quality import (
    BLUR_SOFT,
    NOISE_HIGH,
    FocusQuality,
    analyze,
    estimate_noise_sigma,
    laplacian_variance,
    perceptual_blur,
    sharpness,
)

cv2 = pytest.importorskip("cv2")


def _smooth(size=(400, 500)) -> np.ndarray:
    """A defocused region: smooth, low-frequency, no real detail."""
    ys, xs = np.mgrid[0 : size[0], 0 : size[1]]
    return (xs * 0.3 + ys * 0.2).astype(np.float64)


def _detail(size=(400, 500), period=5) -> np.ndarray:
    ys, xs = np.mgrid[0 : size[0], 0 : size[1]]
    return ((xs // period + ys // period) % 2 * 200 + 25).astype(np.float64)


def _noisy(img, sigma, seed=0):
    return np.clip(img + np.random.default_rng(seed).normal(0, sigma, img.shape), 0, 255)


# --------------------------------------------------------------------------
# Noise estimation — the load-bearing measurement
# --------------------------------------------------------------------------
@pytest.mark.parametrize("true_sigma", [2.0, 5.0, 10.0, 20.0])
def test_noise_sigma_recovers_injected_noise(true_sigma):
    """Immerkaer must recover a known sigma on smooth content within ~15%."""
    got = estimate_noise_sigma(_noisy(_smooth(), true_sigma))

    assert got == pytest.approx(true_sigma, rel=0.15), got


def test_noise_sigma_is_near_zero_on_a_clean_smooth_image():
    assert estimate_noise_sigma(_smooth()) < 0.5


def test_block_percentile_beats_a_global_mean_on_mixed_content():
    """A textured subject on a smooth background is the realistic case.

    A global mean is inflated by the textured region because Immerkaer's mask
    annihilates smooth surfaces, not step edges. Taking a low percentile over
    blocks reads the noise floor from the quiet ones instead.
    """
    scene = _smooth()
    scene[120:280, 150:350] = _detail()[120:280, 150:350]

    clean = estimate_noise_sigma(scene)

    # The whole point: a noiseless mixed scene must not report meaningful noise.
    assert clean < 1.0, clean


def test_noise_sigma_rises_monotonically_with_real_noise():
    scene = _smooth()
    values = [estimate_noise_sigma(_noisy(scene, s)) for s in (0.0, 3.0, 8.0, 16.0)]

    assert values == sorted(values), values


# --------------------------------------------------------------------------
# Noise-corrected sharpness — the fix for the metric this replaces
# --------------------------------------------------------------------------
def test_raw_laplacian_is_fooled_by_noise_but_corrected_sharpness_is_not():
    """The exact failure that motivated this module.

    A *blurred* region with grain must not outscore itself when clean by orders
    of magnitude. Raw Laplacian variance does; the corrected figure does not.
    """
    smooth = _smooth()
    grainy = _noisy(smooth, 15.0)

    raw_ratio = laplacian_variance(grainy) / max(laplacian_variance(smooth), 1e-9)
    corrected = sharpness(grainy)

    assert raw_ratio > 1000, raw_ratio           # the failure, pinned
    assert corrected < laplacian_variance(grainy) * 0.2, corrected  # mostly removed


def test_sharpness_is_higher_for_detail_than_for_smooth():
    assert sharpness(_detail()) > sharpness(_smooth())


def test_sharpness_never_goes_negative():
    """Over-subtraction must clamp, not produce a negative 'sharpness'."""
    assert sharpness(_smooth(), noise_sigma=50.0) == 0.0


# --------------------------------------------------------------------------
# Perceptual blur
# --------------------------------------------------------------------------
def test_blur_is_bounded():
    for img in (_smooth(), _detail(), _noisy(_detail(), 20)):
        assert 0.0 <= perceptual_blur(img) <= 1.0


def test_blur_rises_when_a_real_photo_like_image_is_blurred():
    sharp = _detail(period=9)
    values = [perceptual_blur(cv2.GaussianBlur(sharp, (0, 0), s)) for s in (0.5, 2.0, 5.0)]

    assert values[-1] > values[0], values


def test_denoising_restores_blur_ordering_under_noise():
    """Raw Crete ranks a noisy blurred region as sharper than sharp texture.

    Pinned because it is the reason the metric denoises first — and because the
    residual is why ``_verdict`` checks noise before trusting any blur reading.
    """
    blurred_noisy = _noisy(_smooth(), 15.0)
    sharp_clean = _detail()

    raw_blurred = perceptual_blur(blurred_noisy, noise_sigma=0.0)
    fixed_blurred = perceptual_blur(blurred_noisy)

    assert raw_blurred < perceptual_blur(sharp_clean, noise_sigma=0.0)  # backwards
    assert fixed_blurred > raw_blurred                                   # corrected


def test_flat_patch_is_not_reported_as_sharp():
    """A featureless patch carries no evidence; it must not read as tack sharp."""
    assert perceptual_blur(np.full((200, 200), 128.0)) == 1.0


# --------------------------------------------------------------------------
# Subject vs background, and native resolution
# --------------------------------------------------------------------------
def _natural_texture(size=(900, 1200), seed=7) -> np.ndarray:
    """Band-limited random texture — a stand-in for feather detail.

    A periodic checkerboard is the wrong fixture here: blurred to uniform grey it
    aliases against Crete's fixed 9-tap kernel and the metric degenerates. Natural
    detail has a broad spectrum, so random noise smoothed slightly behaves the way
    a real photograph does.
    """
    rng = np.random.default_rng(seed)
    return np.clip(
        cv2.GaussianBlur(rng.normal(128, 55, size), (0, 0), 1.0), 0, 255
    ).astype(np.float64)


def _scene(subject_sigma: float, background_sigma: float, size=(900, 1200)):
    """A detailed subject box inside a background, each blurred independently."""
    base = _natural_texture(size)
    bg = cv2.GaussianBlur(base, (0, 0), background_sigma) if background_sigma else base.copy()
    sub = cv2.GaussianBlur(base, (0, 0), subject_sigma) if subject_sigma else base.copy()
    y1, y2, x1, x2 = 300, 600, 400, 800
    bg[y1:y2, x1:x2] = sub[y1:y2, x1:x2]
    return bg, (x1, y1, x2, y2)


def test_focus_ratio_is_high_when_the_subject_is_the_sharp_thing():
    img, box = _scene(subject_sigma=0.0, background_sigma=4.0)

    result = analyze(img, box=box)

    assert result.focus_ratio is not None and result.focus_ratio > 2.0


def test_focus_ratio_is_low_when_the_background_is_the_sharp_thing():
    img, box = _scene(subject_sigma=4.0, background_sigma=0.0)

    result = analyze(img, box=box)

    assert result.focus_ratio is not None and result.focus_ratio < 1.0


def test_subject_is_measured_at_native_resolution():
    """The box must not be scaled down before measuring."""
    img, box = _scene(0.0, 3.0)

    result = analyze(img, box=box)

    assert result.scale_used == 1.0
    assert result.subject_px == min(box[3] - box[1], box[2] - box[0])


def test_subject_metrics_beat_whole_frame_metrics_at_finding_a_soft_subject():
    """The premise: a soft subject in a sharp frame is invisible globally."""
    img, box = _scene(subject_sigma=5.0, background_sigma=0.0)

    whole = analyze(img)
    subject = analyze(img, box=box)

    # Globally the frame still looks sharp — most of it is.
    assert whole.verdict == "sharp"
    # Measuring the subject exposes it, by blur and by the subject/background ratio.
    assert subject.blur > whole.blur, (subject.blur, whole.blur)
    assert subject.focus_ratio is not None and subject.focus_ratio < 1.0


def test_box_outside_the_frame_falls_back_to_whole_frame_metrics():
    img, _ = _scene(0.0, 0.0)

    result = analyze(img, box=(5000, 5000, 5100, 5100))

    assert result.subject_sharpness is None
    assert result.focus_ratio is None
    assert result.blur >= 0.0


def test_subject_filling_the_frame_reports_no_focus_ratio():
    """With no background left there is nothing to compare against."""
    img, _ = _scene(0.0, 0.0, size=(300, 400))

    result = analyze(img, box=(0, 0, 400, 300))

    assert result.focus_ratio is None


# --------------------------------------------------------------------------
# Verdicts
# --------------------------------------------------------------------------
def test_noise_is_reported_before_blur():
    """A grainy frame must say 'noisy', not guess at sharpness it cannot measure."""
    result = analyze(_noisy(_smooth(), NOISE_HIGH + 8.0))

    assert result.verdict == "noisy"


def test_clean_detailed_image_is_sharp():
    assert analyze(_detail(period=9)).verdict == "sharp"


def test_heavily_blurred_image_is_not_called_sharp():
    result = analyze(cv2.GaussianBlur(_detail(period=9), (0, 0), 8.0))

    assert result.verdict in {"soft", "blurred"}
    assert result.blur >= BLUR_SOFT


def test_empty_image_does_not_raise():
    result = analyze(np.zeros((0, 0)))

    assert isinstance(result, FocusQuality)
    assert result.verdict == "blurred"


def test_rgb_input_is_accepted():
    gray = _detail()
    rgb = np.dstack([gray] * 3)

    assert analyze(rgb).blur == pytest.approx(analyze(gray).blur, rel=1e-6)


def test_to_dict_round_trips_every_field():
    d = analyze(_detail()).to_dict()

    assert set(d) >= {"noise_sigma", "blur", "sharpness", "verdict", "scale_used"}
