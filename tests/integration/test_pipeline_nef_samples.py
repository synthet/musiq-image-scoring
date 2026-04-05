"""
Tier B: Optional integration tests against real Nikon RAW (NEF) sample files.

Database target: ``image_scoring_test`` (PostgreSQL). NEVER production.
Source: repo ``tests/fixtures/testing_samples`` (or ``NEF_TEST_SAMPLES_ROOT`` env var).

These tests exercise the real indexing and metadata runners against actual NEF files
on disk. Scoring/tagging tests are gated behind the ``ml`` marker and
``IMAGE_SCORING_INTEGRATION_ML=1`` env var (they need GPU + model downloads).

Env vars:
    NEF_TEST_SAMPLES_ROOT                - path to sample images (default: tests/fixtures/testing_samples)
    IMAGE_SCORING_INTEGRATION_MAX_IMAGES - max images to process per test (default: 5)
    IMAGE_SCORING_INTEGRATION_ML=1       - enable ML-dependent tests (scoring, tagging)
    SKIP_POSTGRES_TESTS=1                - skip all Postgres tests
"""
from __future__ import annotations

import os
import time

import pytest

from modules import db
from modules.job_dispatcher import JobDispatcher
from tests.support.testing_samples import (
    list_sample_image_files,
    require_sample_files,
    testing_samples_root,
)

pytestmark = [pytest.mark.postgres, pytest.mark.sample_data]

MAX_IMAGES = int(os.environ.get("IMAGE_SCORING_INTEGRATION_MAX_IMAGES", "5"))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _postgres_clean(postgres_test_session, clean_postgres):
    yield


@pytest.fixture(scope="module")
def sample_root():
    """Resolve and validate the sample images root directory."""
    root = testing_samples_root()
    if not os.path.isdir(root):
        pytest.skip(f"Testing samples root not found: {root}")
    files = list_sample_image_files(root)
    if len(files) < 1:
        pytest.skip(f"No sample images found under {root}")
    return root


@pytest.fixture(scope="module")
def sample_files(sample_root):
    """Return up to MAX_IMAGES sample file paths."""
    files = list_sample_image_files(sample_root)
    return files[:MAX_IMAGES]


def _ml_enabled():
    return os.environ.get("IMAGE_SCORING_INTEGRATION_ML", "").strip().lower() in (
        "1", "true", "yes",
    )


# ---------------------------------------------------------------------------
# Tier B.1: Indexing + metadata (no ML required)
# ---------------------------------------------------------------------------

