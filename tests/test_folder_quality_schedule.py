"""Unit tests for modules.folder_quality_schedule (no DB)."""

import pytest

pytest.skip("modules.folder_quality_schedule not yet implemented", allow_module_level=True)

try:
    from modules.folder_quality_schedule import stages_for_quality_row
except ModuleNotFoundError:
    # Module not implemented yet; tests will be skipped
    stages_for_quality_row = None


def test_stages_for_quality_row_scoring_only():
    row = {
        "scoring_incomplete": 3,
        "thumb_missing": 0,
        "bird_missing_species": 0,
        "stack_issue": 0,
    }
    assert stages_for_quality_row(row) == ["indexing", "metadata", "scoring"]


def test_stages_for_quality_row_includes_culling_when_stack():
    row = {
        "scoring_incomplete": 0,
        "thumb_missing": 0,
        "bird_missing_species": 0,
        "stack_issue": 1,
    }
    assert stages_for_quality_row(row) == ["indexing", "metadata", "scoring", "culling"]


def test_stages_for_quality_row_bird_only_keywords_and_bird_species():
    row = {
        "scoring_incomplete": 0,
        "thumb_missing": 0,
        "bird_missing_species": 1,
        "stack_issue": 0,
    }
    assert stages_for_quality_row(row) == ["keywords", "bird_species"]
