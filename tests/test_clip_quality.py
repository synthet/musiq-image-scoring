"""Unit tests for the CLIP prompt-quality pick/reject signal (no GPU/DB).

Covers the pure math/logic: antonym-softmax scoring, prompt template expansion,
the within-stack rank blend, and the obvious-reject guard.
"""

from __future__ import annotations

import pytest

pytest.importorskip("sklearn")

from modules import clip_quality
from modules.selection import apply_clip_reject_guard, blended_rank_value
import numpy as np


def _unit(vecs):
    a = np.asarray(vecs, dtype=np.float32)
    return a / np.linalg.norm(a, axis=-1, keepdims=True)


# --------------------------------------------------------------------------- #
# score_embeddings
# --------------------------------------------------------------------------- #
def test_score_embeddings_range_and_direction():
    # 2-D toy space: good prompt points +x, bad prompt points -x.
    good = _unit([[1.0, 0.0]])
    bad = _unit([[-1.0, 0.0]])
    img = _unit([[1.0, 0.0], [-1.0, 0.0], [0.0, 1.0]])  # good, bad, neutral
    margin, norm = clip_quality.score_embeddings(img, good, bad)

    assert norm.shape == (3,)
    assert np.all(norm >= 0.0) and np.all(norm <= 1.0)
    assert norm[0] > 0.5 > norm[1]          # good above 0.5, bad below
    assert abs(norm[2] - 0.5) < 1e-3        # orthogonal ~ uncertain
    assert margin[0] > 0 > margin[1]


def test_score_embeddings_normalizes_unnormalized_input():
    good = _unit([[1.0, 0.0]])
    bad = _unit([[-1.0, 0.0]])
    scaled = np.array([[5.0, 0.0]], dtype=np.float32)  # not unit length
    _, norm = clip_quality.score_embeddings(scaled, good, bad)
    assert norm[0] > 0.5


# --------------------------------------------------------------------------- #
# prompt template expansion
# --------------------------------------------------------------------------- #
def test_expand_templates_short_phrase():
    out = clip_quality._expand("sharp")
    assert len(out) == len(clip_quality.TEMPLATES)
    assert "a sharp photograph" in out


def test_expand_verbatim_full_caption():
    # contains a verbatim token ('photo') -> used as-is, not templated
    out = clip_quality._expand("a keeper photo")
    assert out == ["a keeper photo"]


# --------------------------------------------------------------------------- #
# blended_rank_value
# --------------------------------------------------------------------------- #
def test_blend_disabled_returns_score_general():
    img = {"score_general": 0.8, "clip_quality_v0": 0.0}
    assert blended_rank_value(img, "score_general", 0.0) == 0.8


def test_blend_mixes_when_weight_positive():
    img = {"score_general": 0.8, "clip_quality_v0": 0.3}
    val = blended_rank_value(img, "score_general", 0.5)
    assert abs(val - (0.5 * 0.8 + 0.5 * 0.3)) < 1e-9


def test_blend_falls_back_when_clip_missing():
    img = {"score_general": 0.8}  # no clip value
    assert blended_rank_value(img, "score_general", 0.5) == 0.8


def test_blend_changes_order_as_weight_rises():
    # a: high IQA, low CLIP; b: low IQA, high CLIP.
    a = {"id": 1, "score_general": 0.9, "clip_quality_v0": 0.1}
    b = {"id": 2, "score_general": 0.6, "clip_quality_v0": 0.95}
    assert blended_rank_value(a, "score_general", 0.0) > blended_rank_value(b, "score_general", 0.0)
    assert blended_rank_value(b, "score_general", 0.6) > blended_rank_value(a, "score_general", 0.6)


# --------------------------------------------------------------------------- #
# apply_clip_reject_guard
# --------------------------------------------------------------------------- #
def test_guard_downgrades_neutral_below_threshold():
    decisions = [(1, "pick", ""), (2, "neutral", ""), (3, "reject", "")]
    clip_map = {1: 0.9, 2: 0.05, 3: 0.5}
    stack_of = {1: 10, 2: 10, 3: 10}
    out = dict((i, d) for i, d, _ in apply_clip_reject_guard(decisions, clip_map, stack_of, 0.2))
    assert out == {1: "pick", 2: "reject", 3: "reject"}


def test_guard_never_strips_last_pick():
    # sole pick of its stack is below threshold but must survive
    decisions = [(1, "pick", ""), (2, "reject", "")]
    clip_map = {1: 0.01, 2: 0.5}
    stack_of = {1: 7, 2: 7}
    out = dict((i, d) for i, d, _ in apply_clip_reject_guard(decisions, clip_map, stack_of, 0.2))
    assert out[1] == "pick"


def test_guard_downgrades_extra_pick_keeps_one():
    # two picks below threshold -> one downgraded, one kept
    decisions = [(1, "pick", ""), (2, "pick", "")]
    clip_map = {1: 0.05, 2: 0.06}
    stack_of = {1: 7, 2: 7}
    out = [d for _, d, _ in apply_clip_reject_guard(decisions, clip_map, stack_of, 0.2)]
    assert out.count("pick") == 1 and out.count("reject") == 1


def test_guard_never_upgrades():
    decisions = [(1, "neutral", "")]
    clip_map = {1: 0.99}  # above threshold -> unchanged
    out = [d for _, d, _ in apply_clip_reject_guard(decisions, clip_map, {1: 1}, 0.2)]
    assert out == ["neutral"]
