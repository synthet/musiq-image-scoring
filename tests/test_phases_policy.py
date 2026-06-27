import pytest

from modules.phases import PhaseCode, PhaseExecutor, PhaseRegistry, SCORING_EXECUTOR_VERSION
from modules import phases_policy


@pytest.fixture(autouse=True)
def _reset_phase_registry():
    PhaseRegistry._executors.clear()
    yield
    PhaseRegistry._executors.clear()


def test_policy_runs_when_status_missing(monkeypatch):
    monkeypatch.setattr(phases_policy.db, "get_image_phase_statuses", lambda image_id: {})
    monkeypatch.setattr(phases_policy.db, "is_image_scoring_complete", lambda image_id: False)
    decision = phases_policy.explain_phase_run_decision(1, PhaseCode.SCORING)
    assert decision["should_run"] is True
    assert decision["reason"] == "missing_phase_status"


def test_policy_skips_when_status_missing_but_data_complete(monkeypatch):
    """No phase_status row + data already present (e.g. backfill) must not re-run."""
    monkeypatch.setattr(phases_policy.db, "get_image_phase_statuses", lambda image_id: {})
    monkeypatch.setattr(phases_policy.db, "is_image_scoring_complete", lambda image_id: True)
    decision = phases_policy.explain_phase_run_decision(1, PhaseCode.SCORING)
    assert decision["should_run"] is False
    assert decision["reason"] == "data_complete_missing_phase_status"


def test_policy_skips_when_done_same_version(monkeypatch):
    monkeypatch.setattr(
        phases_policy.db,
        "get_image_phase_statuses",
        lambda image_id: {"scoring": {"status": "done", "executor_version": "1.2.3"}},
    )
    monkeypatch.setattr(
        phases_policy.db,
        "is_image_scoring_complete",
        lambda image_id: True,
    )
    PhaseRegistry.register(PhaseExecutor(code=PhaseCode.SCORING, executor_version="1.2.3"))

    decision = phases_policy.explain_phase_run_decision(1, PhaseCode.SCORING)
    assert decision["should_run"] is False
    assert decision["reason"] == "already_done_current_executor"


def test_policy_runs_when_done_but_thumbnail_missing(monkeypatch):
    monkeypatch.setattr(
        phases_policy.db,
        "get_image_phase_statuses",
        lambda image_id: {"metadata": {"status": "done", "executor_version": "1.0.0"}},
    )
    monkeypatch.setattr(phases_policy.db, "is_image_metadata_complete", lambda image_id: True)
    monkeypatch.setattr(
        phases_policy.db,
        "get_image_metadata_asset_gap_reason",
        lambda image_id: "missing_thumbnail",
    )
    PhaseRegistry.register(PhaseExecutor(code=PhaseCode.METADATA, executor_version="1.0.0"))

    decision = phases_policy.explain_phase_run_decision(1, PhaseCode.METADATA)
    assert decision["should_run"] is True
    assert decision["reason"] == "missing_thumbnail"


def test_policy_runs_when_done_but_scoring_data_missing(monkeypatch):
    """If status is 'done' but actual scores are missing, should_run must be True."""
    monkeypatch.setattr(
        phases_policy.db,
        "get_image_phase_statuses",
        lambda image_id: {"scoring": {"status": "done", "executor_version": "1.2.3"}},
    )
    monkeypatch.setattr(
        phases_policy.db,
        "is_image_scoring_complete",
        lambda image_id: False,
    )
    PhaseRegistry.register(PhaseExecutor(code=PhaseCode.SCORING, executor_version="1.2.3"))

    decision = phases_policy.explain_phase_run_decision(1, PhaseCode.SCORING)
    assert decision["should_run"] is True
    assert decision["reason"] == "missing_scoring_data"


def test_policy_runs_when_done_but_version_changed(monkeypatch):
    monkeypatch.setattr(
        phases_policy.db,
        "get_image_phase_statuses",
        lambda image_id: {"keywords": {"status": "done", "executor_version": "1.0.0"}},
    )
    PhaseRegistry.register(PhaseExecutor(code=PhaseCode.KEYWORDS, executor_version="2.0.0"))

    decision = phases_policy.explain_phase_run_decision(1, PhaseCode.KEYWORDS)
    assert decision["should_run"] is True
    assert decision["reason"] == "executor_version_changed"


