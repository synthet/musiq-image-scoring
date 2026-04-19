import sqlite3
from contextlib import contextmanager

from modules import selector_resolver


def _build_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE folders (id INTEGER PRIMARY KEY, path TEXT UNIQUE, parent_id INTEGER)")
    conn.execute("CREATE TABLE images (id INTEGER PRIMARY KEY, file_path TEXT UNIQUE, folder_id INTEGER)")
    conn.executemany(
        "INSERT INTO folders (id, path, parent_id) VALUES (?, ?, ?)",
        [
            (1, "/root", None),
            (2, "/root/sub", 1),
            (3, "/other", None),
        ],
    )
    conn.executemany(
        "INSERT INTO images (id, file_path, folder_id) VALUES (?, ?, ?)",
        [
            (10, "/root/a.jpg", 1),
            (11, "/root/sub/b.jpg", 2),
            (12, "/other/c.jpg", 3),
        ],
    )
    conn.commit()
    return conn


def test_dedupe_helpers_filter_and_preserve_order():
    assert selector_resolver._dedupe_ints(["3", 0, "bad", 2, 3, -1, 2]) == [3, 2]
    assert selector_resolver._dedupe_strs(["  a  ", "", None, "a", "b", " b "]) == ["a", "b"]


def test_resolve_selectors_resolves_paths_and_recursive_folders(monkeypatch):
    conn = _build_conn()

    class FakeDB:
        @staticmethod
        def get_db():
            return conn

        @staticmethod
        @contextmanager
        def connection():
            yield conn

    monkeypatch.setattr(selector_resolver, "db", FakeDB)
    monkeypatch.setattr(selector_resolver.utils, "convert_path_to_wsl", lambda p: p)

    result = selector_resolver.resolve_selectors(
        image_ids=[10, 10],
        image_paths=["/other/c.jpg"],
        folder_ids=[1],
        folder_paths=["/root"],
        recursive=True,
        index_missing=False,
    )

    assert result["resolved_image_ids"] == [10, 12, 11]
    assert sorted(result["resolved_folder_ids"]) == [1, 2]
    assert result["missing_image_paths"] == []
    assert result["missing_folder_paths"] == []
    assert result["indexed_image_paths"] == []
    assert result["indexed_folder_ids"] == []


def test_resolve_selectors_indexes_missing_paths(monkeypatch, tmp_path):
    conn = _build_conn()
    indexed_folder = tmp_path / "indexed"
    indexed_folder.mkdir()
    indexed_file = indexed_folder / "new.jpg"
    indexed_file.write_text("x")

    def sync_folder_to_db(path: str):
        if path == str(indexed_folder):
            conn.execute(
                "INSERT OR IGNORE INTO folders (id, path, parent_id) VALUES (?, ?, ?)",
                (20, str(indexed_folder), None),
            )
            conn.execute(
                "INSERT OR IGNORE INTO images (id, file_path, folder_id) VALUES (?, ?, ?)",
                (21, str(indexed_file), 20),
            )
            conn.commit()

    def get_or_create_folder(path: str) -> int:
        row = conn.execute("SELECT id FROM folders WHERE path = ?", (path,)).fetchone()
        if row:
            return int(row[0])
        conn.execute("INSERT INTO folders (path, parent_id) VALUES (?, NULL)", (path,))
        conn.commit()
        return int(conn.execute("SELECT id FROM folders WHERE path = ?", (path,)).fetchone()[0])

    class FakeDB:
        @staticmethod
        def get_db():
            return conn

        @staticmethod
        @contextmanager
        def connection():
            yield conn

    FakeDB.sync_folder_to_db = staticmethod(sync_folder_to_db)
    FakeDB.get_or_create_folder = staticmethod(get_or_create_folder)

    monkeypatch.setattr(selector_resolver, "db", FakeDB)
    monkeypatch.setattr(selector_resolver.utils, "convert_path_to_wsl", lambda p: p)

    missing_file = str(indexed_file)
    missing_folder = str(indexed_folder)

    result = selector_resolver.resolve_selectors(
        image_paths=[missing_file],
        folder_paths=[missing_folder],
        recursive=False,
        index_missing=True,
    )

    assert result["missing_image_paths"] == []
    assert result["missing_folder_paths"] == [missing_folder]
    assert result["indexed_image_paths"] == [missing_file]
    assert result["indexed_folder_ids"] == [20]
    assert sorted(result["resolved_image_ids"]) == [21]
    assert result["resolved_folder_ids"] == [20]
