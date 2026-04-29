"""Unit tests for ``_resolve_split_brain_collision`` (no DB)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pytest

from modules import indexing_runner


class _FakeConnector:
    def __init__(self, rows_by_id: Dict[int, Dict[str, Any]]):
        self._rows = rows_by_id
        self.executed: List[Tuple[str, tuple]] = []

    def query_one(self, sql: str, params: tuple) -> Optional[Dict[str, Any]]:
        # Only the SELECT for track_id row is exercised.
        assert "FROM images WHERE id = ?" in sql
        (image_id,) = params
        row = self._rows.get(image_id)
        return dict(row) if row else None

    def execute(self, sql: str, params: tuple) -> None:
        self.executed.append((sql, params))
        if sql.startswith("DELETE FROM images WHERE id"):
            (image_id,) = params
            self._rows.pop(image_id, None)


class _FakeDB:
    def __init__(self, rows_by_id: Dict[int, Dict[str, Any]]):
        self.connector = _FakeConnector(rows_by_id)
        self.field_updates: List[Tuple[int, str, Any]] = []
        self.deleted_paths: List[str] = []
        self.invalidated_folder_ids: List[int] = []

    def get_connector(self):
        return self.connector

    def update_image_field(self, image_id: int, field: str, value: Any) -> bool:
        self.field_updates.append((image_id, field, value))
        return True

    def delete_image(self, file_path: str, delete_related: bool = True) -> Tuple[bool, str]:
        self.deleted_paths.append(file_path)
        # Drop the row whose file_path matches, mirroring real delete_image side effects.
        for rid, row in list(self.connector._rows.items()):
            if row.get("file_path") == file_path:
                self.connector._rows.pop(rid, None)
        return True, "ok"

    def invalidate_folder_phase_aggregates(self, *, folder_id: int) -> None:
        self.invalidated_folder_ids.append(folder_id)


@pytest.fixture
def captured_log():
    msgs: List[Tuple[str, str]] = []

    def _log(level: str, message: str, **_: Any) -> None:
        msgs.append((level, message))

    return msgs, _log


def _install_fake_db(monkeypatch, fake_db: _FakeDB) -> None:
    monkeypatch.setattr(indexing_runner, "db", fake_db)


def test_case_a_track_id_lacks_hash_merges_into_hash_row(monkeypatch, captured_log):
    """track_id has no hash → adopt hash_row_id, delete track_id by current path."""
    msgs, log = captured_log
    track_id, hash_row_id = 100, 200
    file_path = "/mnt/d/photos/IMG_0001.NEF"

    track_row = {
        "image_hash": None,
        "file_path": file_path,
        "rating": 4,
        "label": "keep",
        "folder_id": 11,
    }
    hash_row = {
        "image_hash": "deadbeef",
        "file_path": "D:\\photos\\IMG_0001.NEF",
        "rating": 2,
        "label": "",
        "folder_id": 22,
    }
    fake_db = _FakeDB({track_id: track_row, hash_row_id: hash_row})
    _install_fake_db(monkeypatch, fake_db)

    resolved = indexing_runner._resolve_split_brain_collision(
        track_id=track_id,
        hash_row_id=hash_row_id,
        file_path=file_path,
        image_hash="deadbeef",
        hash_version=1,
        existing=hash_row,
        existing_by_path=track_row,
        log=log,
    )

    assert resolved == hash_row_id
    # rating bumped (4 > 2) and label promoted ("keep" over "")
    assert (hash_row_id, "rating", 4) in fake_db.field_updates
    assert (hash_row_id, "label", "keep") in fake_db.field_updates
    # track_id row deleted by current scan path
    assert fake_db.deleted_paths == [file_path]
    # folder aggregates invalidated for the dropped row's folder
    assert fake_db.invalidated_folder_ids == [11]
    assert any("Merged metadata from redundant row 100" in m for _, m in msgs)


def test_case_b_both_have_hash_prefers_track_id(monkeypatch, captured_log):
    """Both rows have hashes → prefer track_id, merge metadata, delete hash_row_id by its own path."""
    msgs, log = captured_log
    track_id, hash_row_id = 300, 400
    file_path = "/mnt/d/photos/DSC_5700.NEF"
    other_path = "D:\\photos\\DSC_5700.NEF"

    # track_id has a stale hash; hash_row_id has the freshly computed one.
    track_row = {
        "image_hash": "stale_hash_v0",
        "file_path": file_path,
        "rating": 1,
        "label": "",
        "folder_id": 33,
    }
    hash_row = {
        "image_hash": "fresh_hash",
        "file_path": other_path,
        "rating": 5,
        "label": "pick",
        "folder_id": 44,
    }
    fake_db = _FakeDB({track_id: track_row, hash_row_id: hash_row})
    _install_fake_db(monkeypatch, fake_db)

    resolved = indexing_runner._resolve_split_brain_collision(
        track_id=track_id,
        hash_row_id=hash_row_id,
        file_path=file_path,
        image_hash="fresh_hash",
        hash_version=2,
        existing=hash_row,
        existing_by_path=track_row,
        log=log,
    )

    assert resolved == track_id
    # rating bumped (5 > 1) and label promoted ("pick" over "")
    assert (track_id, "rating", 5) in fake_db.field_updates
    assert (track_id, "label", "pick") in fake_db.field_updates
    # hash_row_id deleted by its own (non-current) path — current path is preserved
    assert fake_db.deleted_paths == [other_path]
    assert file_path not in fake_db.deleted_paths
    # Stale hash adopted on track_id (slot freed by deletion above)
    assert (track_id, "image_hash", "fresh_hash") in fake_db.field_updates
    assert (track_id, "hash_version", 2) in fake_db.field_updates
    # Folder aggregates invalidated for the redundant row's folder
    assert fake_db.invalidated_folder_ids == [44]
    assert any("Merged hash-collision row 400" in m for _, m in msgs)


def test_case_b_skips_hash_update_when_already_current(monkeypatch, captured_log):
    """track_id already has the freshly computed hash → no redundant hash UPDATE."""
    _, log = captured_log
    track_id, hash_row_id = 1, 2
    file_path = "/x/y.jpg"

    track_row = {
        "image_hash": "same_hash",
        "file_path": file_path,
        "rating": 3,
        "label": "a",
        "folder_id": None,
    }
    hash_row = {
        "image_hash": "same_hash",
        "file_path": "/x/y_alt.jpg",
        "rating": 3,
        "label": "a",
        "folder_id": None,
    }
    fake_db = _FakeDB({track_id: track_row, hash_row_id: hash_row})
    _install_fake_db(monkeypatch, fake_db)

    resolved = indexing_runner._resolve_split_brain_collision(
        track_id=track_id,
        hash_row_id=hash_row_id,
        file_path=file_path,
        image_hash="same_hash",
        hash_version=1,
        existing=hash_row,
        existing_by_path=track_row,
        log=log,
    )

    assert resolved == track_id
    # No image_hash / hash_version writes since the hash is already current.
    fields_written = {field for _, field, _ in fake_db.field_updates}
    assert "image_hash" not in fields_written
    assert "hash_version" not in fields_written
    # No metadata bump either (rating/label equal).
    assert fake_db.field_updates == []
    # Redundant row deleted by its own path.
    assert fake_db.deleted_paths == ["/x/y_alt.jpg"]


def test_case_b_falls_back_to_direct_delete_when_paths_collide(monkeypatch, captured_log):
    """If hash_row_id has no separate file_path, fall back to a direct DELETE by id."""
    _, log = captured_log
    track_id, hash_row_id = 10, 20
    file_path = "/dup/path.png"

    track_row = {
        "image_hash": "h1",
        "file_path": file_path,
        "rating": 0,
        "label": "",
        "folder_id": None,
    }
    hash_row = {
        "image_hash": "h2",
        "file_path": "",
        "rating": 0,
        "label": "",
        "folder_id": None,
    }
    fake_db = _FakeDB({track_id: track_row, hash_row_id: hash_row})
    _install_fake_db(monkeypatch, fake_db)

    resolved = indexing_runner._resolve_split_brain_collision(
        track_id=track_id,
        hash_row_id=hash_row_id,
        file_path=file_path,
        image_hash="h2",
        hash_version=1,
        existing=hash_row,
        existing_by_path=track_row,
        log=log,
    )

    assert resolved == track_id
    # No path-based delete (would have wiped track_id).
    assert fake_db.deleted_paths == []
    # Direct DELETE by id was issued.
    assert any(
        sql.startswith("DELETE FROM images WHERE id") and params == (hash_row_id,)
        for sql, params in fake_db.connector.executed
    )


def test_returns_hash_row_id_when_track_row_missing(monkeypatch, captured_log):
    """Defensive: if the track_id row vanished mid-scan, fall through to hash_row_id."""
    _, log = captured_log
    fake_db = _FakeDB({999: {"image_hash": "h", "file_path": "/p"}})
    _install_fake_db(monkeypatch, fake_db)

    resolved = indexing_runner._resolve_split_brain_collision(
        track_id=123,  # not present in fake_db
        hash_row_id=999,
        file_path="/p",
        image_hash="h",
        hash_version=1,
        existing={"file_path": "/p", "rating": 0, "label": ""},
        existing_by_path=None,
        log=log,
    )

    assert resolved == 999
    assert fake_db.field_updates == []
    assert fake_db.deleted_paths == []