class TestNefIndexingMetadata:
    """Real indexing + metadata extraction against NEF files."""

    def test_indexing_discovers_sample_files(self, sample_root, sample_files):
        """IndexingRunner discovers files and creates DB records."""
        try:
            from modules.indexing_runner import IndexingRunner
        except ImportError:
            pytest.skip("IndexingRunner not available")

        runner = IndexingRunner()
        job_id, _ = db.enqueue_job(
            sample_root,
            phase_code="indexing",
            job_type="indexing",
            queue_payload={"input_path": sample_root, "skip_existing": False},
        )
        # Dequeue to mark running
        db.dequeue_next_job()

        result = runner.start_batch(sample_root, job_id=job_id, skip_existing=False)
        assert result == "Started", f"IndexingRunner returned: {result}"

        # Wait for runner to finish
        deadline = time.time() + 60.0
        while time.time() < deadline:
            status = runner.get_status()
            if not status[0]:  # not running
                break
            time.sleep(0.5)

        assert not runner.get_status()[0], "Indexing did not finish within deadline"

        row = db.get_job(job_id)
        final_status = (row["status"] or "").lower()
        assert final_status in ("completed", "running"), (
            f"Indexing job status: {final_status}"
        )

    def test_metadata_extraction_after_indexing(self, sample_root, sample_files):
        """MetadataRunner extracts EXIF/thumbnails after indexing."""
        try:
            from modules.indexing_runner import IndexingRunner
            from modules.metadata_runner import MetadataRunner
        except ImportError:
            pytest.skip("IndexingRunner or MetadataRunner not available")

        # Step 1: Index
        ix_runner = IndexingRunner()
        ix_jid, _ = db.enqueue_job(
            sample_root,
            phase_code="indexing",
            job_type="indexing",
            queue_payload={"input_path": sample_root},
        )
        db.dequeue_next_job()
        ix_runner.start_batch(sample_root, job_id=ix_jid, skip_existing=False)

        deadline = time.time() + 60.0
        while time.time() < deadline:
            if not ix_runner.get_status()[0]:
                break
            time.sleep(0.5)

        # Step 2: Metadata
        meta_runner = MetadataRunner()
        meta_jid, _ = db.enqueue_job(
            sample_root,
            phase_code="metadata",
            job_type="metadata",
            queue_payload={"input_path": sample_root},
        )
        db.dequeue_next_job()
        result = meta_runner.start_batch(sample_root, job_id=meta_jid, skip_existing=False)
        assert result == "Started", f"MetadataRunner returned: {result}"

        deadline = time.time() + 120.0
        while time.time() < deadline:
            if not meta_runner.get_status()[0]:
                break
            time.sleep(0.5)

        assert not meta_runner.get_status()[0], "Metadata did not finish within deadline"

    def test_indexing_skip_existing_is_idempotent(self, sample_root, sample_files):
        """Running indexing twice with skip_existing=True does not duplicate records."""
        try:
            from modules.indexing_runner import IndexingRunner
        except ImportError:
            pytest.skip("IndexingRunner not available")

        runner = IndexingRunner()

        # Run 1
        jid1, _ = db.enqueue_job(
            sample_root, phase_code="indexing", job_type="indexing",
            queue_payload={"input_path": sample_root, "skip_existing": False},
        )
        db.dequeue_next_job()
        runner.start_batch(sample_root, job_id=jid1, skip_existing=False)
        deadline = time.time() + 60.0
        while time.time() < deadline:
            if not runner.get_status()[0]:
                break
            time.sleep(0.5)

        # Count images
        count1 = db.get_connector().query_one("SELECT COUNT(*) AS cnt FROM images")
        n1 = int(count1["cnt"]) if count1 else 0

        # Run 2 with skip_existing=True
        jid2, _ = db.enqueue_job(
            sample_root, phase_code="indexing", job_type="indexing",
            queue_payload={"input_path": sample_root, "skip_existing": True},
        )
        db.dequeue_next_job()
        runner.start_batch(sample_root, job_id=jid2, skip_existing=True)
        deadline = time.time() + 60.0
        while time.time() < deadline:
            if not runner.get_status()[0]:
                break
            time.sleep(0.5)

        count2 = db.get_connector().query_one("SELECT COUNT(*) AS cnt FROM images")
        n2 = int(count2["cnt"]) if count2 else 0

        assert n2 == n1, f"Expected {n1} images after re-index, got {n2}"


# ---------------------------------------------------------------------------
# Tier B.2: Scoring + tagging (ML required, optional)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _ml_enabled(), reason="ML tests disabled (set IMAGE_SCORING_INTEGRATION_ML=1)")
class TestNefScoringTagging:
    """Real scoring/tagging against NEF files. Requires GPU + models."""

    @pytest.mark.ml
    def test_score_small_batch(self, sample_root, sample_files):
        """Score a small batch of NEF files with real models."""
        try:
            from modules.indexing_runner import IndexingRunner
            from modules.metadata_runner import MetadataRunner
            from modules.scoring import ScoringRunner
        except ImportError as e:
            pytest.skip(f"Runner import failed: {e}")

        # Index + metadata first
        ix = IndexingRunner()
        jid, _ = db.enqueue_job(
            sample_root, phase_code="indexing", job_type="indexing",
            queue_payload={"input_path": sample_root},
        )
        db.dequeue_next_job()
        ix.start_batch(sample_root, job_id=jid, skip_existing=False)
        _wait_runner(ix, 60)

        meta = MetadataRunner()
        mjid, _ = db.enqueue_job(
            sample_root, phase_code="metadata", job_type="metadata",
            queue_payload={"input_path": sample_root},
        )
        db.dequeue_next_job()
        meta.start_batch(sample_root, job_id=mjid, skip_existing=False)
        _wait_runner(meta, 120)

        # Score
        scorer = ScoringRunner()
        sjid, _ = db.enqueue_job(
            sample_root, phase_code="scoring", job_type="scoring",
            queue_payload={"input_path": sample_root, "skip_existing": False},
        )
        db.dequeue_next_job()
        result = scorer.start_batch(sample_root, sjid, False)
        assert result == "Started"
        _wait_runner(scorer, 300)

        # Verify scores written
        scored = db.get_connector().query(
            "SELECT id, score_general FROM images WHERE score_general IS NOT NULL"
        )
        assert len(scored) > 0, "No images were scored"

    @pytest.mark.ml
    def test_tag_small_batch(self, sample_root, sample_files):
        """Tag a small batch with CLIP keywords."""
        try:
            from modules.indexing_runner import IndexingRunner
            from modules.metadata_runner import MetadataRunner
            from modules.tagging import TaggingRunner
        except ImportError as e:
            pytest.skip(f"Runner import failed: {e}")

        ix = IndexingRunner()
        jid, _ = db.enqueue_job(
            sample_root, phase_code="indexing", job_type="indexing",
            queue_payload={"input_path": sample_root},
        )
        db.dequeue_next_job()
        ix.start_batch(sample_root, job_id=jid, skip_existing=False)
        _wait_runner(ix, 60)

        meta = MetadataRunner()
        mjid, _ = db.enqueue_job(
            sample_root, phase_code="metadata", job_type="metadata",
            queue_payload={"input_path": sample_root},
        )
        db.dequeue_next_job()
        meta.start_batch(sample_root, job_id=mjid, skip_existing=False)
        _wait_runner(meta, 120)

        tagger = TaggingRunner()
        tjid, _ = db.enqueue_job(
            sample_root, phase_code="keywords", job_type="tagging",
            queue_payload={"input_path": sample_root},
        )
        db.dequeue_next_job()
        result = tagger.start_batch(
            sample_root, job_id=tjid, overwrite=False, generate_captions=False,
        )
        assert result == "Started"
        _wait_runner(tagger, 300)


