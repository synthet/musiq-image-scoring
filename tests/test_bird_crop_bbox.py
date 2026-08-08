"""Unit tests for the bird-crop study's bbox geometry helpers (no GPU/DB/PIL)."""

from __future__ import annotations

import pytest

from scripts.research.bird_crop.bbox import (
    count_edges_touched,
    geometry_features,
    is_not_detected,
    is_scan_failed,
    padded_box,
    parse_bbox,
    subject_px_at_long_edge,
)


def _box(**kw) -> dict:
    """A realistic Z8 row: 8256x5504 frame, 1600x1200 bird slightly left of centre."""
    base = {
        "x1": 3000,
        "y1": 2000,
        "x2": 4600,
        "y2": 3200,
        "img_w": 8256,
        "img_h": 5504,
        "conf": 0.87,
        "area_frac": 0.0423,
    }
    base.update(kw)
    return base


# --------------------------------------------------------------------------
# parse_bbox — the three-state column
# --------------------------------------------------------------------------
def test_parse_bbox_accepts_real_box():
    box = parse_bbox(_box())
    assert box is not None
    assert (box.x1, box.y1, box.x2, box.y2) == (3000, 2000, 4600, 3200)
    assert box.width == 1600 and box.height == 1200
    assert box.conf == pytest.approx(0.87)


@pytest.mark.parametrize(
    "value",
    [
        None,                          # never scanned
        {"detected": False},           # detector ran, no bird
        {},                            # empty object
        "not a dict",                  # wrong type
        {"x1": 1, "y1": 2, "x2": 3},   # missing keys
    ],
)
def test_parse_bbox_rejects_non_boxes(value):
    """NULL, the sentinel, and malformed rows must all be skipped, not full-framed."""
    assert parse_bbox(value) is None


@pytest.mark.parametrize(
    "value,expected",
    [
        ({"detected": False}, True),
        (None, False),
        ({"detected": True}, False),
        (_box(), False),
        # A scan failure is NOT "no bird here" — an unreadable file says nothing
        # about bird presence, so it must not inflate the not-detected population.
        ({"detected": False, "error": "decode_error: boom"}, False),
    ],
)
def test_is_not_detected_only_matches_clean_no_bird(value, expected):
    assert is_not_detected(value) is expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ({"detected": False, "error": "decode_error: boom"}, True),
        ({"detected": False}, False),
        (None, False),
        (_box(), False),
    ],
)
def test_is_scan_failed_matches_only_the_error_sentinel(value, expected):
    assert is_scan_failed(value) is expected


def test_scan_failure_is_skipped_by_parse_bbox():
    """All three non-box states must yield None so callers skip the image."""
    assert parse_bbox({"detected": False, "error": "file_missing"}) is None


@pytest.mark.parametrize(
    "bad",
    [
        {"x1": 10, "y1": 10, "x2": 10, "y2": 50, "img_w": 100, "img_h": 100},  # zero width
        {"x1": 10, "y1": 10, "x2": 50, "y2": 10, "img_w": 100, "img_h": 100},  # zero height
        {"x1": 0, "y1": 0, "x2": 5, "y2": 5, "img_w": 0, "img_h": 100},        # no frame
    ],
)
def test_parse_bbox_rejects_degenerate(bad):
    assert parse_bbox(bad) is None


def test_parse_bbox_normalises_inverted_coords():
    box = parse_bbox({"x1": 50, "y1": 60, "x2": 10, "y2": 20, "img_w": 100, "img_h": 100})
    assert box is not None
    assert (box.x1, box.x2, box.y1, box.y2) == (10, 50, 20, 60)


def test_area_frac_is_recomputed_not_trusted():
    """A wrong stored area_frac must not leak into the study."""
    box = parse_bbox(_box(area_frac=0.999))
    assert box is not None
    assert box.area_frac == pytest.approx((1600 * 1200) / (8256 * 5504))


# --------------------------------------------------------------------------
# geometry_features
# --------------------------------------------------------------------------
def test_centred_box_has_zero_offset():
    box = parse_bbox({"x1": 40, "y1": 40, "x2": 60, "y2": 60, "img_w": 100, "img_h": 100})
    feats = geometry_features(box)
    assert feats["cx_frac"] == pytest.approx(0.5)
    assert feats["offset_center"] == pytest.approx(0.0)


def test_offset_thirds_zero_on_a_thirds_intersection():
    # Centre at (1/3, 1/3) of a 300x300 frame => (100, 100).
    box = parse_bbox({"x1": 90, "y1": 90, "x2": 110, "y2": 110, "img_w": 300, "img_h": 300})
    assert geometry_features(box)["offset_thirds"] == pytest.approx(0.0)


def test_offset_is_scale_invariant_across_frame_sizes():
    """A Z6ii and a Z8 frame with the same relative composition must score alike."""
    small = parse_bbox({"x1": 1200, "y1": 800, "x2": 1800, "y2": 1200, "img_w": 6048, "img_h": 4032})
    large = parse_bbox({"x1": 1600, "y1": 1067, "x2": 2400, "y2": 1600, "img_w": 8064, "img_h": 5376})
    a, b = geometry_features(small), geometry_features(large)
    assert a["offset_center"] == pytest.approx(b["offset_center"], abs=1e-3)
    assert a["area_frac"] == pytest.approx(b["area_frac"], abs=1e-4)


