"""Unit tests for AF-metadata geometry (no exiftool, no DB, no files).

The reconciliation these cover is easy to get wrong and fails *silently*: Nikon
writes AF coordinates in sensor space while ``images.bird_bbox`` is stored in
EXIF-oriented display space. A missing rotation would not crash — it would just
quietly report that the camera focused somewhere other than the bird on every
portrait frame, and the study would conclude the AF cue is weak.
"""

from __future__ import annotations

import pytest

from scripts.research.bird_crop.af_metadata import (
    AFArea,
    af_bird_agreement,
    af_box_in_display_space,
    availability,
)
from scripts.research.bird_crop.bbox import parse_bbox


def _meta(**over):
    """A landscape Z8-shaped AF record; override any field per test."""
    base = {
        "AFAreaXPosition": 4128,   # centred horizontally
        "AFAreaYPosition": 2752,   # centred vertically
        "AFAreaWidth": 0,
        "AFAreaHeight": 0,
        "AFImageWidth": 8256,
        "AFImageHeight": 5504,
        "Orientation": 1,
    }
    base.update(over)
    return base


def _box(x1, y1, x2, y2, w=1000, h=1000, conf=0.9):
    return parse_bbox(
        {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "img_w": w, "img_h": h, "conf": conf}
    )


# --------------------------------------------------------------------------
# Normalisation
# --------------------------------------------------------------------------
def test_centre_af_point_normalises_to_the_centre():
    af = af_box_in_display_space(_meta())

    assert af is not None
    assert af.cx == pytest.approx(0.5)
    assert af.cy == pytest.approx(0.5)


def test_af_region_extent_is_normalised():
    af = af_box_in_display_space(_meta(AFAreaXPosition=0, AFAreaYPosition=0,
                                       AFAreaWidth=826, AFAreaHeight=550))

    assert af.x1 == pytest.approx(0.0)
    assert af.x2 == pytest.approx(0.1, abs=1e-3)
    assert af.y2 == pytest.approx(0.1, abs=1e-3)


def test_missing_af_area_returns_none():
    """D90/D300 write no AF region — callers must degrade, not guess."""
    assert af_box_in_display_space(_meta(AFAreaXPosition=None)) is None
    assert af_box_in_display_space({}) is None


def test_missing_af_image_size_falls_back_to_exif_frame():
    """One Z6ii file in the sample had AF coords but no AFImageWidth."""
    af = af_box_in_display_space(
        _meta(AFImageWidth=None, AFImageHeight=None, ImageWidth=8256, ImageHeight=5504)
    )

    assert af is not None
    assert af.cx == pytest.approx(0.5)


def test_unusable_frame_size_returns_none():
    assert af_box_in_display_space(_meta(AFImageWidth=0, ImageWidth=0)) is None
    assert af_box_in_display_space(_meta(AFImageWidth="wide", ImageWidth=None)) is None


# --------------------------------------------------------------------------
# Orientation — the part that fails silently if wrong
# --------------------------------------------------------------------------
@pytest.mark.parametrize("orientation", [1, 2, 3, 4, 5, 6, 7, 8])
def test_centre_stays_centred_under_every_orientation(orientation):
    """A point at the sensor centre is at the display centre for all 8 values."""
    af = af_box_in_display_space(_meta(Orientation=orientation))

    assert af.cx == pytest.approx(0.5)
    assert af.cy == pytest.approx(0.5)


@pytest.mark.parametrize(
    "orientation,expected",
    [
        (1, (0.25, 0.10)),   # identity
        (2, (0.75, 0.10)),   # mirror horizontal
        (3, (0.75, 0.90)),   # rotate 180
        (4, (0.25, 0.90)),   # mirror vertical
        (5, (0.10, 0.25)),   # transpose
        (6, (0.90, 0.25)),   # rotate 90 CW
        (7, (0.90, 0.75)),   # transverse
        (8, (0.10, 0.75)),   # rotate 270 CW
    ],
)
def test_off_centre_point_maps_correctly_per_orientation(orientation, expected):
    """A point at sensor (0.25, 0.10) lands where EXIF says it should."""
    af = af_box_in_display_space(
        _meta(AFAreaXPosition=0.25 * 8256, AFAreaYPosition=0.10 * 5504,
              Orientation=orientation)
    )

    assert (af.cx, af.cy) == (pytest.approx(expected[0]), pytest.approx(expected[1]))


