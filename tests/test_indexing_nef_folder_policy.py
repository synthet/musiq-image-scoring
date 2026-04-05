"""Unit tests for NEF-only folder assignment during indexing (no DB)."""

from pathlib import Path

from modules.indexing_runner import (
    _dir_directly_contains_nef,
    _path_under_or_equal,
    _resolve_nef_folder_path,
)


def test_path_under_or_equal(tmp_path: Path) -> None:
    base = tmp_path / "a" / "b"
    base.mkdir(parents=True)
    child = tmp_path / "a" / "b" / "c"
    child.mkdir()
    assert _path_under_or_equal(str(child), str(base))
    assert _path_under_or_equal(str(base), str(base))
    assert not _path_under_or_equal(str(tmp_path / "x"), str(base))


def test_dir_directly_contains_nef_case_insensitive(tmp_path: Path) -> None:
    d = tmp_path / "raw"
    d.mkdir()
    (d / "x.NEF").write_bytes(b"")
    cache: dict[str, bool] = {}
    assert _dir_directly_contains_nef(str(d), cache) is True


def test_resolve_prefers_deepest_ancestor_with_direct_nef(tmp_path: Path) -> None:
    sub = tmp_path / "raw" / "sub"
    sub.mkdir(parents=True)
    (sub / "a.nef").write_bytes(b"")
    jpg = sub / "x.jpg"
    jpg.write_bytes(b"")
    cache: dict[str, bool] = {}
    got = _resolve_nef_folder_path(str(jpg), str(tmp_path), cache)
    assert got == str(sub)


def test_resolve_respects_scan_stop(tmp_path: Path) -> None:
    outer = tmp_path / "outer"
    inner = outer / "inner"
    inner.mkdir(parents=True)
    (outer / "o.nef").write_bytes(b"")
    (inner / "i.jpg").write_bytes(b"")
    cache: dict[str, bool] = {}
    got = _resolve_nef_folder_path(str(inner / "i.jpg"), str(inner), cache)
    assert got is None


def test_resolve_none_when_no_nef_under_scan_root(tmp_path: Path) -> None:
    jpgs = tmp_path / "jpgs"
    jpgs.mkdir()
    (jpgs / "a.jpg").write_bytes(b"")
    cache: dict[str, bool] = {}
    got = _resolve_nef_folder_path(str(jpgs / "a.jpg"), str(tmp_path), cache)
    assert got is None
