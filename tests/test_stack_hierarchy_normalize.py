"""Postgres tests for normalize_stack_hierarchy and removal cleanup."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.postgres]


@pytest.fixture(autouse=True)
def _postgres_clean(postgres_test_session, clean_postgres):
    yield


def _register_images(folder_id: int, n: int) -> list[int]:
    from modules import db

    ids = []
    for i in range(n):
        iid, _ = db.register_image_for_import(
            f"/test/hierarchy_norm/img_{i}.jpg",
            f"img_{i}.jpg",
            "jpg",
            folder_id,
        )
        ids.append(iid)
    return ids


def test_normalize_dissolves_singleton_root_stack():
    from modules import db

    folder_id = db.get_or_create_folder("/test/hierarchy_norm_singleton")
    img_ids = _register_images(folder_id, 2)
    db.create_stacks_batch(
        [{"name": "singleton_test", "best_image_id": img_ids[0], "image_ids": [img_ids[0]]}]
    )
    stack_id = db.get_connector().query_one(
        "SELECT id FROM stacks ORDER BY id DESC LIMIT 1"
    )["id"]

    result = db.normalize_stack_hierarchy(int(stack_id))
    assert result["action"] == "dissolved_singleton"

    row = db.get_connector().query_one(
        "SELECT stack_id, sub_stack_id FROM images WHERE id = ?",
        (img_ids[0],),
    )
    assert row["stack_id"] is None
    assert row["sub_stack_id"] is None


def test_normalize_collapses_single_leaf_stack():
    from modules import db

    folder_id = db.get_or_create_folder("/test/hierarchy_norm_single_leaf")
    img_ids = _register_images(folder_id, 3)
    db.create_stacks_batch(
        [{"name": "single_leaf_test", "best_image_id": img_ids[0], "image_ids": img_ids}]
    )
    stack_id = int(
        db.get_connector().query_one("SELECT id FROM stacks ORDER BY id DESC LIMIT 1")["id"]
    )
    db.create_sub_stacks_batch(
        [
            {
                "stack_id": stack_id,
                "name": "only_leaf",
                "best_image_id": img_ids[0],
                "level1_space": "mobilenet_v2_imagenet_gap",
                "level2_visual_space": "openclip_l14_laion2b_image",
                "level2_semantic_space": None,
                "policy_version": "2.0",
                "image_ids": img_ids,
            }
        ]
    )

    result = db.normalize_stack_hierarchy(stack_id)
    assert result["action"] == "normalized"
    assert "collapsed_single_leaf" in result["details"]["steps"]

    subs = db.get_connector().query(
        "SELECT id FROM sub_stacks WHERE stack_id = ?", (stack_id,)
    )
    assert len(list(subs)) == 0
    for iid in img_ids:
        row = db.get_connector().query_one(
            "SELECT sub_stack_id FROM images WHERE id = ?", (iid,)
        )
        assert row["sub_stack_id"] is None


def test_remove_images_dissolves_to_singleton():
    from modules import db

    folder_id = db.get_or_create_folder("/test/hierarchy_remove_singleton")
    img_ids = _register_images(folder_id, 2)
    db.create_stacks_batch(
        [{"name": "remove_test", "best_image_id": img_ids[0], "image_ids": img_ids}]
    )
    stack_id = int(
        db.get_connector().query_one("SELECT id FROM stacks ORDER BY id DESC LIMIT 1")["id"]
    )

    ok, msg = db.remove_images_from_stack([img_ids[0]])
    assert ok

    remaining = db.get_connector().query_one(
        "SELECT stack_id, sub_stack_id FROM images WHERE id = ?", (img_ids[1],)
    )
    assert remaining["stack_id"] is None
    assert remaining["sub_stack_id"] is None

    stack_row = db.get_connector().query_one("SELECT id FROM stacks WHERE id = ?", (stack_id,))
    assert stack_row is None
