"""Tests for modules.thumbnail_maintenance helpers (no DB)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from modules import thumbnail_maintenance  # noqa: E402


def test_filesystem_path_for_image_existing(tmp_path):
    f = tmp_path / "x.jpg"
    f.write_bytes(b"x")
    p = str(f.resolve())
    assert thumbnail_maintenance.filesystem_path_for_image(p) == p


def test_folder_like_patterns_windows_drive():
    pats = thumbnail_maintenance.folder_like_patterns(r"D:\Photos\2024")
    assert any("D:\\Photos\\2024\\%" in x or "D:/Photos/2024/%" in x.replace("\\", "/") for x in pats)
    assert any("/mnt/d/Photos/2024/%" in x for x in pats)


@pytest.mark.parametrize(
    "limit,fetch_expected",
    [
        (1, 3),
        (500, 1500),
    ],
)
def test_regenerate_missing_thumbnails_batch_respects_limit(monkeypatch, limit, fetch_expected):
    """Stops after ``limit`` successful regenerations; SQL fetch uses limit * 3."""
    captured: dict = {}

    class FakeConnector:
        def query(self, sql, params=None):
            captured["fetch"] = params[0] if params else None
            n = int(params[0])
            out = []
            for i in range(n):
                out.append(
                    {
                        "id": i + 1,
                        "file_path": f"/tmp/img{i}.jpg",
                        "thumbnail_path": None,
                        "thumbnail_path_win": None,
                    }
                )
            return out

    monkeypatch.setattr(
        "modules.thumbnail_maintenance.db.get_connector",
        lambda: FakeConnector(),
    )
    monkeypatch.setattr(
        "modules.thumbnail_maintenance.filesystem_path_for_image",
        lambda p: p if p.startswith("/tmp/") else None,
    )
    monkeypatch.setattr("modules.thumbnail_maintenance.resolved_thumb_ok", lambda *a: False)
    monkeypatch.setattr(
        "modules.thumbnail_maintenance.thumbnails.generate_thumbnail",
        lambda path, **kw: f"/thumb/{os.path.basename(path)}",
    )
    monkeypatch.setattr("modules.thumbnail_maintenance.os.path.isfile", lambda p: True)
    monkeypatch.setattr("modules.thumbnail_maintenance.os.path.getsize", lambda p: 10)
    monkeypatch.setattr("modules.thumbnail_maintenance.db.update_image_thumbnail_paths", lambda *a, **k: True)

    stats = thumbnail_maintenance.regenerate_missing_thumbnails_batch(limit=limit)
    assert captured["fetch"] == fetch_expected
    assert stats["regenerated"] == limit
    assert stats["failed"] == 0
