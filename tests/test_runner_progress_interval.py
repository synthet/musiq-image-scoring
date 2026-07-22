"""Regression: PROGRESS_INTERVAL must be module-scoped for extracted helpers.

Commit 4e2cac3 lifted per-image work into class methods but left
PROGRESS_INTERVAL as a local in _run_batch_internal, causing:
  NameError: name 'PROGRESS_INTERVAL' is not defined
on the first image in metadata/indexing runs.
"""
from modules import indexing_runner, metadata_runner


def test_metadata_progress_interval_is_module_scoped():
    assert metadata_runner.PROGRESS_INTERVAL == 50
    assert "PROGRESS_INTERVAL" in metadata_runner.MetadataRunner._process_metadata_image_row.__code__.co_names
    # Same expression the helpers evaluate — must resolve without NameError.
    assert 50 % metadata_runner.PROGRESS_INTERVAL == 0


def test_indexing_progress_interval_is_module_scoped():
    assert indexing_runner.PROGRESS_INTERVAL == 50
    assert "PROGRESS_INTERVAL" in indexing_runner.IndexingRunner._process_indexing_file.__code__.co_names
    assert 50 % indexing_runner.PROGRESS_INTERVAL == 0
