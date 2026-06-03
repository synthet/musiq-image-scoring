"""Unit tests for two-level culling compute helpers."""

from __future__ import annotations

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("sklearn")

from modules.selection_policy import classify_best_m
from modules.two_level_culling import (
    SubStackSlotInfo,
    TwoLevelConfig,
    TwoLevelLevelConfig,
    allocate_picks_uniform,
    compute_leaf_substacks,
    process_stack_two_level,
)


def _emb(vec):
    return np.asarray(vec, dtype=np.float32).tobytes()


def test_classify_best_m_picks_top_m():
    ids = [1, 2, 3, 4, 5]
    out = classify_best_m(ids, m=2, reject_rest=True)
    assert out[1] == "pick" and out[2] == "pick"
    assert out[3] == "reject" and out[5] == "reject"


def test_classify_best_m_singleton_neutral():
    assert classify_best_m([42], m=3) == {42: "neutral"}


def test_classify_best_m_neutral_remainder():
    out = classify_best_m([1, 2, 3], m=1, reject_rest=False)
    assert out[1] == "pick"
    assert out[2] == "neutral" and out[3] == "neutral"


def test_allocate_picks_uniform_reduces_m_when_over_cap():
    # 10 substacks, M=3, N=20 -> M_eff=2, total=20
    infos = [SubStackSlotInfo(size=5, top_score=float(i)) for i in range(10)]
    slots = allocate_picks_uniform(infos, m=3, n=20)
    assert len(slots) == 10
    assert all(s == 2 for s in slots)
    assert sum(slots) == 20


def test_allocate_picks_uniform_leftover_to_largest():
    # 4 substacks size 10, M=3, N=20 -> M_eff=5 capped to M=3 -> 12 picks, leftover 8
    infos = [
        SubStackSlotInfo(size=10, top_score=0.9),
        SubStackSlotInfo(size=10, top_score=0.8),
        SubStackSlotInfo(size=10, top_score=0.7),
        SubStackSlotInfo(size=10, top_score=0.6),
    ]
    slots = allocate_picks_uniform(infos, m=3, n=20)
    assert sum(slots) <= 20
    assert max(slots) <= 3
    assert all(s >= 1 for s in slots)


def test_allocate_picks_uniform_respects_substack_size():
    infos = [SubStackSlotInfo(size=1, top_score=1.0) for _ in range(5)]
    slots = allocate_picks_uniform(infos, m=3, n=20)
    assert all(s <= 1 for s in slots)
    assert sum(slots) == 5


def test_compute_leaf_substacks_single_pass():
    # One model, one threshold: two groups along x and y axes.
    images = [{"id": i} for i in range(1, 7)]
    emb = {
        1: _emb([1.0, 0.0]),
        2: _emb([0.99, 0.01]),
        3: _emb([0.98, 0.02]),
        4: _emb([0.0, 1.0]),
        5: _emb([0.01, 0.99]),
        6: _emb([0.02, 0.98]),
    }
    leaves = compute_leaf_substacks(images, emb, 0.05)
    id_sets = sorted([sorted(img["id"] for img in g) for g in leaves])
    assert id_sets == [[1, 2, 3], [4, 5, 6]]
    assert sum(len(g) for g in leaves) == 6


def test_compute_leaf_substacks_single_image():
    images = [{"id": 1}]
    out = compute_leaf_substacks(images, {}, 0.05)
    assert len(out) == 1 and out[0][0]["id"] == 1


def _tl_cfg(threshold=0.05):
    return TwoLevelConfig(
        picks_per_substack=1,
        max_picks_per_stack=20,
        level1=TwoLevelLevelConfig("mobilenet_v2_imagenet_gap", 0.15),
        level2=TwoLevelLevelConfig("openclip_l14_laion2b_image", threshold),
        diversity_enabled=False,
        score_field="score_general",
    )


def _sort_key(img):
    return (-float(img.get("score_general") or 0), int(img.get("id") or 0))


def test_process_stack_two_level_shapes_and_pick_cap():
    # Two visually distinct leaves; picks_per_substack=1 -> one pick per leaf.
    images = [{"id": i, "score_general": 0.5 + i / 100.0, "file_path": f"/p/{i}.nef"} for i in range(1, 7)]
    emb = {
        1: _emb([1.0, 0.0]), 2: _emb([0.99, 0.01]), 3: _emb([0.98, 0.02]),
        4: _emb([0.0, 1.0]), 5: _emb([0.01, 0.99]), 6: _emb([0.02, 0.98]),
    }
    tl_cfg = _tl_cfg()
    rows, decisions, leaf_count = process_stack_two_level(42, images, emb, tl_cfg, _sort_key)

    assert leaf_count == 2
    assert len(rows) == 2
    for r in rows:
        assert r["stack_id"] == 42
        assert r["level2_visual_space"] == "openclip_l14_laion2b_image"
        assert r["level2_semantic_space"] is None
        assert r["policy_version"] == "2.0"
        assert r["best_image_id"] in {img["id"] for img in images}

    picks = sum(1 for _, d, _ in decisions if d == "pick")
    assert picks == 2  # one per leaf
    assert picks <= tl_cfg.max_picks_per_stack
    assert {img_id for img_id, _, _ in decisions} == {img["id"] for img in images}


def test_process_stack_two_level_missing_embeddings_single_leaf():
    # No vectors -> single fallback leaf -> capped picks, still well-formed.
    images = [{"id": i, "score_general": float(i), "file_path": ""} for i in range(1, 5)]
    rows, decisions, leaf_count = process_stack_two_level(7, images, {}, _tl_cfg(), _sort_key)
    assert leaf_count == 1
    assert len(rows) == 1
    assert sum(1 for _, d, _ in decisions if d == "pick") <= _tl_cfg().max_picks_per_stack
