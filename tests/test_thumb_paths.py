"""
Tests for thumbnail path helpers: nested layout, get_thumb_wsl/get_thumb_win, conversions.
No DB or sample files required.
"""
import os
import sys

import pytest

# Ensure project root on path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from modules import thumbnails


def test_collapse_malformed_thumbnail_segments():
    s = "../image-scoring-backend/thumbnails/app/thumbnails/a7/file.jpg"
    out = thumbnails.collapse_malformed_thumbnail_segments(s)
    assert "app/thumbnails" not in out.replace("\\", "/")
    assert out.replace("\\", "/").endswith("thumbnails/a7/file.jpg")


def test_thumbnail_pair_needs_repair_docker_and_incomplete():
    assert thumbnails.thumbnail_pair_needs_repair(
        "/app/thumbnails/e7/e7fb2c22547e5e312201223617a6d771.jpg",
        r"\app\thumbnails\e7\e7fb2c22547e5e312201223617a6d771.jpg",
    )
    assert thumbnails.thumbnail_pair_needs_repair(
        "/mnt/d/Projects/image-scoring-backend/thumbnails/2c952d26101f8908167e1a5b1acdaad4.jpg",
        None,
    )
    assert not thumbnails.thumbnail_pair_needs_repair(
        "/mnt/d/Projects/image-scoring-backend/thumbnails/ab/abcdef0123456789abcdef0123456789.jpg",
        r"D:\Projects\image-scoring-backend\thumbnails\ab\abcdef0123456789abcdef0123456789.jpg",
    )


def test_normalize_stored_thumbnail_pair_collapses_without_file():
    tp, tw = thumbnails.normalize_stored_thumbnail_pair(
        "../image-scoring-backend/thumbnails/app/thumbnails/zz/notfound.jpg",
        None,
    )
    assert tp is not None
    assert "app/thumbnails" not in tp.replace("\\", "/")
    assert tw is not None


def test_database_thumbnail_pair_maps_container_to_host(monkeypatch, tmp_path):
    """With host roots set, DB pair uses /mnt/... and D:\\... instead of /app/thumbnails/..."""
    monkeypatch.setenv("DOCKER_CONTAINER", "1")
    monkeypatch.setenv("IMAGE_SCORING_HOST_PROJECT_WSL", "/mnt/d/Projects/image-scoring-backend")
    monkeypatch.setenv("IMAGE_SCORING_HOST_PROJECT_WIN", r"D:\Projects\image-scoring-backend")
    fake_root = tmp_path / "app"
    thumb_dir = fake_root / "thumbnails" / "e7"
    thumb_dir.mkdir(parents=True)
    thumb_file = thumb_dir / "e7fb2c22547e5e312201223617a6d771.jpg"
    thumb_file.write_bytes(b"x")
    monkeypatch.setattr(thumbnails, "PROJECT_ROOT", fake_root.resolve())
    monkeypatch.setattr(thumbnails, "THUMB_DIR", str(fake_root / "thumbnails"))

    tp, tw = thumbnails.database_thumbnail_pair_from_fs_path(str(thumb_file))
    assert tp.replace("\\", "/").startswith("/mnt/d/Projects/image-scoring-backend/thumbnails/e7/")
    assert "e7fb2c22547e5e312201223617a6d771.jpg" in tp.replace("\\", "/")
    assert r"D:\Projects\image-scoring-backend\thumbnails\e7" in tw.replace("/", "\\")


def test_synthetic_app_paths_rewritten_when_host_roots_set(monkeypatch):
    monkeypatch.setenv("IMAGE_SCORING_HOST_PROJECT_WSL", "/mnt/d/Projects/image-scoring-backend")
    monkeypatch.setenv("IMAGE_SCORING_HOST_PROJECT_WIN", r"D:\Projects\image-scoring-backend")
    tp, tw = thumbnails._synthetic_app_thumbnail_db_pair(
        "/app/thumbnails/e7/e7fb2c22547e5e312201223617a6d771.jpg",
        r"\app\thumbnails\e7\e7fb2c22547e5e312201223617a6d771.jpg",
    )
    assert tp
    assert tw
    assert "/app/thumbnails" not in (tp + tw).replace("\\", "/").lower()
    assert tp.startswith("/mnt/d/Projects/image-scoring-backend/")


def test_normalize_remaps_docker_app_thumbnails_even_when_file_missing():
    """DB must not keep /app/thumbnails/...; remap to THUMB_DIR under project root."""
    fake_hash = "z" * 32
    rel = f"zz/{fake_hash}.jpg"
    tp, tw = thumbnails.normalize_stored_thumbnail_pair(f"/app/thumbnails/{rel}", None)
    assert tp is not None and tw is not None
    assert "/app/thumbnails" not in tp.replace("\\", "/").lower()
    assert "app/thumbnails" not in tw.replace("\\", "/").lower()
    expected_abs = os.path.normpath(os.path.join(thumbnails.THUMB_DIR, rel.replace("/", os.sep)))
    exp_tp, exp_tw = thumbnails.database_thumbnail_pair_from_fs_path(expected_abs)
    assert tp == exp_tp
    assert tw == exp_tw


