"""Unit tests for indexing.nikon_nef_only policy helpers."""

from unittest.mock import patch

from modules.indexing_policy import (
    DEFAULT_INDEXING_EXTENSIONS,
    discovery_extensions,
    filter_image_rows_for_nef_policy,
    logical_roots_from_user_prefixes,
    passes_nikon_nef_policy,
    path_is_under_logical_roots,
)


def test_discovery_default_includes_common_raw_and_raster():
    with patch("modules.indexing_policy.nikon_nef_only_enabled", return_value=False):
        ex = discovery_extensions()
    assert ".nef" in ex
    assert ".jpg" in ex
    assert ex == DEFAULT_INDEXING_EXTENSIONS


def test_discovery_nef_only():
    with patch("modules.indexing_policy.nikon_nef_only_enabled", return_value=True):
        ex = discovery_extensions()
    assert ex == frozenset({".nef"})


def test_passes_nikon_nef_policy_respects_flag():
    with patch("modules.indexing_policy.nikon_nef_only_enabled", return_value=False):
        assert passes_nikon_nef_policy("/x/foo.jpg", "jpeg") is True
    with patch("modules.indexing_policy.nikon_nef_only_enabled", return_value=True):
        assert passes_nikon_nef_policy("/x/foo.jpg", "jpeg") is False
        assert passes_nikon_nef_policy("/x/foo.NEF", None) is True
        assert passes_nikon_nef_policy("/x/foo.jpg", "nef") is True


def test_filter_image_rows_for_nef_policy():
    rows = [
        {"id": 1, "file_path": "/a/x.jpg", "file_type": "jpg"},
        {"id": 2, "file_path": "/a/y.nef", "file_type": "nef"},
    ]
    with patch("modules.indexing_policy.nikon_nef_only_enabled", return_value=True):
        out = filter_image_rows_for_nef_policy(rows)
    assert len(out) == 1
    assert out[0]["id"] == 2


def test_logical_roots_strict_prefix_not_lightroombackup():
    roots = logical_roots_from_user_prefixes(["/mnt/d/Photos/Lightroom"])
    assert path_is_under_logical_roots("/mnt/d/Photos/Lightroom/x.nef", roots)
    assert not path_is_under_logical_roots("/mnt/d/Photos/LightroomBackup/x.nef", roots)


def test_path_is_indexing_excluded_reads_config():
    from modules.indexing_policy import path_is_indexing_excluded

    fake_cfg = {"indexing": {"excluded_paths": ["/tmp/blacklist"]}}
    with patch("modules.config.load_config", return_value=fake_cfg):
        assert path_is_indexing_excluded("/tmp/blacklist/a.jpg")
        assert not path_is_indexing_excluded("/tmp/blacklist_other/a.jpg")
