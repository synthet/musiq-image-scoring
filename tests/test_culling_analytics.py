"""Integration tests for culling analytics (PostgreSQL)."""

import pytest

from modules import config


pytestmark = [pytest.mark.postgres, pytest.mark.db]


@pytest.fixture
def _skip_non_postgres():
    if config.get_database_engine() != "postgres":
        pytest.skip("PostgreSQL engine required")


def test_library_analytics_smoke(_skip_non_postgres):
    from modules.culling_analytics.service import get_library_analytics

    result = get_library_analytics()
    assert result["scope"] == "library"
    assert "stack_size" in result
    assert "flags" in result
    assert result["flags"]["flag_layer"] == "images.pick_status"
    assert "generated_at" in result


def test_stack_analytics_not_found(_skip_non_postgres):
    from modules.culling_analytics.service import get_stack_analytics

    result = get_stack_analytics(999999999)
    assert result.get("error") == "stack_not_found"


def test_session_analytics_not_found(_skip_non_postgres):
    from modules.culling_analytics.service import get_session_analytics

    result = get_session_analytics(999999999)
    assert result.get("error") == "session_not_found"
