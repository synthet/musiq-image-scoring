"""
Tier B: JobDispatcher with runners wired to mock engines (no GPU inference).

Requires Firebird + template.fdb. Patches scoring DB backups to avoid side effects.
"""
from __future__ import annotations

import os
import shutil
import time
import uuid
from unittest.mock import patch

import pytest

from tests.support.optional_deps import require_psycopg2, require_sklearn, require_torch

require_sklearn()
require_torch()
require_psycopg2()

from modules import db
from modules.clustering import ClusteringRunner
from modules.engines.mock import MockClusteringEngine, MockLiqeScorer, MockScoringEngine, MockTaggingEngine
from modules.job_dispatcher import JobDispatcher
from modules.scoring import ScoringRunner
from modules.tagging import TaggingRunner


@pytest.fixture(scope="module")
def pipeline_mock_db(tmp_path_factory):
    template = os.path.abspath("template.fdb")
    if not os.path.exists(template):
        pytest.skip("template.fdb not found - Firebird tests unavailable")

    tmp = tmp_path_factory.mktemp("mock_pipeline")
    db_path = str(tmp / f"mock_pipe_{uuid.uuid4().hex}.fdb")
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
def clean_jobs(pipeline_mock_db):
    conn = db.get_db()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM job_phases")
    except Exception:
        pass
    c.execute("DELETE FROM jobs")
    conn.commit()
    conn.close()


@pytest.mark.firebird
@patch("modules.scoring.db.backup_database", lambda *args, **kwargs: None)
def test_dispatcher_completes_scoring_tagging_clustering_with_mock_engines(
    pipeline_mock_db, tmp_path
):
    d_scoring = tmp_path / "scoring_folder"
    d_tag = tmp_path / "tag_folder"
    d_cluster = tmp_path / "cluster_folder"
    d_scoring.mkdir()
    d_tag.mkdir()
    d_cluster.mkdir()

    scoring_r = ScoringRunner(scoring_engine=MockScoringEngine(), liqe_scorer=MockLiqeScorer())
    tagging_r = TaggingRunner(tagging_engine=MockTaggingEngine())
    cluster_r = ClusteringRunner(clustering_engine=MockClusteringEngine())

    d = JobDispatcher(
        scoring_runner=scoring_r,
        tagging_runner=tagging_r,
        clustering_runner=cluster_r,
        poll_interval=5.0,
    )

    j_score, _ = db.enqueue_job(
        str(d_scoring),
        phase_code="scoring",
        job_type="scoring",
        queue_payload={"input_path": str(d_scoring)},
    )
    j_tag, _ = db.enqueue_job(
        str(d_tag),
        phase_code="keywords",
        job_type="tagging",
        queue_payload={"input_path": str(d_tag)},
    )
    j_clust, _ = db.enqueue_job(
        str(d_cluster),
        phase_code="clustering",
        job_type="clustering",
        queue_payload={"input_path": str(d_cluster)},
    )

    deadline = time.time() + 30.0
    while time.time() < deadline:
        d.tick_for_tests()
        if all(
            db.get_job_by_id(j)["status"] == "completed"
            for j in (j_score, j_tag, j_clust)
        ):
            break
        time.sleep(0.05)

    assert db.get_job_by_id(j_score)["status"] == "completed"
    assert db.get_job_by_id(j_tag)["status"] == "completed"
    assert db.get_job_by_id(j_clust)["status"] == "completed"
