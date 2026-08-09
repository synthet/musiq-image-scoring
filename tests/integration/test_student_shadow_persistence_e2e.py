"""Postgres E2E: student shadow rows persist without touching teacher composites.

Requires configured test PostgreSQL. Marked postgres so the fast suite skips it.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.postgres, pytest.mark.db]


def test_student_rows_persist_separately_with_shadow_and_version():
    pytest.skip("Requires test Postgres + seeded images; implement against e2e DB when campaign starts")


def test_teacher_rows_and_image_composites_are_unchanged():
    pytest.skip("Requires test Postgres; assert score_general unchanged after student shadow run")


def test_rerun_upserts_only_same_versioned_proxy_names():
    pytest.skip("Requires test Postgres; assert (image_id, model_name) upsert semantics")
