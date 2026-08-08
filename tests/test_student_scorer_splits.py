"""Split leakage / determinism tests (AC-3)."""

from __future__ import annotations

import pytest

from scripts.research.student_scorer.build_splits import (
    assert_no_cross_split_groups,
    assign_splits,
    build_components,
    near_duplicate_leakage,
    splits_to_dict,
)


def _rows():
    # Two bursts that must stay together; plus singletons with capture days
    return [
        {"image_id": 1, "image_hash": "h1", "hash_version": "v1", "burst_uuid": "b1",
         "stack_id": 10, "sub_stack_id": 100, "capture_day": "2024-01-01", "folder_id": 1},
        {"image_id": 2, "image_hash": "h2", "hash_version": "v1", "burst_uuid": "b1",
         "stack_id": 10, "sub_stack_id": 100, "capture_day": "2024-01-01", "folder_id": 1},
        {"image_id": 3, "image_hash": "h3", "hash_version": "v1", "burst_uuid": None,
         "stack_id": 11, "sub_stack_id": 101, "capture_day": "2024-06-01", "folder_id": 2},
        {"image_id": 4, "image_hash": "h4", "hash_version": "v1", "burst_uuid": None,
         "stack_id": 12, "sub_stack_id": 102, "capture_day": "2024-06-02", "folder_id": 2},
        {"image_id": 5, "image_hash": "h5", "hash_version": "v1", "burst_uuid": None,
         "stack_id": 13, "sub_stack_id": 103, "capture_day": "2025-01-01", "folder_id": 3},
        {"image_id": 6, "image_hash": "h6", "hash_version": "v1", "burst_uuid": None,
         "stack_id": 14, "sub_stack_id": 104, "capture_day": "2025-01-02", "folder_id": 3},
        {"image_id": 7, "image_hash": "h7", "hash_version": "v1", "burst_uuid": None,
         "stack_id": 15, "sub_stack_id": 105, "capture_day": "2023-01-01", "folder_id": 4},
        {"image_id": 8, "image_hash": "h8", "hash_version": "v1", "burst_uuid": None,
         "stack_id": 16, "sub_stack_id": 106, "capture_day": "2023-02-01", "folder_id": 5},
    ]


def test_connected_groups_never_cross_splits():
    rows = _rows()
    comps = build_components(rows)
    assert comps[1] == comps[2]  # same burst/stack
    assignments = assign_splits(rows, seed=7)
    assert_no_cross_split_groups(assignments)
    split_of = {a.image_id: a.split for a in assignments}
    assert split_of[1] == split_of[2]


def test_temporal_holdout_precedes_iid_assignment():
    rows = _rows()
    assignments = assign_splits(rows, seed=7, ood_newest_fraction=0.25)
    splits = {a.split for a in assignments}
    assert "ood_test" in splits
    # Newest capture days should be preferred for OOD
    ood_ids = {a.image_id for a in assignments if a.split == "ood_test"}
    assert ood_ids  # non-empty


def test_split_is_seed_deterministic():
    rows = _rows()
    a = splits_to_dict(assign_splits(rows, seed=99))
    b = splits_to_dict(assign_splits(rows, seed=99))
    c = splits_to_dict(assign_splits(rows, seed=100))
    assert a == b
    assert a != c


def test_near_duplicate_leakage_forces_rebuild():
    rows = _rows()
    for r in rows:
        r["embed_sim_cluster"] = None
    # Force a cross-split near-dupe cluster id on images that land in different splits
    assignments = assign_splits(rows, seed=3)
    # Pick two images from different splits if possible
    by_split = {}
    for a in assignments:
        by_split.setdefault(a.split, []).append(a.image_id)
    splits_with_members = [s for s, ids in by_split.items() if ids]
    if len(splits_with_members) < 2:
        pytest.skip("need two splits for leakage test")
    id_a = by_split[splits_with_members[0]][0]
    id_b = by_split[splits_with_members[1]][0]
    for r in rows:
        if r["image_id"] in (id_a, id_b):
            r["embed_sim_cluster"] = "dupe_cluster_1"
    leaks = near_duplicate_leakage(rows, assignments)
    assert leaks
    assert len(leaks[0]["splits"]) > 1