def test_rotation_keeps_corners_ordered():
    """A rotation can swap min and max; the box must come back well-formed."""
    af = af_box_in_display_space(
        _meta(AFAreaXPosition=0, AFAreaYPosition=0,
              AFAreaWidth=826, AFAreaHeight=550, Orientation=6)
    )

    assert af.x1 <= af.x2 and af.y1 <= af.y2


def test_unknown_orientation_is_treated_as_identity():
    """An unrecognised value must leave coordinates alone, not rotate arbitrarily."""
    off = _meta(AFAreaXPosition=0.25 * 8256, AFAreaYPosition=0.10 * 5504)
    for bad in (0, 99, None, "sideways"):
        af = af_box_in_display_space({**off, "Orientation": bad})
        assert (af.cx, af.cy) == (pytest.approx(0.25), pytest.approx(0.10))


# --------------------------------------------------------------------------
# Agreement geometry
# --------------------------------------------------------------------------
def test_af_centre_inside_bird_box_is_detected():
    af = AFArea(0.45, 0.45, 0.55, 0.55)
    result = af_bird_agreement(af, _box(400, 400, 600, 600))

    assert result["centre_inside"] is True
    assert result["centre_distance"] == pytest.approx(0.0, abs=1e-6)
    assert result["iou"] > 0.0


def test_af_centre_outside_bird_box_is_detected():
    af = AFArea(0.05, 0.05, 0.15, 0.15)
    result = af_bird_agreement(af, _box(400, 400, 600, 600))

    assert result["centre_inside"] is False
    assert result["iou"] == 0.0
    assert result["centre_distance"] > 0.4


def test_identical_boxes_give_iou_one():
    af = AFArea(0.4, 0.4, 0.6, 0.6)
    result = af_bird_agreement(af, _box(400, 400, 600, 600))

    assert result["iou"] == pytest.approx(1.0)


def test_agreement_normalises_the_bird_box_by_its_own_frame():
    """bird_bbox carries img_w/img_h; a different decode size must not shift it."""
    af = AFArea(0.45, 0.45, 0.55, 0.55)
    small = af_bird_agreement(af, _box(400, 400, 600, 600, w=1000, h=1000))
    large = af_bird_agreement(af, _box(1600, 1600, 2400, 2400, w=4000, h=4000))

    assert small["iou"] == pytest.approx(large["iou"])
    assert small["centre_distance"] == pytest.approx(large["centre_distance"])


def test_missing_side_returns_none_not_a_disagreement():
    """14.4% of the library has no AF area; scoring that as misfocus would be wrong."""
    assert af_bird_agreement(None, _box(400, 400, 600, 600)) is None
    assert af_bird_agreement(AFArea(0.4, 0.4, 0.6, 0.6), None) is None


# --------------------------------------------------------------------------
# Coverage reporting
# --------------------------------------------------------------------------
def test_availability_counts_per_camera():
    rows = [
        {"Model": "NIKON Z 8", "AFAreaXPosition": 1, "FocusDistance": 3.4},
        {"Model": "NIKON Z 8", "AFAreaXPosition": 2, "FocusDistance": 5.0},
        {"Model": "NIKON D90", "FocusDistance": 2.0},
        {"Model": "NIKON D90"},
    ]

    out = availability(rows)

    assert out["NIKON Z 8"] == {"n": 2, "af_area": 2, "focus_distance": 2}
    assert out["NIKON D90"] == {"n": 2, "af_area": 0, "focus_distance": 1}
    assert list(out) == ["NIKON Z 8", "NIKON D90"]  # sorted by count, descending
