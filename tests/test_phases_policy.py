import pytest

from modules.phases import PhaseCode, PhaseExecutor, PhaseRegistry
from modules import phases_policy


@pytest.fixture(autouse=True)
def _reset_phase_registry():
    PhaseRegistry._executors.clear()
    yield
    PhaseRegistry._executors.clear()


def test_policy_runs_when_status_missing(monkeypatch):
    monkeypatch.setattr(phases_policy.db, "get_image_phase_statuses", lambda image_id: {})
    decision = phases_policy.explain_phase_run_decision(1, PhaseCode.SCORING)
    assert decision["should_run"] is True
    assert decision["reason"] == "missing_phase_status"


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
    decision = phases_policy.explain_phase_run_decision(1, PhaseCode.SCORING)
    assert decision["should_run"] is True
    assert decision["reason"] == "status_failed"


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
        "is_image_metadata_complete",
        lambda image_id: True, # In my new logic, rating=0 is complete
    )
    PhaseRegistry.register(PhaseExecutor(code=PhaseCode.METADATA, executor_version="1.0.0"))

    decision = phases_policy.explain_phase_run_decision(1, PhaseCode.METADATA)
    assert decision["should_run"] is False
    assert decision["reason"] == "already_done_current_executor"
