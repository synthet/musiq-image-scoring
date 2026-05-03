"""Unit tests for ``modules.sub_clustering.compute_sub_clusters``.

Pure-compute, no DB, no ML models. Skipped if sklearn/numpy aren't available.
"""

from __future__ import annotations

import math

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("sklearn")

from modules.sub_clustering import (
    assign_decisions_in_stack,
    compute_sub_clusters,
    iter_sub_cluster_assignments,
)


def _emb_bytes(vec):
    return np.asarray(vec, dtype=np.float32).tobytes()


def test_empty_input_returns_empty():
    assert compute_sub_clusters([], {}, distance_threshold=0.05) == []


def test_single_image_returns_singleton_subcluster():
    images = [{"id": 1}]
    out = compute_sub_clusters(images, {1: _emb_bytes([1.0, 0.0])}, distance_threshold=0.05)
    assert len(out) == 1 and len(out[0]) == 1 and out[0][0]["id"] == 1


def test_two_distinct_groups_split_under_tight_threshold():
    # Two clearly distinct directions in 2D.
    a1 = [1.0, 0.0]
    a2 = [0.99, 0.01]
    b1 = [0.0, 1.0]
    b2 = [0.01, 0.99]
    images = [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}]
    embs = {1: _emb_bytes(a1), 2: _emb_bytes(a2), 3: _emb_bytes(b1), 4: _emb_bytes(b2)}
    out = compute_sub_clusters(images, embs, distance_threshold=0.05)
    # Expect two sub-clusters; ids {1,2} vs {3,4} regardless of order.
    assert len(out) == 2
    sets = sorted([sorted(img["id"] for img in g) for g in out])
    assert sets == [[1, 2], [3, 4]]


def test_loose_threshold_collapses_to_one_subcluster():
    images = [{"id": 1}, {"id": 2}, {"id": 3}]
    embs = {
        1: _emb_bytes([1.0, 0.0]),
        2: _emb_bytes([0.0, 1.0]),
        3: _emb_bytes([0.5, 0.5]),
    }
    # A very loose threshold (1.5) should fold everything into one bucket.
    out = compute_sub_clusters(images, embs, distance_threshold=1.5)
    assert len(out) == 1
    assert sorted(img["id"] for img in out[0]) == [1, 2, 3]


def test_missing_embeddings_routed_to_fallback_bucket():
    images = [{"id": 1}, {"id": 2}, {"id": 3}]
    embs = {
        1: _emb_bytes([1.0, 0.0]),
        2: _emb_bytes([0.99, 0.01]),
        # 3 has no embedding
    }
    out = compute_sub_clusters(images, embs, distance_threshold=0.05)
    # Two sub-clusters: the valid pair, and a fallback bucket for the missing one.
    assert len(out) == 2
    fallback = next(g for g in out if any(im["id"] == 3 for im in g))
    assert [im["id"] for im in fallback] == [3]


def test_all_missing_embeddings_become_single_fallback():
    images = [{"id": 1}, {"id": 2}]
    out = compute_sub_clusters(images, {}, distance_threshold=0.05)
    assert len(out) == 1
    assert sorted(im["id"] for im in out[0]) == [1, 2]


def test_iter_sub_cluster_assignments_indexes_groups():
    images = [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}]
    embs = {
        1: _emb_bytes([1.0, 0.0]),
        2: _emb_bytes([0.99, 0.01]),
        3: _emb_bytes([0.0, 1.0]),
        4: _emb_bytes([0.01, 0.99]),
    }
    out = compute_sub_clusters(images, embs, distance_threshold=0.05)
    assignments = iter_sub_cluster_assignments(out)
    # Each id present, exactly two distinct cluster indices.
    assert set(assignments) == {1, 2, 3, 4}
    assert len(set(assignments.values())) == 2
    # Same-bucket pairs share an index.
    assert assignments[1] == assignments[2]
    assert assignments[3] == assignments[4]
    assert assignments[1] != assignments[3]


