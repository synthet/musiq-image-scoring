"""Regression: scan_stop/nef_cache must be parameters of the extracted helper.

Commit 4e2cac3 lifted the per-file loop body out of _run_batch_internal into
_process_indexing_file but left scan_stop and nef_cache behind as locals of the
former, causing:
  NameError: name 'scan_stop' is not defined
on *every* image (both the existing-image and new-image branches), so runs
reported completed with images_processed=0 / images_failed=N, and the post-run
audit re-queued the same work forever.

Same commit, same failure mode as test_runner_progress_interval.py.
"""
import inspect

from modules import indexing_runner


def test_scan_stop_and_nef_cache_are_parameters_not_globals():
    fn = indexing_runner.IndexingRunner._process_indexing_file
    params = inspect.signature(fn).parameters

    # Must be accepted as arguments...
    assert "scan_stop" in params
    assert "nef_cache" in params

    # ...and never resolved as module globals (that is the NameError).
    assert "scan_stop" not in fn.__code__.co_names
    assert "nef_cache" not in fn.__code__.co_names


def test_batch_forwards_scan_stop_and_nef_cache():
    """_run_batch_internal must pass scan_stop/nef_cache through, not drop them."""
    src = inspect.getsource(indexing_runner.IndexingRunner._run_batch_internal)
    assert "scan_stop=scan_stop" in src
    assert "nef_cache=nef_cache" in src


def test_nef_cache_defaults_to_usable_mapping():
    """The helper contract is Dict[str, bool]; a None default must be normalized."""
    params = inspect.signature(
        indexing_runner.IndexingRunner._process_indexing_file
    ).parameters
    assert params["nef_cache"].default is None
    assert "nef_cache = {}" in inspect.getsource(
        indexing_runner.IndexingRunner._process_indexing_file
    )
