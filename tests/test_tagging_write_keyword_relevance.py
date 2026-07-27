"""Regression: write_keyword_relevance must be bound in _run_batch_internal.

Commit 4e2cac3 extracted per-image tagging into _process_tagging_image_row but
dropped the config binding (and phase-policy filter / counters) above the loop,
causing:
  NameError: name 'write_keyword_relevance' is not defined
on keywords/tagging runs.
"""
import inspect

import pytest

pytest.importorskip("torch")

from modules.tagging import TaggingRunner


def test_run_batch_internal_binds_write_keyword_relevance():
    src = inspect.getsource(TaggingRunner._run_batch_internal)
    assert "write_keyword_relevance = bool(" in src
    assert "get_config_section('tagging')" in src
    assert "write_keyword_relevance=write_keyword_relevance" in src
    # Counters required by the extracted helper must also be initialized.
    assert "processed_count = 0" in src
    assert "processed_folders = set()" in src
    # Phase-policy filter must run before the per-image helper loop.
    assert "explain_phase_run_decision(" in src
    names = TaggingRunner._run_batch_internal.__code__.co_names
    assert "write_keyword_relevance" in names or "get_config_section" in names
