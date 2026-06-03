"""Unit tests for clip_culling input-size helpers (no GPU/DB)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from PIL import Image


@pytest.mark.parametrize(
    "size,long_edge,expected_max",
    [
        ((800, 600), 384, 384),
        ((400, 300), 512, 400),
        ((200, 100), 224, 200),
    ],
)
def test_load_pil_resized_downscales(size, long_edge, expected_max):
    from scripts.research.clip_culling import common

    fake = Image.new("RGB", size)

    with patch.object(common, "load_pil", return_value=fake):
        out = common.load_pil_resized("/fake/path.jpg", long_edge)
    assert max(out.size) == expected_max
    assert out.size[0] <= size[0] and out.size[1] <= size[1]


def test_load_pil_resized_no_op_when_none():
    from scripts.research.clip_culling import common

    fake = Image.new("RGB", (100, 50))
    with patch.object(common, "load_pil", return_value=fake):
        out = common.load_pil_resized("/fake/path.jpg", None)
    assert out.size == (100, 50)


def test_pair_margin_synthetic():
    from scripts.research.clip_culling.input_size_eval import pair_margin

    import numpy as np

    # Two tight clusters + distant third
    a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    b = np.array([0.99, 0.01, 0.0], dtype=np.float32)
    c = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    emb = {1: a, 2: b, 3: c}
    gt = {1: 0, 2: 0, 3: 1}
    m = pair_margin(emb, gt, max_pairs=100)
    assert m["pair_margin"] is not None
    assert m["diff_burst_median_dist"] > m["same_burst_median_dist"]


def test_npz_cache_path_naming():
    from scripts.research.clip_culling import common

    p = common.npz_cache_path("openclip_l14", "thumb", 512)
    assert "embedding_openclip_l14_thumb_512.npz" in str(p)
    p2 = common.npz_cache_path("openclip_l14", "thumb", 512, preprocess_size=336)
    assert "preprocess336" in str(p2)
    p3 = common.npz_cache_path("blip", "thumb", 384, track="caption")
    assert "caption_blip_thumb_384.npz" in str(p3)
    p4 = common.npz_cache_path("clip_b32", "file", 512, track="tagging")
    assert "tagging_clip_b32_file_512.npz" in str(p4)


def test_tag_entropy():
    from scripts.research.clip_culling.input_size_tagging_eval import tag_entropy

    preds = {
        1: {"landscape", "nature"},
        2: {"portrait", "urban"},
        3: {"wildlife", "nature"},
    }
    ent = tag_entropy(preds)
    assert ent > 0


def test_eval_caption_run_synthetic():
    from scripts.research.clip_culling.input_size_eval import eval_caption_run

    captions = {1: "a sunset over the beach", 2: "sunset beach scene", 3: "mountain landscape"}
    burst_gt = {1: 0, 2: 0, 3: 1}
    db_kw = {1: {"beach", "sunset"}, 3: {"mountain", "landscape"}}
    m = eval_caption_run(captions, burst_gt, db_kw)
    assert m["burst_caption_uniqueness"] is not None
    assert m["n_captions"] == 3


def test_eval_iqa_burst_spread():
    from scripts.research.clip_culling.input_size_eval import eval_iqa_burst_spread

    scores = {1: 0.5, 2: 0.8, 3: 0.6, 4: 0.9}
    burst_gt = {1: 0, 2: 0, 3: 1, 4: 1}
    m = eval_iqa_burst_spread(scores, burst_gt, min_burst_size=2)
    assert m["mean_within_burst_std"] is not None
    assert m["n_bursts"] == 2
