"""Unit tests for the synthetic degradation primitives (no GPU/DB, synthetic images).

These guard the part of the study that provides ground truth by construction: if a
degradation does not actually degrade, or leaks outside the region it was asked to
touch, every number downstream is meaningless.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from scripts.research.bird_crop.degradation_eval import (
    BLUR_SIGMAS,
    DEGRADATIONS,
    MOTION_LENGTHS,
    NOISE_SIGMAS,
    _LADDER,
    degrade,
    sensitivity,
)


def _detailed_image(size=(200, 160)) -> Image.Image:
    """High-frequency checkerboard: blur/smear measurably reduces its variance."""
    w, h = size
    xs = np.arange(w)
    ys = np.arange(h)
    grid = ((xs[None, :] // 4 + ys[:, None] // 4) % 2 * 255).astype(np.uint8)
    return Image.fromarray(np.dstack([grid] * 3))


def _high_freq_energy(img: Image.Image) -> float:
    """Mean absolute horizontal gradient — falls when detail is destroyed."""
    arr = np.asarray(img.convert("L"), dtype=np.float32)
    return float(np.abs(np.diff(arr, axis=1)).mean())


# --------------------------------------------------------------------------
# Every ladder starts at a clean anchor
# --------------------------------------------------------------------------
@pytest.mark.parametrize("kind", DEGRADATIONS)
def test_every_ladder_starts_clean(kind):
    """sensitivity() reads the clean baseline from the first rung."""
    assert _LADDER[kind][0] == 0


@pytest.mark.parametrize("kind", DEGRADATIONS)
def test_zero_strength_is_a_noop(kind):
    img = _detailed_image()
    out = degrade(img, kind, 0)
    assert np.array_equal(np.asarray(img), np.asarray(out))


@pytest.mark.parametrize("kind", DEGRADATIONS)
def test_ladder_is_monotonically_increasing(kind):
    ladder = _LADDER[kind]
    assert list(ladder) == sorted(ladder)


# --------------------------------------------------------------------------
# Degradations actually degrade, and monotonically
# --------------------------------------------------------------------------
@pytest.mark.parametrize("kind,ladder", [("blur", BLUR_SIGMAS), ("motion", MOTION_LENGTHS)])
def test_blur_and_motion_monotonically_destroy_detail(kind, ladder):
    img = _detailed_image()
    energies = [_high_freq_energy(degrade(img, kind, s)) for s in ladder]
    assert energies == sorted(energies, reverse=True), energies
    assert energies[-1] < energies[0] * 0.5


def test_noise_monotonically_adds_variance_to_a_flat_image():
    flat = Image.new("RGB", (200, 160), (128, 128, 128))
    stds = [float(np.asarray(degrade(flat, "noise", s), dtype=np.float32).std()) for s in NOISE_SIGMAS]
    assert stds == sorted(stds), stds
    assert stds[0] == pytest.approx(0.0)


def test_motion_blur_preserves_image_size_for_long_kernels():
    """Regression: PIL's ImageFilter.Kernel only supports 3x3/5x5, so the longer
    rungs of the motion ladder must not go through it."""
    img = _detailed_image()
    for n in MOTION_LENGTHS:
        out = degrade(img, "motion", n)
        assert out.size == img.size, n


def test_motion_blur_smears_along_x_only():
    """Directionality, tested with stripes rather than a checkerboard.

    Vertical stripes vary along x, so a horizontal smear must wreck them.
    Horizontal stripes are constant along x, so averaging along x must leave them
    untouched. (A checkerboard cannot show this: smearing it horizontally also
    collapses the vertical differences, because both phases average to the same
    value.)
    """
    h, w = 160, 200
    vertical_stripes = ((np.arange(w) // 4) % 2 * 255).astype(np.uint8)
    vert = Image.fromarray(np.dstack([np.tile(vertical_stripes, (h, 1))] * 3))
    horizontal_stripes = ((np.arange(h) // 4) % 2 * 255).astype(np.uint8)
    horiz = Image.fromarray(np.dstack([np.tile(horizontal_stripes[:, None], (1, w))] * 3))

    smeared_vert = degrade(vert, "motion", 21)
    smeared_horiz = degrade(horiz, "motion", 21)

    # Vertical stripes: detail destroyed.
    assert _high_freq_energy(smeared_vert) < 0.2 * _high_freq_energy(vert)
    # Horizontal stripes: untouched by an x-axis average.
    assert np.allclose(
        np.asarray(smeared_horiz, dtype=np.float32),
        np.asarray(horiz, dtype=np.float32),
        atol=1.0,
    )


def test_motion_blur_does_not_darken_edges():
    """Reflect padding, not zero padding — otherwise the frame edge dims and the
    scorer would react to a vignette instead of the smear."""
    flat = Image.new("RGB", (200, 160), (200, 200, 200))
    out = np.asarray(degrade(flat, "motion", 21), dtype=np.float32)
    assert out[:, :5].mean() == pytest.approx(200, abs=1.0)
    assert out[:, -5:].mean() == pytest.approx(200, abs=1.0)


# --------------------------------------------------------------------------
# Region masking — the mechanism that isolates "subject soft" from "photo soft"
# --------------------------------------------------------------------------
@pytest.mark.parametrize("kind,strength", [("blur", 6.4), ("motion", 21), ("noise", 32.0)])
def test_region_degradation_leaves_outside_pixels_untouched(kind, strength):
    img = _detailed_image()
    region = (50, 40, 120, 100)
    out = degrade(img, kind, strength, region_box=region)

    a_in, a_out = np.asarray(img), np.asarray(out)
    left, top, right, bottom = region

    # Outside the box: byte-identical.
    assert np.array_equal(a_in[:top, :], a_out[:top, :])
    assert np.array_equal(a_in[bottom:, :], a_out[bottom:, :])
    assert np.array_equal(a_in[:, :left], a_out[:, :left])
    assert np.array_equal(a_in[:, right:], a_out[:, right:])
    # Inside the box: changed.
    assert not np.array_equal(a_in[top:bottom, left:right], a_out[top:bottom, left:right])


def test_region_degradation_is_weaker_globally_than_whole_frame():
    """The premise of the 2x2: degrading only the subject moves whole-frame
    statistics far less than degrading everything."""
    img = _detailed_image()
    region = (50, 40, 120, 100)
    clean = _high_freq_energy(img)
    subject_only = _high_freq_energy(degrade(img, "blur", 6.4, region_box=region))
    whole = _high_freq_energy(degrade(img, "blur", 6.4))
    assert whole < subject_only < clean


def test_region_zero_strength_is_a_noop():
    img = _detailed_image()
    out = degrade(img, "blur", 0, region_box=(10, 10, 50, 50))
    assert np.array_equal(np.asarray(img), np.asarray(out))


# --------------------------------------------------------------------------
# sensitivity()
# --------------------------------------------------------------------------
def test_sensitivity_detects_a_perfect_negative_response():
    out = sensitivity([0, 1, 2, 3], [1.0, 0.8, 0.6, 0.4])
    assert out["spearman"] == pytest.approx(-1.0)
    # clean 1.0 -> worst 0.4 is a 60% drop
    assert out["relative_drop"] == pytest.approx(0.6)
    assert out["n"] == 4


def test_sensitivity_reports_a_flat_response_as_no_drop():
    """A scorer blind to the degradation must show ~zero drop, which is exactly
    the signal the study is looking for in the full-frame/subject cell."""
    out = sensitivity([0, 1, 2, 3], [0.7, 0.7, 0.7, 0.7])
    assert out["relative_drop"] == pytest.approx(0.0)


def test_sensitivity_tolerates_missing_scores():
    out = sensitivity([0, 1, 2, 3], [1.0, None, 0.6, None])
    assert out["n"] == 2


def test_sensitivity_needs_at_least_three_points():
    out = sensitivity([0, 1], [1.0, 0.5])
    assert out["spearman"] is None
    assert out["n"] == 2


def test_sensitivity_ignores_non_finite_scores():
    out = sensitivity([0, 1, 2], [1.0, float("nan"), 0.5])
    assert out["n"] == 2
