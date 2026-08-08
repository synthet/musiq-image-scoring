"""Unit tests for bird-crop variant parsing and PIL cropping (no GPU/DB, synthetic images)."""

from __future__ import annotations

import pytest
from PIL import Image

from scripts.research.bird_crop.crops import (
    CropSpec,
    crop_for_variant,
    parse_variant,
    rescale_box,
    resize_to_long_edge,
)
from scripts.research.bird_crop.bbox import parse_bbox

FRAME = (4000, 3000)
BBOX = {"x1": 1800, "y1": 1400, "x2": 2200, "y2": 1700, "img_w": 4000, "img_h": 3000, "conf": 0.8}


def _frame() -> Image.Image:
    return Image.new("RGB", FRAME, (10, 120, 30))


# --------------------------------------------------------------------------
# parse_variant
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "token,pad,ctx_k",
    [
        ("full", 0.0, 0.0),
        ("crop", 0.10, 0.0),        # must reproduce production's pad_frac=0.10
        ("croppad25", 0.25, 0.0),
        ("croppad50", 0.50, 0.0),
        ("cropctx10", 0.10, 1.0),
        ("cropctx15", 0.10, 1.5),
        ("cropctx20", 0.10, 2.0),
    ],
)
def test_parse_variant_known_tokens(token, pad, ctx_k):
    spec = parse_variant(token)
    assert spec.token == token
    assert spec.pad == pytest.approx(pad)
    assert spec.ctx_k == pytest.approx(ctx_k)


def test_parse_variant_is_case_insensitive_and_trims():
    assert parse_variant("  CROP  ").pad == pytest.approx(0.10)


@pytest.mark.parametrize("token", ["cropbogus", "", "thumb", "croppad", "cropctx", "crop_pad25"])
def test_parse_variant_rejects_unknown(token):
    """A typo must fail loudly, not silently degrade to a full frame."""
    with pytest.raises(ValueError):
        parse_variant(token)


def test_full_is_the_only_full_frame_variant():
    assert parse_variant("full").is_full_frame
    assert not parse_variant("crop").is_full_frame


# --------------------------------------------------------------------------
# crop_for_variant — skip semantics are the correctness-critical part
# --------------------------------------------------------------------------
@pytest.mark.parametrize("bbox", [None, {"detected": False}, {}, "junk"])
def test_crop_returns_none_without_a_box(bbox):
    """No box => skip the image. Silently returning the full frame would make a
    crop run and a full-frame run cover different populations."""
    assert crop_for_variant(_frame(), bbox, parse_variant("crop")) is None


@pytest.mark.parametrize("bbox", [None, {"detected": False}])
def test_full_variant_still_works_without_a_box(bbox):
    result = crop_for_variant(_frame(), bbox, parse_variant("full"))
    assert result is not None
    assert result.image.size == FRAME


def test_crop_size_matches_padded_box():
    result = crop_for_variant(_frame(), BBOX, parse_variant("crop"))
    assert result is not None
    # 400x300 box, pad 10% => +40 each side in x, +30 in y
    assert result.crop_w == 400 + 80
    assert result.crop_h == 300 + 60
    assert result.image.size == (480, 360)


def test_more_padding_yields_a_larger_crop():
    sizes = []
    for token in ("crop", "croppad25", "croppad50"):
        result = crop_for_variant(_frame(), BBOX, parse_variant(token))
        assert result is not None
        sizes.append(result.crop_w)
    assert sizes == sorted(sizes)
    assert len(set(sizes)) == 3


def test_crop_is_much_smaller_than_the_frame():
    """The whole premise: the crop must concentrate pixels on the subject."""
    result = crop_for_variant(_frame(), BBOX, parse_variant("crop"))
    assert result is not None
    assert result.crop_w * result.crop_h < 0.05 * FRAME[0] * FRAME[1]


def test_aspect_is_reported_and_at_least_one():
    result = crop_for_variant(_frame(), BBOX, parse_variant("crop"))
    assert result is not None
    # 480x360 => 4:3
    assert result.aspect == pytest.approx(480 / 360)
    assert result.aspect >= 1.0