def test_policy_skips_when_running(monkeypatch):
    monkeypatch.setattr(
        phases_policy.db,
        "get_image_phase_statuses",
        lambda image_id: {"scoring": {"status": "running"}},
    )
    decision = phases_policy.explain_phase_run_decision(1, PhaseCode.SCORING)
    assert decision["should_run"] is False
    assert decision["reason"] == "already_running"


def test_policy_runs_when_failed(monkeypatch):
    monkeypatch.setattr(
        phases_policy.db,
        "get_image_phase_statuses",
        lambda image_id: {"scoring": {"status": "failed"}},
    )
    monkeypatch.setattr(phases_policy.db, "is_image_scoring_complete", lambda image_id: False)
    decision = phases_policy.explain_phase_run_decision(1, PhaseCode.SCORING)
    assert decision["should_run"] is True
    assert decision["reason"] == "status_failed"


def test_policy_skips_when_status_not_started_but_data_complete(monkeypatch):
    """Phase row in not_started state with data already present must not re-run."""
    monkeypatch.setattr(
        phases_policy.db,
        "get_image_phase_statuses",
        lambda image_id: {"scoring": {"status": "not_started"}},
    )
    monkeypatch.setattr(phases_policy.db, "is_image_scoring_complete", lambda image_id: True)
    decision = phases_policy.explain_phase_run_decision(1, PhaseCode.SCORING)
    assert decision["should_run"] is False
    assert decision["reason"] == "data_complete_status_not_started"


def test_policy_skips_when_status_failed_but_data_complete(monkeypatch):
    """Phase row in failed state with data present (e.g. partial write) must not re-run."""
    monkeypatch.setattr(
        phases_policy.db,
        "get_image_phase_statuses",
        lambda image_id: {"scoring": {"status": "failed"}},
    )
    monkeypatch.setattr(phases_policy.db, "is_image_scoring_complete", lambda image_id: True)
    decision = phases_policy.explain_phase_run_decision(1, PhaseCode.SCORING)
    assert decision["should_run"] is False
    assert decision["reason"] == "data_complete_status_failed"


def test_policy_force_run(monkeypatch):
    monkeypatch.setattr(
        phases_policy.db,
        "get_image_phase_statuses",
        lambda image_id: {"scoring": {"status": "done", "executor_version": "1.0.0"}},
    )
    # Even if versions match, force_run should trigger run.
    decision = phases_policy.explain_phase_run_decision(
        1, PhaseCode.SCORING, current_executor_version="1.0.0", force_run=True
    )
    assert decision["should_run"] is True
    assert decision["reason"] == "force_run_requested"


def test_policy_runs_when_keyword_data_missing(monkeypatch):
    """If keywords status is 'done' but no keywords exist, should_run must be True."""
    monkeypatch.setattr(
        phases_policy.db,
        "get_image_phase_statuses",
        lambda image_id: {"keywords": {"status": "done", "executor_version": "1.0.0"}},
    )
    monkeypatch.setattr(
        phases_policy.db,
        "is_image_keywords_complete",
        lambda image_id: False,
    )
    PhaseRegistry.register(PhaseExecutor(code=PhaseCode.KEYWORDS, executor_version="1.0.0"))

    decision = phases_policy.explain_phase_run_decision(1, PhaseCode.KEYWORDS)
    assert decision["should_run"] is True
    assert decision["reason"] == "missing_keyword_data"


def test_policy_runs_when_indexing_data_missing(monkeypatch):
    monkeypatch.setattr(
        phases_policy.db,
        "get_image_phase_statuses",
        lambda image_id: {"indexing": {"status": "done", "executor_version": "1.0.0"}},
    )
    monkeypatch.setattr(
        phases_policy.db,
        "is_image_indexing_complete",
        lambda image_id: False,
    )
    PhaseRegistry.register(PhaseExecutor(code=PhaseCode.INDEXING, executor_version="1.0.0"))

    decision = phases_policy.explain_phase_run_decision(1, PhaseCode.INDEXING)
    assert decision["should_run"] is True
    assert decision["reason"] == "missing_indexing_data"


