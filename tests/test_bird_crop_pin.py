"""Unit tests for the pinned-population plumbing (no GPU/DB, stubbed SELECT).

These guard the invariant the whole re-sweep exists to restore: every track must
measure the *same* images. The original failure was silent — runs shrank or
shifted their population and still produced plausible-looking numbers — so the
tests here mostly assert that shrinkage is loud.
"""

from __future__ import annotations

import pytest

from scripts.research.bird_crop import bursts, prod
from scripts.research.bird_crop.pin_study_set import read_ids


@pytest.fixture
def captured_select(monkeypatch):
    """Stub ``prod.select`` and record the SQL/params it was called with."""
    calls: list[tuple[str, object]] = []
    rows: list[dict] = []

    def fake_select(sql, params=None):
        calls.append((sql, params))
        return list(rows)

    monkeypatch.setattr(prod, "select", fake_select)

    class Harness:
        def returns(self, ids):
            rows[:] = [{"id": i, "folder_id": 1, "bird_bbox": {"x1": 0}} for i in ids]

        @property
        def sql(self):
            return calls[-1][0]

        @property
        def params(self):
            return calls[-1][1]

    return Harness()


# --------------------------------------------------------------------------
# Pinned selection replaces folder/limit selection
# --------------------------------------------------------------------------
def test_pinned_query_filters_by_id_and_not_by_folder(captured_select):
    captured_select.returns([1, 2, 3])

    bursts.load_boxed_rows(image_ids=[3, 1, 2])

    assert "i.id = ANY(%s)" in captured_select.sql
    assert "i.folder_id = ANY(%s)" not in captured_select.sql
    assert "LIMIT" not in captured_select.sql


def test_pinned_ids_are_sorted_and_deduplicated(captured_select):
    captured_select.returns([1, 2, 3])

    bursts.load_boxed_rows(image_ids=[3, 1, 2, 3, 1])

    assert captured_select.params == [[1, 2, 3]]


def test_unpinned_call_is_unchanged(captured_select):
    """The folder path must keep working for ad-hoc, non-comparative runs."""
    captured_select.returns([1, 2])

    bursts.load_boxed_rows(folders=[62, 676], limit=10)

    assert "i.folder_id = ANY(%s)" in captured_select.sql
    assert "LIMIT %s" in captured_select.sql
    assert captured_select.params == [[62, 676], 10]


# --------------------------------------------------------------------------
# A pinned run must never quietly measure fewer images
# --------------------------------------------------------------------------
def test_missing_pinned_id_raises_and_names_it(captured_select):
    """``_SQL_BOXED`` joins image_exif, so a pinned id can vanish through it."""
    captured_select.returns([1, 3])  # id 2 dropped by the boxed/EXIF filters

    with pytest.raises(SystemExit) as exc:
        bursts.load_boxed_rows(image_ids=[1, 2, 3])

    message = str(exc.value)
    assert "1 pinned image id" in message
    assert "[2]" in message
    assert "date_time_original" in message  # names the likely cause


def test_complete_result_returns_every_pinned_row(captured_select):
    captured_select.returns([1, 2, 3])

    rows = bursts.load_boxed_rows(image_ids=[1, 2, 3])

    assert [r["id"] for r in rows] == [1, 2, 3]


# --------------------------------------------------------------------------
# The pin is the population; narrowing it is a bug, not an option
# --------------------------------------------------------------------------
def test_pin_combined_with_folders_is_rejected(captured_select):
    captured_select.returns([1])

    with pytest.raises(SystemExit, match="mutually exclusive"):
        bursts.load_boxed_rows(image_ids=[1], folders=[62])


def test_pin_combined_with_limit_is_rejected(captured_select):
    captured_select.returns([1])

    with pytest.raises(SystemExit, match="mutually exclusive"):
        bursts.load_boxed_rows(image_ids=[1], limit=50)


def test_zero_limit_is_not_treated_as_narrowing(captured_select):
    """``--limit 0`` is how the CLIs disable the budget on a pinned run."""
    captured_select.returns([1, 2])

    rows = bursts.load_boxed_rows(image_ids=[1, 2], limit=0)

    assert len(rows) == 2


# --------------------------------------------------------------------------
# read_ids — the parser both new CLIs and input_size_embed share
# --------------------------------------------------------------------------
def test_read_ids_ignores_comments_and_blank_lines(tmp_path):
    path = tmp_path / "ids.txt"
    path.write_text("# header\n\n12\n  7  \n34 # trailing\n", encoding="utf-8")

    assert read_ids(path) == [7, 12, 34]


def test_read_ids_rejects_duplicates(tmp_path):
    path = tmp_path / "ids.txt"
    path.write_text("1\n2\n1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate"):
        read_ids(path)


def test_read_ids_rejects_non_integers(tmp_path):
    path = tmp_path / "ids.txt"
    path.write_text("1\nnot-an-id\n", encoding="utf-8")

    with pytest.raises(ValueError, match="not an integer image id"):
        read_ids(path)


def test_read_ids_rejects_an_empty_file(tmp_path):
    path = tmp_path / "ids.txt"
    path.write_text("# only a comment\n", encoding="utf-8")

    with pytest.raises(ValueError, match="no image ids"):
        read_ids(path)


def test_read_ids_reports_a_missing_file_with_the_fix(tmp_path):
    with pytest.raises(FileNotFoundError, match="pin_study_set"):
        read_ids(tmp_path / "absent.txt")