def test_crop_scale_factor_is_native_over_model_input():
    """Recorded so the analysis can regress out resampling ratio (an IQA confound)."""
    result = crop_for_variant(_frame(), BBOX, parse_variant("crop"), long_edge=224)
    assert result is not None
    assert result.crop_scale_factor == pytest.approx(480 / 224)
    assert result.crop_scale_factor > 1.0  # not upscaled


def test_cropctx_expands_only_when_the_box_is_smaller_than_the_floor():
    tiny = {"x1": 1990, "y1": 1490, "x2": 2010, "y2": 1510, "img_w": 4000, "img_h": 3000}
    plain = crop_for_variant(_frame(), tiny, parse_variant("crop"), long_edge=224)
    ctx = crop_for_variant(_frame(), tiny, parse_variant("cropctx15"), long_edge=224)
    assert plain is not None and ctx is not None
    assert ctx.crop_w > plain.crop_w
    assert ctx.crop_w >= int(1.5 * 224)


def test_cropctx_is_a_noop_for_a_large_box():
    """Documents the measured finding: on 45MP frames the native box already
    exceeds k x long_edge, so cropctx equals crop for ~all of the library."""
    plain = crop_for_variant(_frame(), BBOX, parse_variant("crop"), long_edge=224)
    ctx = crop_for_variant(_frame(), BBOX, parse_variant("cropctx15"), long_edge=224)
    assert plain is not None and ctx is not None
    assert (ctx.crop_w, ctx.crop_h) == (plain.crop_w, plain.crop_h)


def test_crop_never_exceeds_frame_bounds():
    edge = {"x1": 0, "y1": 0, "x2": 300, "y2": 200, "img_w": 4000, "img_h": 3000}
    result = crop_for_variant(_frame(), edge, parse_variant("croppad50"), long_edge=224)
    assert result is not None
    assert result.crop_w <= FRAME[0]
    assert result.crop_h <= FRAME[1]


# --------------------------------------------------------------------------
# rescale_box — the RAW decode-branch hazard
# --------------------------------------------------------------------------
def test_rescale_box_is_identity_when_sizes_match():
    box = parse_bbox(BBOX)
    assert rescale_box(box, 4000, 3000) is box


def test_rescale_box_scales_when_the_decode_differs():
    """A later decode can pick a different RAW branch and yield another size, so
    coordinates must scale by ratio rather than be trusted as absolute pixels."""
    box = parse_bbox(BBOX)
    scaled = rescale_box(box, 2000, 1500)  # half size
    assert (scaled.x1, scaled.y1, scaled.x2, scaled.y2) == (900, 700, 1100, 850)
    assert (scaled.img_w, scaled.img_h) == (2000, 1500)
    # Relative geometry must survive the rescale.
    assert scaled.area_frac == pytest.approx(box.area_frac, abs=1e-4)


def test_crop_uses_rescaled_coords_when_decode_size_differs():
    """A 2000x1500 decode with a box stored against 4000x3000 must still crop the
    subject, not a wrong region."""
    smaller = Image.new("RGB", (2000, 1500))
    result = crop_for_variant(smaller, BBOX, parse_variant("crop"))
    assert result is not None
    assert result.crop_w == pytest.approx(240, abs=2)  # half of 480


# --------------------------------------------------------------------------
# resize_to_long_edge
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "size,long_edge,expected_max",
    [((800, 600), 224, 224), ((200, 100), 224, 200), ((400, 300), 0, 400)],
)
def test_resize_downscales_but_never_upscales(size, long_edge, expected_max):
    out = resize_to_long_edge(Image.new("RGB", size), long_edge)
    assert max(out.size) == expected_max


def test_resize_preserves_aspect_ratio():
    out = resize_to_long_edge(Image.new("RGB", (800, 400)), 224)
    assert out.size == (224, 112)


def test_crop_spec_is_hashable_and_frozen():
    spec = parse_variant("crop")
    assert isinstance(spec, CropSpec)
    with pytest.raises(Exception):
        spec.pad = 0.9  # type: ignore[misc]