def test_policy_skips_valid_unrated_metadata(monkeypatch):
    """Metadata status='done' with rating=0/label='' is considered complete."""
    monkeypatch.setattr(
        phases_policy.db,
        "get_image_phase_statuses",
        lambda image_id: {"metadata": {"status": "done", "executor_version": "1.0.0"}},
    )
    monkeypatch.setattr(
        phases_policy.db,
        "get_image_metadata_asset_gap_reason",
        lambda image_id: None,
    )
    monkeypatch.setattr(
        phases_policy.db,
        "is_image_metadata_complete",
        lambda image_id: True, # In my new logic, rating=0 is complete
    )
    PhaseRegistry.register(PhaseExecutor(code=PhaseCode.METADATA, executor_version="1.0.0"))

    decision = phases_policy.explain_phase_run_decision(1, PhaseCode.METADATA)
    assert decision["should_run"] is False
    assert decision["reason"] == "already_done_current_executor"


def test_policy_skips_bird_species_when_done_same_version(monkeypatch):
    monkeypatch.setattr(
        phases_policy.db,
        "get_image_phase_statuses",
        lambda image_id: {"bird_species": {"status": "done", "executor_version": "1.0.0"}},
    )
    monkeypatch.setattr(
        phases_policy.db,
        "is_image_bird_species_complete",
        lambda image_id: True,
    )
    PhaseRegistry.register(PhaseExecutor(code=PhaseCode.BIRD_SPECIES, executor_version="1.0.0"))

    decision = phases_policy.explain_phase_run_decision(1, PhaseCode.BIRD_SPECIES)
    assert decision["should_run"] is False
    assert decision["reason"] == "already_done_current_executor"


def test_policy_runs_culling_when_similarity_artefacts_missing(monkeypatch):
    """Re-run when IPS says done but the healing completeness predicate still fails."""
    monkeypatch.setattr(
        phases_policy.db,
        "get_image_phase_statuses",
        lambda image_id: {"culling": {"status": "done", "executor_version": "1.0.0"}},
    )
    monkeypatch.setattr(
        phases_policy.db,
        "is_image_culling_work_complete",
        lambda image_id: False,
    )
    PhaseRegistry.register(
        PhaseExecutor(code=PhaseCode.CULLING, executor_version="1.0.0"),
    )

    decision = phases_policy.explain_phase_run_decision(
        1, PhaseCode.CULLING, current_executor_version="1.0.0"
    )
    assert decision["should_run"] is True
    assert decision["reason"] == "missing_culling_work"


def test_policy_skips_culling_when_similarity_artefacts_present(monkeypatch):
    monkeypatch.setattr(
        phases_policy.db,
        "get_image_phase_statuses",
        lambda image_id: {"culling": {"status": "done", "executor_version": "1.0.0"}},
    )
    monkeypatch.setattr(
        phases_policy.db,
        "is_image_culling_work_complete",
        lambda image_id: True,
    )
    PhaseRegistry.register(
        PhaseExecutor(code=PhaseCode.CULLING, executor_version="1.0.0"),
    )

    decision = phases_policy.explain_phase_run_decision(
        1, PhaseCode.CULLING, current_executor_version="1.0.0"
    )
    assert decision["should_run"] is False
    assert decision["reason"] == "already_done_current_executor"


def test_policy_runs_bird_species_when_version_changed(monkeypatch):
    monkeypatch.setattr(
        phases_policy.db,
        "get_image_phase_statuses",
        lambda image_id: {"bird_species": {"status": "done", "executor_version": "1.0.0"}},
    )
    PhaseRegistry.register(PhaseExecutor(code=PhaseCode.BIRD_SPECIES, executor_version="2.0.0"))

    decision = phases_policy.explain_phase_run_decision(1, PhaseCode.BIRD_SPECIES)
    assert decision["should_run"] is True
    assert decision["reason"] == "executor_version_changed"


