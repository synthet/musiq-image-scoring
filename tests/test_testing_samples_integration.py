"""
Integration tests using real files under ``tests/fixtures/testing_samples`` (or ``NEF_TEST_SAMPLES_ROOT``).

Uses mock engines so CI/dev machines without GPU still exercise real paths + DB + pipeline.
Skips automatically when the samples directory is missing or empty.

Smoke tests (no DB): ``tests/test_testing_samples_smoke.py``.

Run::

    pytest tests/test_testing_samples_integration.py -m "sample_data and firebird" -v
"""
from __future__ import annotations

import os
import shutil
import time
import uuid
from unittest.mock import patch

import pytest

from modules import db
from modules.engines.mock import MockLiqeScorer, MockScoringEngine, MockTaggingEngine
from modules.scoring import ScoringRunner
from modules.tagging import TaggingRunner
from tests.support.testing_samples import list_sample_image_files, require_sample_files

pytestmark = pytest.mark.sample_data


class _NonRawMockScoringEngine(MockScoringEngine):
    """Treat all paths as non-RAW so PrepWorker does not load MultiModelMUSIQ for conversion."""

    def is_raw_file(self, file_path: str) -> bool:
        return False


def _insert_image_row_for_abs_path(abs_path: str) -> tuple[int, str]:
    """Register folder + image row; returns (image_id, db file_path)."""
    abs_path = os.path.abspath(abs_path)
    folder = os.path.dirname(abs_path)
    filename = os.path.basename(abs_path)
    folder_id = db.get_or_create_folder(folder)
    if folder_id is None:
        raise RuntimeError(f"get_or_create_folder failed for {folder!r}")

    conn = db.get_db()
    c = conn.cursor()
    c.execute("SELECT path FROM folders WHERE id = ?", (folder_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise RuntimeError("folder row missing")
    stored_folder = row[0]
    db_path = f"{stored_folder}/{filename}".replace("\\", "/")
    c.execute(
        "INSERT INTO images (file_path, folder_id, file_name) VALUES (?, ?, ?) RETURNING id",
        (db_path, folder_id, filename),
    )
    ins = c.fetchone()
    conn.commit()
    conn.close()
    if not ins:
        raise RuntimeError("INSERT images failed")
    return int(ins[0]), db_path


def _fetch_keywords(image_id: int) -> str:
    conn = db.get_db()
    c = conn.cursor()
    c.execute("SELECT keywords FROM images WHERE id = ?", (image_id,))
    row = c.fetchone()
    conn.close()
    return (row[0] or "").strip() if row else ""


@pytest.fixture(scope="module")
def samples_db(tmp_path_factory):
    template = os.path.abspath("template.fdb")
    if not os.path.exists(template):
        pytest.skip("template.fdb not found - Firebird tests unavailable")

    tmp = tmp_path_factory.mktemp("samples_integration")
    db_path = str(tmp / f"samples_{uuid.uuid4().hex}.fdb")
    shutil.copy2(template, db_path)

    original_path = db.DB_PATH
    db.DB_PATH = os.path.abspath(db_path)
    db.reset_init_db_state_for_tests()
    try:
        db.init_db()
    except Exception as exc:
        db.DB_PATH = original_path
        pytest.skip(f"DB init failed: {exc}")

    yield
    db.DB_PATH = original_path


@pytest.fixture(autouse=True)
def clean_jobs(samples_db):
    conn = db.get_db()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM job_phases")
    except Exception:
        pass
    try:
        c.execute("DELETE FROM images")
    except Exception:
        pass
    try:
        c.execute("DELETE FROM folders")
    except Exception:
        pass
    c.execute("DELETE FROM jobs")
    conn.commit()
    conn.close()


@pytest.mark.firebird
@patch("modules.scoring.db.backup_database", lambda *args, **kwargs: None)
def test_mock_scoring_resolved_path_uses_real_sample_file(samples_db):
    require_sample_files(1)
    sample_path = list_sample_image_files()[0]
    assert os.path.isfile(sample_path)

    image_id, _db_path = _insert_image_row_for_abs_path(sample_path)
    job_id = db.create_job(os.path.dirname(sample_path), job_type="scoring", status="pending")

    runner = ScoringRunner(
        scoring_engine=_NonRawMockScoringEngine(),
        liqe_scorer=MockLiqeScorer(),
    )
    assert runner.start_batch(
        os.path.dirname(sample_path),
        job_id,
        skip_existing=False,
        resolved_image_ids=[image_id],
    ) == "Started"

    deadline = time.time() + 120.0
    while time.time() < deadline and runner.is_running:
        time.sleep(0.05)

    assert not runner.is_running
    assert db.get_job_by_id(job_id)["status"] == "completed"


@pytest.mark.firebird
def test_mock_tagging_folder_scans_real_sample_tree(samples_db):
    """
    Register one real sample file, run TaggingRunner with MockTaggingEngine on that folder, assert keywords in DB.
    """
    require_sample_files(1)
    sample_path = list_sample_image_files()[0]
    folder = os.path.dirname(sample_path)
    image_id, _db_path = _insert_image_row_for_abs_path(sample_path)

    job_id = db.create_job(folder, job_type="tagging", status="pending")
    runner = TaggingRunner(tagging_engine=MockTaggingEngine(keywords=["sample", "test"]))
    assert runner.start_batch(folder, job_id=job_id, overwrite=True, generate_captions=False) == "Started"

    deadline = time.time() + 120.0
    while time.time() < deadline and runner.is_running:
        time.sleep(0.05)

    assert not runner.is_running
    assert db.get_job_by_id(job_id)["status"] == "completed"

    kw = _fetch_keywords(image_id)
    assert "sample" in kw or "test" in kw