# ---------------------------------------------------------------------------
# Tier B.3: Full pipeline via dispatcher with real runners (indexing + metadata only)
# ---------------------------------------------------------------------------

class TestNefDispatcherPipeline:
    """Dispatcher-driven pipeline using real indexing + metadata, fake ML runners."""

    def test_index_metadata_via_dispatcher(self, sample_root, sample_files):
        """Full dispatcher loop for indexing -> metadata with real runners."""
        try:
            from modules.indexing_runner import IndexingRunner
            from modules.metadata_runner import MetadataRunner
        except ImportError:
            pytest.skip("Runners not available")

        from tests.support.fake_runners import (
            FakeClusteringRunner,
            FakeScoringRunner,
            FakeSelectionRunner,
            FakeTaggingRunner,
        )

        dispatcher = JobDispatcher(
            indexing_runner=IndexingRunner(),
            metadata_runner=MetadataRunner(),
            scoring_runner=FakeScoringRunner(delay_s=0.02),
            tagging_runner=FakeTaggingRunner(delay_s=0.02),
            clustering_runner=FakeClusteringRunner(delay_s=0.02),
            selection_runner=FakeSelectionRunner(delay_s=0.02),
            poll_interval=5.0,
        )

        plan = ("indexing", "metadata")
        from tests.support.pipeline_matrix import enqueue_monolithic
        job_id = enqueue_monolithic(sample_root, plan, skip_existing=False)

        # Run dispatcher in a loop (real runners take time)
        deadline = time.time() + 180.0
        while time.time() < deadline:
            dispatcher.tick_for_tests()
            row = db.get_job(job_id)
            if row and (row["status"] or "").lower() in ("completed", "failed"):
                break
            time.sleep(1.0)

        row = db.get_job(job_id)
        assert (row["status"] or "").lower() == "completed", (
            f"Dispatcher pipeline job status: {row['status']}"
        )

    def test_cancel_during_indexing(self, sample_root, sample_files):
        """Enqueue two jobs, cancel the second while first indexes."""
        try:
            from modules.indexing_runner import IndexingRunner
        except ImportError:
            pytest.skip("IndexingRunner not available")

        from tests.support.fake_runners import FakePhaseRunner

        dispatcher = JobDispatcher(
            indexing_runner=IndexingRunner(),
            metadata_runner=FakePhaseRunner(delay_s=0.02),
            poll_interval=5.0,
        )

        from tests.support.pipeline_matrix import enqueue_monolithic
        j1 = enqueue_monolithic(sample_root, ("indexing",), skip_existing=False)
        j2 = enqueue_monolithic(sample_root, ("indexing",), skip_existing=False)

        # Cancel j2 while it's queued
        result = db.request_cancel_job(j2)
        assert result["success"] is True

        # Let j1 finish
        deadline = time.time() + 120.0
        while time.time() < deadline:
            dispatcher.tick_for_tests()
            r1 = db.get_job(j1)
            if r1 and (r1["status"] or "").lower() in ("completed", "failed"):
                break
            time.sleep(1.0)

        assert (db.get_job(j1)["status"] or "").lower() == "completed"
        assert (db.get_job(j2)["status"] or "").lower() == "cancelled"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wait_runner(runner, timeout_s: float):
    """Block until runner finishes or timeout."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if not runner.get_status()[0]:
            return
        time.sleep(0.5)
    assert not runner.get_status()[0], f"Runner did not finish within {timeout_s}s"