def test_policy_skips_legacy_null_executor_version_when_data_complete(monkeypatch):
    """Pre-versioning IPS rows (executor_version=NULL) must not force stale_executor reruns."""
    monkeypatch.setattr(
        phases_policy.db,
        "get_image_phase_statuses",
        lambda image_id: {"metadata": {"status": "done", "executor_version": None}},
    )
    monkeypatch.setattr(
        phases_policy.db,
        "get_image_metadata_asset_gap_reason",
        lambda image_id: None,
    )
    monkeypatch.setattr(
        phases_policy.db,
        "is_image_metadata_complete",
        lambda image_id: True,
    )
    PhaseRegistry.register(PhaseExecutor(code=PhaseCode.METADATA, executor_version="1.0.0"))

    decision = phases_policy.explain_phase_run_decision(1, PhaseCode.METADATA)
    assert decision["should_run"] is False
    assert decision["reason"] == "already_done_current_executor"


def test_explain_uses_prefetched_statuses_without_db_call(monkeypatch):
    """When prefetched_statuses is supplied, the per-image DB fetch is skipped."""
    def _boom(_image_id):
        raise AssertionError("get_image_phase_statuses must not be called when prefetched")

    monkeypatch.setattr(phases_policy.db, "get_image_phase_statuses", _boom)
    monkeypatch.setattr(phases_policy.db, "is_image_scoring_complete", lambda _i: False)

    decision = phases_policy.explain_phase_run_decision(
        1,
        PhaseCode.SCORING,
        prefetched_statuses={"scoring": {"status": "not_started"}},
    )
    assert decision["should_run"] is True
    assert decision["reason"] == "status_not_started"


def test_explain_prefetched_matches_per_image_decision(monkeypatch):
    """A prefetched slice and the per-image fetch must yield identical decisions."""
    statuses = {"scoring": {"status": "done", "executor_version": "1.2.3"}}
    monkeypatch.setattr(phases_policy.db, "get_image_phase_statuses", lambda _i: statuses)
    monkeypatch.setattr(phases_policy.db, "is_image_scoring_complete", lambda _i: True)
    PhaseRegistry.register(PhaseExecutor(code=PhaseCode.SCORING, executor_version="1.2.3"))

    per_image = phases_policy.explain_phase_run_decision(1, PhaseCode.SCORING)
    prefetched = phases_policy.explain_phase_run_decision(
        1, PhaseCode.SCORING, prefetched_statuses=statuses
    )
    assert per_image["should_run"] == prefetched["should_run"] is False
    assert per_image["reason"] == prefetched["reason"] == "already_done_current_executor"


def test_policy_skips_scoring_when_canonical_executor_version_matches(monkeypatch):
    """IPS rows with SCORING_EXECUTOR_VERSION must match registry, not per-model VERSION tags."""
    monkeypatch.setattr(
        phases_policy.db,
        "get_image_phase_statuses",
        lambda image_id: {
            "scoring": {"status": "done", "executor_version": SCORING_EXECUTOR_VERSION},
        },
    )
    monkeypatch.setattr(
        phases_policy.db,
        "is_image_scoring_complete",
        lambda image_id: True,
    )
    PhaseRegistry.register(
        PhaseExecutor(code=PhaseCode.SCORING, executor_version=SCORING_EXECUTOR_VERSION),
    )

    decision = phases_policy.explain_phase_run_decision(1, PhaseCode.SCORING)
    assert decision["should_run"] is False
    assert decision["reason"] == "already_done_current_executor"


def test_culling_not_started_runs_when_healing_predicate_incomplete(monkeypatch):
    """Culling policy must follow healing completeness, not cull_decision alone."""
    monkeypatch.setattr(
        phases_policy.db,
        "get_image_phase_statuses",
        lambda _i: {"culling": {"status": "not_started", "executor_version": "1.0.0"}},
    )
    monkeypatch.setattr(phases_policy.db, "is_image_culling_work_complete", lambda _i: False)

    decision = phases_policy.explain_phase_run_decision(1, PhaseCode.CULLING)
    assert decision["should_run"] is True
    assert decision["reason"] == "status_not_started"


def test_culling_not_started_skips_when_healing_predicate_complete(monkeypatch):
    monkeypatch.setattr(
        phases_policy.db,
        "get_image_phase_statuses",
        lambda _i: {"culling": {"status": "not_started", "executor_version": "1.0.0"}},
    )
    monkeypatch.setattr(phases_policy.db, "is_image_culling_work_complete", lambda _i: True)

    decision = phases_policy.explain_phase_run_decision(1, PhaseCode.CULLING)
    assert decision["should_run"] is False
    assert decision["reason"] == "data_complete_status_not_started"