def test_per_subcluster_pick_quota_changes_outcome():
    """End-to-end policy check: 38% quota *per sub-cluster* keeps the best of
    each visually-distinct group rather than only the global top scorers.

    Stack of 5 images: 3 near-duplicates + 2 distinct frames. With a single
    flat 38% split (= ceil(5*0.38) = 2) you'd typically pick the top two
    from the dominant cluster and drop both diverse frames. Per-sub-cluster
    quota guarantees at least one keeper per visually distinct group.
    """
    # Three near-identical "burst" frames pointed in direction A:
    cluster_a = [
        {"id": 10, "score_general": 0.92},
        {"id": 11, "score_general": 0.91},
        {"id": 12, "score_general": 0.90},
    ]
    # Two distinct frames pointed in direction B:
    cluster_b = [
        {"id": 20, "score_general": 0.70},
        {"id": 21, "score_general": 0.60},
    ]

    images = cluster_a + cluster_b
    embs = {
        10: _emb_bytes([1.0, 0.0]),
        11: _emb_bytes([0.99, 0.01]),
        12: _emb_bytes([0.98, 0.02]),
        20: _emb_bytes([0.0, 1.0]),
        21: _emb_bytes([0.01, 0.99]),
    }
    sub_groups = compute_sub_clusters(images, embs, distance_threshold=0.05)
    assert len(sub_groups) == 2

    picks: list[int] = []
    for sub in sub_groups:
        sorted_sub = sorted(sub, key=lambda im: -im["score_general"])
        k = math.ceil(len(sorted_sub) * 0.38)
        picks.extend(im["id"] for im in sorted_sub[:k])

    # The top of the B cluster (id 20) survives because it's now competing
    # only against id 21, not against the higher-scored A cluster.
    assert 20 in picks
    # And the top of the A cluster (id 10) is still picked.
    assert 10 in picks


# ---------------------------------------------------------------------------
# assign_decisions_in_stack — shared helper for SelectionService + backfill
# ---------------------------------------------------------------------------


def test_assign_decisions_returns_tuples_per_image():
    images = [
        {"id": 1, "score_general": 0.9, "file_path": "/a.jpg"},
        {"id": 2, "score_general": 0.8, "file_path": "/b.jpg"},
        {"id": 3, "score_general": 0.7, "file_path": "/c.jpg"},
        {"id": 4, "score_general": 0.6, "file_path": "/d.jpg"},
    ]
    embs = {
        1: _emb_bytes([1.0, 0.0]),
        2: _emb_bytes([0.99, 0.01]),
        3: _emb_bytes([0.0, 1.0]),
        4: _emb_bytes([0.01, 0.99]),
    }
    decisions = assign_decisions_in_stack(
        images, embs, distance_threshold=0.05, frac=0.33,
    )
    # Every image accounted for
    assert {d[0] for d in decisions} == {1, 2, 3, 4}
    # File paths are pass-through
    paths = {d[0]: d[2] for d in decisions}
    assert paths[1] == "/a.jpg" and paths[3] == "/c.jpg"
    # Per-sub-cluster bands: each cluster of size 2 → 1 pick + 1 neutral
    # under classify_sorted_ids (n=2 small-stack rule). So at least one pick
    # per visually distinct cluster.
    by_decision = {d: [] for d in ("pick", "reject", "neutral")}
    for img_id, decision, _ in decisions:
        by_decision[decision].append(img_id)
    # 1 (top of A) and 3 (top of B) should both be picks, not just 1.
    assert 1 in by_decision["pick"]
    assert 3 in by_decision["pick"]


def test_assign_decisions_handles_empty_input():
    assert assign_decisions_in_stack([], {}, distance_threshold=0.05) == []


def test_assign_decisions_singleton_yields_neutral():
    decisions = assign_decisions_in_stack(
        [{"id": 42, "score_general": 0.5, "file_path": "/x.jpg"}],
        {42: _emb_bytes([1.0, 0.0])},
        distance_threshold=0.05,
    )
    assert decisions == [(42, "neutral", "/x.jpg")]
