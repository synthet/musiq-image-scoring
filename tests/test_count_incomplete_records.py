"""Sanity checks for scoring-incomplete COUNT vs bounded listing."""

from __future__ import annotations

import pytest


@pytest.mark.db
def test_count_incomplete_records_matches_list_len():
    """COUNT(*) should match len(get_incomplete_records(N)) when N >= count."""
    from modules import db

    total = int(db.count_incomplete_records())
    if total > 5000:
        pytest.skip("too many incomplete rows for full-list compare in CI")
    rows = db.get_incomplete_records(total + 100)
    assert len(rows) == total