def test_host_roots_do_not_remap_native_checkout(monkeypatch, tmp_path):
    """Leaked IMAGE_SCORING_HOST_PROJECT_* must not rewrite paths when not in Docker /app layout."""
    monkeypatch.setenv("IMAGE_SCORING_HOST_PROJECT_WSL", "/mnt/z/WRONG/clone")
    monkeypatch.setenv("IMAGE_SCORING_HOST_PROJECT_WIN", r"Z:\WRONG\clone")
    monkeypatch.delenv("DOCKER_CONTAINER", raising=False)
    fake_root = tmp_path / "image-scoring-backend"
    (fake_root / "thumbnails" / "ab").mkdir(parents=True)
    thumb = fake_root / "thumbnails" / "ab" / "deadbeef.jpg"
    thumb.write_bytes(b"x")
    monkeypatch.setattr(thumbnails, "PROJECT_ROOT", fake_root.resolve())
    monkeypatch.setattr(thumbnails, "THUMB_DIR", str(fake_root / "thumbnails"))

    tp, tw = thumbnails.database_thumbnail_pair_from_fs_path(str(thumb))
    assert "/mnt/z/WRONG" not in (tp or "")
    assert "WRONG" not in (tw or "").replace("/", "\\")


def test_remap_container_thumbnail_path_to_host():
    rel = "e7/e7fb2c22547e5e312201223617a6d771.jpg"
    host = thumbnails.remap_container_thumbnail_path_to_host(f"/app/thumbnails/{rel}")
    assert host is not None
    assert host.endswith(rel.replace("/", os.sep))
    assert host.startswith(thumbnails.THUMB_DIR)


def test_get_thumb_path_nested_layout():
    """get_thumb_path returns path under thumbnails/{hash[:2]}/{hash}.jpg."""
    path = "/mnt/x/Photos/test/image.NEF"
    result = thumbnails.get_thumb_path(path)
    assert result is not None
    assert result.endswith(".jpg")
    base = os.path.basename(result)
    stem = base[:-4]
    assert len(stem) == 32
    parent = os.path.basename(os.path.dirname(result))
    assert parent == stem[:2]
    assert result.startswith(thumbnails.THUMB_DIR)


def test_thumb_path_to_win():
    """WSL path converts to Windows path."""
    wsl = "/mnt/x/ws/thumbnails/ab/abcdef0123456789.jpg"
    win = thumbnails.thumb_path_to_win(wsl)
    assert win is not None
    assert "\\" in win or win.startswith("X:")
    assert "ab" in win and "abcdef0123456789.jpg" in win


def test_thumb_path_to_wsl():
    """Windows path converts to WSL path."""
    win = r"X:\ws\thumbnails\ab\abcdef0123456789.jpg"
    wsl = thumbnails.thumb_path_to_wsl(win)
    assert wsl is not None
    assert wsl.startswith("/mnt/")
    assert "/ab/abcdef0123456789.jpg" in wsl


def test_get_thumb_wsl_prefers_thumbnail_path():
    """get_thumb_wsl returns thumbnail_path when set."""
    row = {"thumbnail_path": "/mnt/x/thumbnails/ab/ab123.jpg", "thumbnail_path_win": r"X:\thumbnails\ab\ab123.jpg"}
    assert thumbnails.get_thumb_wsl(row) == "/mnt/x/thumbnails/ab/ab123.jpg"


def test_get_thumb_wsl_fallback_from_win():
    """get_thumb_wsl converts thumbnail_path_win when thumbnail_path empty."""
    row = {"thumbnail_path": None, "thumbnail_path_win": r"X:\thumbnails\ab\ab123.jpg"}
    result = thumbnails.get_thumb_wsl(row)
    assert result is not None
    assert result.startswith("/mnt/")


def test_get_thumb_win_prefers_thumbnail_path_win():
    """get_thumb_win returns thumbnail_path_win when set."""
    row = {"thumbnail_path": "/mnt/x/thumbnails/ab/ab123.jpg", "thumbnail_path_win": r"X:\thumbnails\ab\ab123.jpg"}
    assert thumbnails.get_thumb_win(row) == r"X:\thumbnails\ab\ab123.jpg"


def test_get_thumb_win_fallback_from_wsl():
    """get_thumb_win converts thumbnail_path when thumbnail_path_win empty."""
    row = {"thumbnail_path": "/mnt/x/ws/thumbnails/ab/ab123.jpg", "thumbnail_path_win": None}
    result = thumbnails.get_thumb_win(row)
    assert result is not None
    assert "\\" in result or result.startswith("X:")


def test_get_local_thumb_uses_platform():
    """get_local_thumb returns wsl or win path based on platform."""
    row = {"thumbnail_path": "/mnt/x/t.jpg", "thumbnail_path_win": r"X:\t.jpg"}
    result = thumbnails.get_local_thumb(row)
    assert result is not None
    if os.name == "nt":
        assert result == r"X:\t.jpg"
    else:
        assert result == "/mnt/x/t.jpg"


def test_consumers_import_and_call_get_thumb_wsl():
    """Consumer modules can import thumbnails and call get_thumb_wsl with a row-like dict."""
    row = {
        "id": 1,
        "thumbnail_path": "/mnt/x/ws/thumbnails/ab/abcdef1234567890.jpg",
        "thumbnail_path_win": r"thumbnails\ab\abcdef1234567890.jpg",
    }
    wsl = thumbnails.get_thumb_wsl(row)
    win = thumbnails.get_thumb_win(row)
    assert wsl == row["thumbnail_path"]
    assert win == row["thumbnail_path_win"]
