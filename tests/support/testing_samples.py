"""
Discover image files under the local testing samples tree (NEF/JPEG/PNG/etc.).

Default root: ``NEF_TEST_SAMPLES_ROOT`` env var, else ``tests/fixtures/testing_samples``
under the repository root (see ``modules/testing_samples_paths.py``).
"""
from __future__ import annotations

import os
from typing import List

from modules.testing_samples_paths import default_testing_samples_root

DEFAULT_TESTING_SAMPLES_ROOT = default_testing_samples_root()

# Extensions commonly used under the fixtures tree + generic rasters for mixed trees
SAMPLE_IMAGE_EXTENSIONS = frozenset(
    {
        ".nef",
        ".nrw",
        ".arw",
        ".cr2",
        ".cr3",
        ".dng",
        ".jpg",
        ".jpeg",
        ".png",
        ".tif",
        ".tiff",
        ".webp",
    }
)


def testing_samples_root() -> str:
    return os.environ.get("NEF_TEST_SAMPLES_ROOT", DEFAULT_TESTING_SAMPLES_ROOT)


def list_sample_image_files(root: str | None = None) -> List[str]:
    """Sorted absolute paths to sample images under ``root`` (empty if missing)."""
    root = os.path.abspath(os.path.normpath(root or testing_samples_root()))
    if not os.path.isdir(root):
        return []
    found: List[str] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in sorted(filenames):
            ext = os.path.splitext(name)[1].lower()
            if ext not in SAMPLE_IMAGE_EXTENSIONS:
                continue
            full = os.path.join(dirpath, name)
            if os.path.isfile(full):
                found.append(os.path.abspath(full))
    return sorted(found)


def require_sample_files(min_count: int = 1) -> List[str]:
    """Return paths or raise pytest.skip if root missing or not enough files."""
    import pytest

    paths = list_sample_image_files()
    root = testing_samples_root()
    if not os.path.isdir(root):
        pytest.skip(f"Testing samples root not found: {root}")
    if len(paths) < min_count:
        pytest.skip(
            f"Need at least {min_count} sample image(s) under {root}; "
            f"found {len(paths)}. See scripts/python/NEF_TESTING_SAMPLES_URLS.md"
        )
    return paths
