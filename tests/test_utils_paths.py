"""
Tests for path utilities in modules/utils.py.

Covers convert_path_to_local, convert_path_to_wsl, compute_file_hash,
resolve_file_path (all 4 strategies), and get_image_creation_time.
"""

import hashlib
import os
import platform
import pytest

from modules import utils


# ---------------------------------------------------------------------------
# convert_path_to_local
# ---------------------------------------------------------------------------

def test_convert_path_to_local_wsl_to_windows(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    result = utils.convert_path_to_local("/mnt/d/Photos/img.jpg")
    assert result == "D:/Photos/img.jpg"


def test_convert_path_to_local_wsl_double_slash(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    result = utils.convert_path_to_local("/mnt//d/Photos/img.jpg")
    assert result == "D:/Photos/img.jpg"


def test_convert_path_to_local_wsl_drive_uppercase(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    result = utils.convert_path_to_local("/mnt/c/Users/test.nef")
    assert result == "C:/Users/test.nef"


def test_convert_path_to_local_already_windows_unchanged(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    result = utils.convert_path_to_local("D:/Photos/img.jpg")
    assert result == "D:/Photos/img.jpg"


def test_convert_path_to_local_windows_path_on_linux(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    result = utils.convert_path_to_local("D:/Photos/img.jpg")
    assert result == "/mnt/d/Photos/img.jpg"


def test_convert_path_to_local_windows_backslash_on_linux(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    result = utils.convert_path_to_local("D:\\Photos\\img.jpg")
    assert result == "/mnt/d/Photos/img.jpg"


def test_convert_path_to_local_native_linux_path_unchanged(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    result = utils.convert_path_to_local("/home/user/photos/img.jpg")
    assert result == "/home/user/photos/img.jpg"


# ---------------------------------------------------------------------------
# Docker host→container project root remap
# ---------------------------------------------------------------------------

def _patch_host_project_env(monkeypatch, base_dir: str):
    monkeypatch.setenv("IMAGE_SCORING_HOST_PROJECT_WSL", "/mnt/d/Projects/image-scoring-backend")
    monkeypatch.setenv("IMAGE_SCORING_HOST_PROJECT_WIN", "D:\\Projects\\image-scoring-backend")
    from modules import config
    monkeypatch.setattr(config, "BASE_DIR", base_dir)


def test_convert_path_to_local_remaps_wsl_host_project_to_container_root(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    _patch_host_project_env(monkeypatch, "/app")
    result = utils.convert_path_to_local(
        "/mnt/d/Projects/image-scoring-backend/thumbnails/b6/abc.jpg"
    )
    assert result.replace("\\", "/") == "/app/thumbnails/b6/abc.jpg"


def test_convert_path_to_local_remaps_windows_host_project_to_container_root(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    _patch_host_project_env(monkeypatch, "/app")
    result = utils.convert_path_to_local(
        "D:\\Projects\\image-scoring-backend\\thumbnails\\b6\\abc.jpg"
    )
    assert result.replace("\\", "/") == "/app/thumbnails/b6/abc.jpg"


def test_convert_path_to_local_no_remap_outside_project(monkeypatch):
    """Paths outside the host project root are not touched by the Docker remap."""
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    _patch_host_project_env(monkeypatch, "/app")
    result = utils.convert_path_to_local("/mnt/d/Photos/Z8/DSC_4093.NEF")
    # No remap → falls through to existing Linux behavior (no Windows-drive prefix).
    assert result == "/mnt/d/Photos/Z8/DSC_4093.NEF"


def test_convert_path_to_local_remap_disabled_when_env_unset(monkeypatch):
    monkeypatch.delenv("IMAGE_SCORING_HOST_PROJECT_WSL", raising=False)
    monkeypatch.delenv("IMAGE_SCORING_HOST_PROJECT_WIN", raising=False)
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    result = utils.convert_path_to_local(
        "/mnt/d/Projects/image-scoring-backend/thumbnails/b6/abc.jpg"
    )
    # Without env vars, no remap. Linux pass-through.
    assert result == "/mnt/d/Projects/image-scoring-backend/thumbnails/b6/abc.jpg"


# ---------------------------------------------------------------------------
# resolve_scope_input_path
# ---------------------------------------------------------------------------

def test_resolve_scope_input_path_finds_existing_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    d = tmp_path / "scope_dir"
    d.mkdir()
    win, tried = utils.resolve_scope_input_path(str(d))
    assert os.path.exists(win)
    assert win == os.path.normpath(str(d))
    assert any(str(d) == t or os.path.normpath(t) == win for t in tried)


def test_resolve_scope_input_path_windows_prefers_drive_for_mnt(monkeypatch):
    """On Windows, /mnt/d/... is not a real path; converted D:/... must be tried first."""
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    checked: list[str] = []

    def fake_exists(p):
        checked.append(p)
        return str(p).replace("\\", "/") == "D:/Photos/here"

    monkeypatch.setattr(os.path, "exists", fake_exists)
    win, _tried = utils.resolve_scope_input_path("/mnt/d/Photos/here")
    assert win.replace("\\", "/") == "D:/Photos/here"
    assert any(str(x).replace("\\", "/") == "D:/Photos/here" for x in checked)


def test_resolve_scope_input_path_none_when_missing(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(os.path, "exists", lambda _p: False)
    win, tried = utils.resolve_scope_input_path("/mnt/d/does/not/exist")
    assert win is None
    assert tried


def test_is_docker_runtime_env(monkeypatch):
    monkeypatch.delenv("DOCKER_CONTAINER", raising=False)
    monkeypatch.setattr(os.path, "exists", lambda p: False)
    assert utils.is_docker_runtime() is False
    monkeypatch.setenv("DOCKER_CONTAINER", "1")
    assert utils.is_docker_runtime() is True


def test_is_docker_runtime_dotdockerenv(monkeypatch):
    monkeypatch.delenv("DOCKER_CONTAINER", raising=False)

    def exists(p):
        return p == "/.dockerenv"

    monkeypatch.setattr(os.path, "exists", exists)
    assert utils.is_docker_runtime() is True


# ---------------------------------------------------------------------------
# convert_path_to_wsl
# ---------------------------------------------------------------------------

def test_convert_path_to_wsl_windows_slash():
    result = utils.convert_path_to_wsl("D:/Photos/img.jpg")
    assert result == "/mnt/d/Photos/img.jpg"


def test_convert_path_to_wsl_windows_backslash():
    result = utils.convert_path_to_wsl("D:\\Photos\\img.jpg")
    assert result == "/mnt/d/Photos/img.jpg"


def test_convert_path_to_wsl_already_wsl_unchanged():
    result = utils.convert_path_to_wsl("/mnt/d/Photos/img.jpg")
    assert result == "/mnt/d/Photos/img.jpg"


def test_convert_path_to_wsl_linux_path_unchanged():
    result = utils.convert_path_to_wsl("/home/user/photos.jpg")
    assert result == "/home/user/photos.jpg"


# ---------------------------------------------------------------------------
# compute_file_hash
# ---------------------------------------------------------------------------

def test_compute_file_hash_sha256(tmp_path, monkeypatch):
    # Prevent resolve_file_path from trying DB lookups
    monkeypatch.setattr(utils, "resolve_file_path", lambda path, image_id=None: path)

    test_file = tmp_path / "sample.bin"
    content = b"hello world"
    test_file.write_bytes(content)

    result = utils.compute_file_hash(str(test_file))
    expected = hashlib.sha256(content).hexdigest()
    assert result == expected


def test_compute_file_hash_md5(tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "resolve_file_path", lambda path, image_id=None: path)

    test_file = tmp_path / "sample.bin"
    content = b"test content"
    test_file.write_bytes(content)

    result = utils.compute_file_hash(str(test_file), algorithm="md5")
    expected = hashlib.md5(content).hexdigest()
    assert result == expected


def test_compute_file_hash_nonexistent_returns_none(monkeypatch):
    monkeypatch.setattr(utils, "resolve_file_path", lambda path, image_id=None: None)
    result = utils.compute_file_hash("/nonexistent/path/file.jpg")
    assert result is None


# ---------------------------------------------------------------------------
# resolve_file_path
# ---------------------------------------------------------------------------

def test_resolve_file_path_strategy2_as_is(tmp_path, monkeypatch):
    """Strategy 2: path exists as-is on filesystem."""
    test_file = tmp_path / "img.jpg"
    test_file.write_text("fake")

    result = utils.resolve_file_path(str(test_file))
    assert result == str(test_file)


def test_resolve_file_path_strategy3_converted(tmp_path, monkeypatch):
    """Strategy 3: converted path exists."""
    test_file = tmp_path / "img.jpg"
    test_file.write_text("fake")

    # Simulate: db_path doesn't exist as-is, but convert_path_to_local returns the real path
    fake_path = "/mnt/x/nonexistent/img.jpg"
    monkeypatch.setattr(utils, "convert_path_to_local", lambda p: str(test_file))

    result = utils.resolve_file_path(fake_path)
    assert result == str(test_file)


def test_resolve_file_path_returns_none_when_nothing_found(tmp_path, monkeypatch):
    """Strategy 4 (no image_id): all strategies fail -> returns None."""
    monkeypatch.setattr(utils, "convert_path_to_local", lambda p: p)

    result = utils.resolve_file_path("/nonexistent/path/that/does/not/exist.jpg")
    assert result is None


def test_resolve_file_path_strategy1_from_db(tmp_path, monkeypatch):
    """Strategy 1: resolved_paths table has a verified path."""
    test_file = tmp_path / "resolved.jpg"
    test_file.write_text("fake")

    from modules import db
    monkeypatch.setattr(db, "get_resolved_path", lambda image_id, verified_only=True: str(test_file))
    monkeypatch.setattr(utils, "convert_path_to_local", lambda p: p)

    result = utils.resolve_file_path("/some/db/path.jpg", image_id=1)
    assert result == str(test_file)


# ---------------------------------------------------------------------------
# get_image_creation_time
# ---------------------------------------------------------------------------

def test_get_image_creation_time_returns_datetime_for_missing_file():
    """Missing file should not raise — returns datetime.now() fallback."""
    import datetime
    result = utils.get_image_creation_time("/nonexistent/image.jpg")
    assert isinstance(result, datetime.datetime)


def test_get_image_creation_time_returns_datetime_for_real_file(tmp_path):
    """Real file without EXIF returns filesystem mtime as datetime."""
    import datetime
    test_file = tmp_path / "test.jpg"
    test_file.write_bytes(b"fake jpeg")

    result = utils.get_image_creation_time(str(test_file))
    assert isinstance(result, datetime.datetime)