def test_aspect_is_at_least_one_and_orientation_agnostic():
    tall = parse_bbox({"x1": 0, "y1": 0, "x2": 100, "y2": 300, "img_w": 1000, "img_h": 1000})
    wide = parse_bbox({"x1": 0, "y1": 0, "x2": 300, "y2": 100, "img_w": 1000, "img_h": 1000})
    assert geometry_features(tall)["aspect"] == pytest.approx(3.0)
    assert geometry_features(wide)["aspect"] == pytest.approx(3.0)


@pytest.mark.parametrize(
    "coords,expected",
    [
        ((10, 10, 90, 90), 0),   # free-floating
        ((0, 10, 90, 90), 1),    # left edge
        ((0, 0, 90, 90), 2),     # left + top
        ((0, 0, 100, 100), 4),   # fills frame
    ],
)
def test_count_edges_touched(coords, expected):
    x1, y1, x2, y2 = coords
    box = parse_bbox({"x1": x1, "y1": y1, "x2": x2, "y2": y2, "img_w": 100, "img_h": 100})
    assert count_edges_touched(box) == expected


# --------------------------------------------------------------------------
# subject_px_at_long_edge — the headline quantity of the study
# --------------------------------------------------------------------------
def test_subject_px_at_long_edge_matches_hand_calculation():
    box = parse_bbox(_box())  # 1600px bird in an 8256px frame
    # 1600 * (224 / 8256) = 43.4
    assert subject_px_at_long_edge(box, 224) == pytest.approx(1600 * 224 / 8256)
    # Larger model input must see proportionally more subject.
    assert subject_px_at_long_edge(box, 384) > subject_px_at_long_edge(box, 224)


# --------------------------------------------------------------------------
# padded_box — the crop policies
# --------------------------------------------------------------------------
def test_pad_matches_production_crop_to_box_maths():
    """pad=0.10 must reproduce modules.bird_detection.crop_to_box exactly."""
    box = parse_bbox(_box())
    left, top, right, bottom = padded_box(box, pad=0.10)
    assert (left, top, right, bottom) == (
        3000 - 160, 2000 - 120, 4600 + 160, 3200 + 120,
    )


def test_pad_zero_is_the_tight_box():
    box = parse_bbox(_box())
    assert padded_box(box, pad=0.0) == (3000, 2000, 4600, 3200)


def test_padding_clamps_to_frame_bounds():
    box = parse_bbox({"x1": 0, "y1": 0, "x2": 100, "y2": 100, "img_w": 100, "img_h": 100})
    left, top, right, bottom = padded_box(box, pad=0.5)
    assert (left, top, right, bottom) == (0, 0, 100, 100)


def test_min_long_px_expands_small_subject():
    """A 200px bird asked for a 600px window gets one, centred on the bird."""
    box = parse_bbox({"x1": 900, "y1": 900, "x2": 1100, "y2": 1100, "img_w": 4000, "img_h": 4000})
    left, top, right, bottom = padded_box(box, pad=0.0, min_long_px=600)
    assert right - left == 600
    assert bottom - top == 600
    # Still centred on the bird.
    assert (left + right) / 2 == pytest.approx(1000)


def test_min_long_px_does_not_shrink_large_subject():
    """A subject already larger than the floor must be left alone."""
    box = parse_bbox({"x1": 0, "y1": 0, "x2": 2000, "y2": 2000, "img_w": 4000, "img_h": 4000})
    left, top, right, bottom = padded_box(box, pad=0.0, min_long_px=600)
    assert (right - left, bottom - top) == (2000, 2000)


def test_min_long_px_never_upscales_beyond_the_frame():
    """The core cropctx guarantee: never invent pixels that do not exist."""
    box = parse_bbox({"x1": 40, "y1": 40, "x2": 60, "y2": 60, "img_w": 100, "img_h": 100})
    left, top, right, bottom = padded_box(box, pad=0.0, min_long_px=5000)
    assert (left, top, right, bottom) == (0, 0, 100, 100)
    assert right - left <= box.img_w
    assert bottom - top <= box.img_h


def test_edge_adjacent_subject_keeps_requested_window_size():
    """A bird against the left edge should gain context to the right, not lose it."""
    box = parse_bbox({"x1": 0, "y1": 500, "x2": 200, "y2": 700, "img_w": 4000, "img_h": 4000})
    rect = padded_box(box, pad=0.0, min_long_px=600)
    assert rect[0] == 0
    assert rect[2] - rect[0] == 600


@pytest.mark.parametrize("pad", [0.0, 0.10, 0.25, 0.50])
@pytest.mark.parametrize("min_long_px", [0, 384, 1024])
def test_padded_box_always_within_frame_and_non_degenerate(pad, min_long_px):
    box = parse_bbox(_box())
    left, top, right, bottom = padded_box(box, pad=pad, min_long_px=min_long_px)
    assert 0 <= left < right <= box.img_w
    assert 0 <= top < bottom <= box.img_h
