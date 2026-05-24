import pytest

from modules.run_modes import (
    CANONICAL_RUN_MODE,
    infer_run_mode,
    normalize_run_mode,
    resolve_run_mode_flags,
)


def test_default_run_mode():
    assert infer_run_mode(None, run_mode_explicit=False) == CANONICAL_RUN_MODE
    assert normalize_run_mode(None) == CANONICAL_RUN_MODE
    assert normalize_run_mode("") == CANONICAL_RUN_MODE


def test_legacy_run_mode_aliases_map_to_canonical():
    for legacy in (
        "process_unprocessed_or_empty",
        "process_all_overwrite",
        "validate_and_repair",
    ):
        assert normalize_run_mode(legacy) == CANONICAL_RUN_MODE


def test_explicit_invalid_run_mode_raises():
    with pytest.raises(ValueError):
        normalize_run_mode("invalid_mode")


def test_resolve_run_mode_flags_returns_expected_shape():
    flags = resolve_run_mode_flags(CANONICAL_RUN_MODE)
    assert flags == {
        "skip_done": False,
        "skip_existing": False,
        "force_rerun": False,
        "fix_incomplete_stages": True,
        "overwrite": False,
        "force_rescan": False,
    }
