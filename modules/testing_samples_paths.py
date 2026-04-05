"""Default path for NEF / raster test fixtures (repo-relative).

Override with env ``NEF_TEST_SAMPLES_ROOT`` where supported (see ``tests.support.testing_samples``).
"""
from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    """Repository root (directory containing ``modules/``)."""
    return Path(__file__).resolve().parent.parent


def default_testing_samples_root() -> str:
    return str(repo_root() / "tests" / "fixtures" / "testing_samples")
