"""Unit tests for the soft-retry path resolver in modules.indexing_runner.

The indexing runner used to fail fast when a WSL ``/mnt/<drive>/...`` path
transiently disappeared (e.g. drvfs blip after heavy host I/O). The wrapper
``_resolve_scope_input_path_with_retry`` re-tries with backoff for paths that
look like network/mount paths, and is a no-op for plain local paths.
"""

from __future__ import annotations

from unittest.mock import patch

from modules.indexing_runner import (
    _looks_like_transient_mount_path,
    _resolve_scope_input_path_with_retry,
)


def _silent_log(level, msg, image_id=None):
    return None


def test_looks_like_transient_mount_path_wsl():
    assert _looks_like_transient_mount_path("/mnt/d/Photos/2026") is True


def test_looks_like_transient_mount_path_unc():
    assert _looks_like_transient_mount_path("//server/share/dir") is True
    assert _looks_like_transient_mount_path(r"\\server\share\dir") is True


def test_looks_like_transient_mount_path_local():
    assert _looks_like_transient_mount_path("/home/user/photos") is False
    assert _looks_like_transient_mount_path(r"D:\Photos") is False
    assert _looks_like_transient_mount_path("") is False


def test_resolve_with_retry_returns_immediately_on_success():
    with patch(
        "modules.indexing_runner.resolve_scope_input_path",
        return_value=("/mnt/d/Photos/2026", ["/mnt/d/Photos/2026"]),
    ) as resolver, patch("time.sleep") as sleeper:
        resolved, tried = _resolve_scope_input_path_with_retry(
            "/mnt/d/Photos/2026", log=_silent_log
        )
    assert resolved == "/mnt/d/Photos/2026"
    assert tried == ["/mnt/d/Photos/2026"]
    assert resolver.call_count == 1
    sleeper.assert_not_called()


def test_resolve_with_retry_retries_and_eventually_succeeds():
    sequence = [
        (None, ["/mnt/d/foo"]),
        (None, ["/mnt/d/foo"]),
        ("/mnt/d/foo", ["/mnt/d/foo"]),
    ]
    with patch(
        "modules.indexing_runner.resolve_scope_input_path",
        side_effect=sequence,
    ) as resolver, patch("time.sleep") as sleeper:
        resolved, _ = _resolve_scope_input_path_with_retry(
            "/mnt/d/foo", log=_silent_log, max_attempts=3, base_delay=0.0
        )
    assert resolved == "/mnt/d/foo"
    assert resolver.call_count == 3
    assert sleeper.call_count == 2


def test_resolve_with_retry_gives_up_after_max_attempts():
    with patch(
        "modules.indexing_runner.resolve_scope_input_path",
        return_value=(None, ["/mnt/d/missing"]),
    ) as resolver, patch("time.sleep"):
        resolved, tried = _resolve_scope_input_path_with_retry(
            "/mnt/d/missing", log=_silent_log, max_attempts=3, base_delay=0.0
        )
    assert resolved is None
    assert tried == ["/mnt/d/missing"]
    assert resolver.call_count == 3


def test_resolve_with_retry_does_not_retry_local_paths():
    with patch(
        "modules.indexing_runner.resolve_scope_input_path",
        return_value=(None, [r"D:\Photos\missing"]),
    ) as resolver, patch("time.sleep") as sleeper:
        resolved, _ = _resolve_scope_input_path_with_retry(
            r"D:\Photos\missing", log=_silent_log, max_attempts=3, base_delay=0.0
        )
    assert resolved is None
    assert resolver.call_count == 1
    sleeper.assert_not_called()
