import pytest

from modules.run_modes import infer_run_mode, resolve_run_mode_flags


def test_infer_run_mode_from_legacy_flags_defaults_to_unprocessed():
    assert (
        infer_run_mode(
            None,
            run_mode_explicit=False,
            skip_done=None,
            force_rerun=None,
            fix_incomplete_stages=None,
        )
        == "process_unprocessed_or_empty"
    )


@pytest.mark.parametrize(
    ("skip_done", "force_rerun", "fix_incomplete_stages", "expected"),
    [
        (True, False, False, "process_unprocessed_or_empty"),
        (False, False, False, "process_all_overwrite"),
        (True, True, False, "process_all_overwrite"),
        (True, False, True, "validate_and_repair"),
    ],
)
def test_infer_run_mode_from_legacy_flag_matrix(
    skip_done, force_rerun, fix_incomplete_stages, expected
):
    assert (
        infer_run_mode(
            None,
            run_mode_explicit=False,
            skip_done=skip_done,
            force_rerun=force_rerun,
            fix_incomplete_stages=fix_incomplete_stages,
        )
        == expected
    )


def test_explicit_run_mode_ignores_conflicting_legacy_booleans():
    assert (
        infer_run_mode(
            "process_unprocessed_or_empty",
            run_mode_explicit=True,
            skip_done=False,
            force_rerun=True,
            fix_incomplete_stages=True,
        )
        == "process_unprocessed_or_empty"
    )


def test_explicit_invalid_run_mode_raises():
    with pytest.raises(ValueError):
        infer_run_mode("invalid_mode", run_mode_explicit=True)


@pytest.mark.parametrize(
    "run_mode",
    [
        "process_all_overwrite",
        "process_unprocessed_or_empty",
        "validate_and_repair",
    ],
)
def test_resolve_run_mode_flags_returns_expected_shape(run_mode):
    flags = resolve_run_mode_flags(run_mode)
    assert {
        "skip_done",
        "skip_existing",
        "force_rerun",
        "fix_incomplete_stages",
        "overwrite",
        "force_rescan",
    }.issubset(flags.keys())
