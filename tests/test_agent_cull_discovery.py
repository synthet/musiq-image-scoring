"""Tests for agent cull discovery eligibility."""

from modules.agent_cull.config import AgentCullConfig
from modules.agent_cull.discovery import (
    GroupCounts,
    build_review_unit_key,
    discover_eligible_units_from_stack_rows,
    is_group_eligible,
)
from modules.culling_analytics.hierarchy import TIER_SINGLETON_ROOT


def _cfg() -> AgentCullConfig:
    return AgentCullConfig()


def test_build_review_unit_key():
    assert build_review_unit_key(5, None) == "stack:5"
    assert build_review_unit_key(5, 9) == "stack:5:sub:9"


def test_eligible_group():
    ok, reason = is_group_eligible(
        GroupCounts(total=5, picked=3, rejected=2, neutral=0, usable=5),
        _cfg(),
    )
    assert ok is True
    assert reason is None


def test_skip_large_group():
    ok, reason = is_group_eligible(
        GroupCounts(total=10, picked=5, rejected=3, usable=10),
        _cfg(),
    )
    assert ok is False
    assert reason == "group_too_large"


def test_skip_no_rejected():
    ok, reason = is_group_eligible(
        GroupCounts(total=4, picked=2, rejected=0, usable=4),
        _cfg(),
    )
    assert ok is False
    assert reason == "no_rejected_images"


def test_skip_no_picked():
    ok, reason = is_group_eligible(
        GroupCounts(total=4, picked=0, rejected=2, usable=4),
        _cfg(),
    )
    assert ok is False
    assert reason == "no_picked_images"


def test_eligible_picked_lt_rejected():
    ok, reason = is_group_eligible(
        GroupCounts(total=5, picked=1, rejected=2, usable=5),
        _cfg(),
    )
    assert ok is True
    assert reason is None


def test_skip_singleton_root():
    ok, reason = is_group_eligible(
        GroupCounts(total=1, picked=0, rejected=1, usable=1),
        _cfg(),
        hierarchy_tier=TIER_SINGLETON_ROOT,
    )
    assert ok is False
    assert reason == "singleton_root"


def test_discover_flat_stack_eligible():
    rows = [
        {"id": 1, "pick_status": 1, "file_path": "/tmp/a.jpg"},
        {"id": 2, "pick_status": 1, "file_path": "/tmp/b.jpg"},
        {"id": 3, "pick_status": -1, "file_path": "/tmp/c.jpg"},
    ]
    units = discover_eligible_units_from_stack_rows(
        10,
        rows,
        _cfg(),
        is_usable_fn=lambda _r: True,
    )
    assert len(units) == 1
    assert units[0].rejected_ids == (3,)
    assert units[0].picked_ids == (1, 2)


def test_discover_substack_three_picks_six_rejects():
    rows = []
    for i in range(1, 4):
        rows.append({"id": i, "pick_status": 1, "sub_stack_id": 1, "file_path": f"/tmp/p{i}.jpg"})
    for i in range(4, 10):
        rows.append({"id": i, "pick_status": -1, "sub_stack_id": 1, "file_path": f"/tmp/r{i}.jpg"})
    units = discover_eligible_units_from_stack_rows(
        23243,
        rows,
        _cfg(),
        leaf_count=1,
        images_with_substack=9,
        is_usable_fn=lambda _r: True,
    )
    assert len(units) == 1
    assert units[0].sub_stack_id == 1
    assert len(units[0].picked_ids) == 3
    assert len(units[0].rejected_ids) == 6


def test_discover_skips_ineligible():
    rows = [
        {"id": 1, "pick_status": -1, "file_path": "/tmp/a.jpg"},
        {"id": 2, "pick_status": -1, "file_path": "/tmp/b.jpg"},
    ]
    units = discover_eligible_units_from_stack_rows(
        10,
        rows,
        _cfg(),
        is_usable_fn=lambda _r: True,
    )
    assert units == []
