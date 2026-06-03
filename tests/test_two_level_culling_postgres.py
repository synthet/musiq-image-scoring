"""Postgres tests for two-level culling schema and pick cap."""

from __future__ import annotations

import pytest

from modules.selection_policy import classify_best_m
from modules.two_level_culling import SubStackSlotInfo, allocate_picks_uniform

pytestmark = [pytest.mark.postgres]


@pytest.fixture(autouse=True)
def _postgres_clean(postgres_test_session, clean_postgres):
    yield


def test_sub_stacks_table_exists():
    from modules import db_postgres

    row = db_postgres.execute_select_one(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = %s",
        ("sub_stacks",),
    )
    assert row is not None


def test_images_sub_stack_id_column():
    from modules import db_postgres

    row = db_postgres.execute_select_one(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'images' AND column_name = %s",
        ("sub_stack_id",),
    )
    assert row is not None


def test_create_sub_stacks_batch_and_clear():
    from modules import db

    folder_id = db.get_or_create_folder("/test/two_level_culling")
    assert folder_id

    img_ids = []
    for i in range(4):
        iid, _ = db.register_image_for_import(
            f"/test/two_level_culling/img_{i}.jpg",
            f"img_{i}.jpg",
            "jpg",
            folder_id,
        )
        img_ids.append(iid)

    stack_ok, _ = db.create_stacks_batch(
        [{"name": "tl_test_stack", "best_image_id": img_ids[0], "image_ids": img_ids}]
    )
    assert stack_ok
    stacks = db.get_connector().query(
        "SELECT id FROM stacks ORDER BY id DESC LIMIT 1"
    )
    stack_id = list(stacks)[0]["id"]

    sub_ok, msg = db.create_sub_stacks_batch(
        [
            {
                "stack_id": stack_id,
                "name": "sub_a",
                "best_image_id": img_ids[0],
                "level1_space": "mobilenet_v2_imagenet_gap",
                "level2_visual_space": "mobilenet_v2_imagenet_gap",
                "level2_semantic_space": "clip_vit_b32_image",
                "policy_version": "2.0",
                "image_ids": img_ids[:2],
            },
            {
                "stack_id": stack_id,
                "name": "sub_b",
                "best_image_id": img_ids[2],
                "level1_space": "mobilenet_v2_imagenet_gap",
                "level2_visual_space": "mobilenet_v2_imagenet_gap",
                "level2_semantic_space": "clip_vit_b32_image",
                "policy_version": "2.0",
                "image_ids": img_ids[2:],
            },
        ]
    )
    assert sub_ok, msg

    substacks = db.get_substacks_for_stack(stack_id)
    assert len(substacks) == 2

    rows = list(
        db.get_connector().query(
            "SELECT sub_stack_id FROM images WHERE stack_id = ? ORDER BY id",
            (stack_id,),
        )
    )
    assert all(r["sub_stack_id"] is not None for r in rows)

    ok, clear_msg = db.clear_sub_stacks_for_folder("/test/two_level_culling")
    assert ok, clear_msg
    assert len(db.get_substacks_for_stack(stack_id)) == 0


def test_pick_cap_never_exceeds_n():
    for c in (1, 4, 10, 25):
        infos = [SubStackSlotInfo(size=8, top_score=float(i)) for i in range(c)]
        slots = allocate_picks_uniform(infos, m=3, n=20)
        assert sum(slots) <= 20
        pick_count = sum(
            list(classify_best_m(list(range(slot)), m=slot).values()).count("pick")
            for slot in slots
        )
        assert pick_count <= 20
