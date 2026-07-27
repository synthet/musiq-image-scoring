"""
Unit tests for PipelineOrchestrator phase order, cancel, and failure propagation.

Issue #309 / TEST_IMPROVEMENTS_PLAN P2.1 named modules/engine.py, but the
scoring → culling → keywords coordinator is PipelineOrchestrator. These tests
use controllable fake runners and an in-memory DB stub — no ML, GPU, or live DB.

Canonical order (PIPELINE_TERMINOLOGY / PHASE_ORDER):
  scoring → culling (selection_runner) → keywords (tagging_runner)
"""
from __future__ import annotations

from typing import Any, Callable, Optional

import pytest

from modules.phases import PhaseCode
from modules.pipeline_orchestrator import PipelineOrchestrator


FOLDER = "D:/orch-unit/test-folder"
PHASES_SKC = ["scoring", "culling", "keywords"]


# ---------------------------------------------------------------------------
# Controllable runners (synchronous — no threads / sleeps)
# ---------------------------------------------------------------------------


class ControllableRunner:
    """Minimal runner API: start_batch / get_status / stop with finish() control."""

    def __init__(self, name: str, stub: "InMemoryJobDb"):
        self.name = name
        self.stub = stub
        self.is_running = False
        self.stop_calls = 0
        self.start_calls: list[dict[str, Any]] = []
        self._job_id: Optional[int] = None
        self.status_message = "Idle"
        self.log_history: list[str] = []

    def get_status(self):
        return (
            self.is_running,
            "\n".join(self.log_history),
            self.status_message,
            1 if not self.is_running and self._job_id else 0,
            1,
        )

    def stop(self):
        self.stop_calls += 1
        self.log_history.append("stop")
        self.is_running = False
        self.status_message = "Stopped"

    def start_batch(self, input_path: str, job_id: int = None, **kwargs: Any) -> str:
        if job_id is None:
            return f"Error: job_id required for {self.name}."
        if self.is_running:
            return "Error: Already running."
        self.is_running = True
        self._job_id = int(job_id)
        self.status_message = "Running..."
        self.log_history = ["started"]
        self.start_calls.append({"input_path": input_path, "job_id": int(job_id), **kwargs})
        return "Started"

    def finish(self, status: str = "completed", log: str = "done") -> None:
        """Mark runner idle and update the phase child job status in the stub."""
        assert self._job_id is not None, f"{self.name}: finish() before start_batch"
        self.is_running = False
        self.status_message = status
        self.log_history.append(log)
        self.stub.update_job_status(self._job_id, status, log)


# ---------------------------------------------------------------------------
# In-memory job / phase plan stub (mirrors db helpers the orchestrator calls)
# ---------------------------------------------------------------------------


class InMemoryJobDb:
    def __init__(self):
        self._next_id = 1
        self.jobs: dict[int, dict[str, Any]] = {}
        self.phases: dict[int, list[dict[str, Any]]] = {}  # root_job_id -> phase rows
        self.folder_summaries: dict[str, list[dict[str, Any]]] = {}
        self.all_phases: list[dict[str, Any]] = [
            {"code": "indexing", "optional": False, "default_skip": False},
            {"code": "metadata", "optional": False, "default_skip": False},
            {"code": "scoring", "optional": False, "default_skip": False},
            {"code": "culling", "optional": False, "default_skip": False},
            {"code": "keywords", "optional": False, "default_skip": False},
        ]
        self.fulfillment = {
            "indexing_pct": 100.0,
            "score_pct": 100.0,
            "thumbnail_pct": 100.0,
        }

    def create_job(
        self,
        input_path,
        phase_code=None,
        job_type=None,
        status="pending",
        current_phase=None,
        next_phase_index=None,
        runner_state=None,
        **_kwargs,
    ):
        jid = self._next_id
        self._next_id += 1
        self.jobs[jid] = {
            "id": jid,
            "input_path": input_path,
            "phase_code": phase_code,
            "job_type": job_type or phase_code,
            "status": status,
            "log": None,
            "current_phase": current_phase,
            "next_phase_index": next_phase_index,
            "runner_state": runner_state,
        }
        return jid

    def create_job_phases(self, job_id, phase_codes, first_phase_state=None):
        rows = []
        for idx, code in enumerate(phase_codes):
            if idx > 0:
                state = "pending"
            elif first_phase_state == "queued":
                state = "queued"
            else:
                state = "running"
            rows.append(
                {
                    "phase_order": idx,
                    "phase_code": code,
                    "state": state,
                    "started_at": None,
                    "completed_at": None,
                    "error_message": None,
                }
            )
        self.phases[job_id] = rows
        return list(rows)

    def get_job_phases(self, job_id, tx=None):
        return [dict(r) for r in self.phases.get(job_id, [])]

    def get_next_running_job_phase(self, job_id, tx=None):
        for row in self.phases.get(job_id, []):
            if (row.get("state") or "").strip().lower() == "running":
                return row["phase_code"]
        return None

    def set_job_phase_state(self, job_id, phase_code, state, error_message=None, tx=None):
        rows = self.phases.get(job_id, [])
        target = None
        for row in rows:
            if row["phase_code"] == phase_code:
                target = row
                break
        if target is None:
            return None
        # Accept orchestrator spellings (cancelled / canceled / failed / completed / skipped / …)
        target["state"] = state
        if error_message is not None:
            target["error_message"] = error_message
        new_state = (state or "").strip().lower()
        if new_state in {"completed", "skipped"}:
            order = target["phase_order"]
            for row in rows:
                if row["phase_order"] > order and (row.get("state") or "") == "pending":
                    row["state"] = "running"
                    break
        return self.get_job_phases(job_id)

    def get_job_by_id(self, job_id):
        job = self.jobs.get(job_id)
        return dict(job) if job else None

    def update_job_status(
        self,
        job_id,
        status,
        log=None,
        current_phase=None,
        next_phase_index=None,
        runner_state=None,
    ):
        job = self.jobs.get(job_id)
        if not job:
            return
        job["status"] = status
        if log is not None:
            job["log"] = log
        if current_phase is not None:
            job["current_phase"] = current_phase
        if next_phase_index is not None:
            job["next_phase_index"] = next_phase_index
        if runner_state is not None:
            job["runner_state"] = runner_state

    def set_job_execution_cursor(self, job_id, current_phase=None, next_phase_index=None, runner_state=None):
        self.update_job_status(
            job_id,
            self.jobs[job_id]["status"],
            current_phase=current_phase,
            next_phase_index=next_phase_index,
            runner_state=runner_state,
        )

    def get_folder_phase_summary(self, folder_path, force_refresh=False):
        return list(self.folder_summaries.get(folder_path, []))

    def get_all_phases(self, enabled_only=True):
        return list(self.all_phases)

    def get_folder_fulfillment_stats_for_path(self, folder_path):
        return dict(self.fulfillment)

    def set_folder_phase_status(self, **_kwargs):
        return None

    def invalidate_folder_phase_aggregates(self, **_kwargs):
        return None

    def refresh_folder_phase_aggregates_with_ancestors(self, **_kwargs):
        return None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def stub() -> InMemoryJobDb:
    return InMemoryJobDb()


@pytest.fixture
def runners(stub: InMemoryJobDb):
    scoring = ControllableRunner("scoring", stub)
    tagging = ControllableRunner("keywords", stub)  # keywords phase → tagging_runner
    selection = ControllableRunner("culling", stub)  # culling phase → selection_runner
    return scoring, tagging, selection


@pytest.fixture
def orch(monkeypatch, stub: InMemoryJobDb, runners):
    scoring, tagging, selection = runners

    monkeypatch.setattr("modules.pipeline_orchestrator.db", stub)
    monkeypatch.setattr(
        "modules.pipeline_orchestrator.log_phase_transition",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "modules.pipeline_orchestrator.config.get_config_value",
        lambda *a, **k: False,
    )
    monkeypatch.setattr(
        "modules.pipeline_orchestrator.config.get_config_section",
        lambda *a, **k: {},
    )

    o = PipelineOrchestrator(
        scoring_runner=scoring,
        tagging_runner=tagging,
        selection_runner=selection,
        indexing_runner=None,
        metadata_runner=None,
        enable_background_tick=False,
    )
    # Drain gate must not block unit tests (would call live SQL otherwise).
    monkeypatch.setattr(o, "_count_non_terminal_phase_rows", lambda *a, **k: 0)
    return o


def _drain_until_idle(orch: PipelineOrchestrator, finishers: dict[str, Callable[[], None]], max_ticks: int = 20):
    """Advance ticks; when a phase runner is idle mid-run, call its finisher once."""
    for _ in range(max_ticks):
        st = orch.get_status()
        if not st.get("active"):
            return
        phase = st.get("current_phase")
        if phase and phase in finishers:
            runner = orch._runners.get(phase)
            if runner and runner.is_running:
                finishers[phase]()
        orch.on_tick()


# ---------------------------------------------------------------------------
# Happy path / phase order
# ---------------------------------------------------------------------------


def test_happy_path_scoring_then_culling_then_keywords(orch, runners, stub):
    scoring, tagging, selection = runners
    root_id = orch.start(FOLDER, target_phases=PHASES_SKC, force_rerun=True)
    assert root_id is not None
    assert scoring.start_calls, "scoring must start first"
    assert not selection.start_calls
    assert not tagging.start_calls

    scoring.finish("completed")
    orch.on_tick()
    assert selection.start_calls, "culling must start after scoring completes"
    assert not tagging.start_calls

    selection.finish("completed")
    orch.on_tick()
    assert tagging.start_calls, "keywords must start after culling completes"

    tagging.finish("completed")
    orch.on_tick()
    assert orch.get_status()["active"] is False
    assert stub.jobs[root_id]["status"] == "completed"
    assert [c["job_id"] for c in scoring.start_calls]  # one start each
    assert len(scoring.start_calls) == 1
    assert len(selection.start_calls) == 1
    assert len(tagging.start_calls) == 1


def test_start_order_recorded_scoring_culling_keywords(orch, runners):
    scoring, tagging, selection = runners
    order: list[str] = []

    def track(name):
        def _finish():
            order.append(name)
            getattr(
                {"scoring": scoring, "culling": selection, "keywords": tagging}[name],
                "finish",
            )("completed")

        return _finish

    orch.start(FOLDER, target_phases=PHASES_SKC, force_rerun=True)
    _drain_until_idle(
        orch,
        {
            "scoring": track("scoring"),
            "culling": track("culling"),
            "keywords": track("keywords"),
        },
    )
    assert order == ["scoring", "culling", "keywords"]


def test_culling_never_starts_before_scoring_complete(orch, runners):
    scoring, tagging, selection = runners
    orch.start(FOLDER, target_phases=PHASES_SKC, force_rerun=True)
    orch.on_tick()  # scoring still running
    assert len(scoring.start_calls) == 1
    assert selection.start_calls == []
    assert tagging.start_calls == []


def test_keywords_never_starts_before_culling_complete(orch, runners):
    scoring, tagging, selection = runners
    orch.start(FOLDER, target_phases=PHASES_SKC, force_rerun=True)
    scoring.finish("completed")
    orch.on_tick()
    orch.on_tick()  # culling still running
    assert len(selection.start_calls) == 1
    assert tagging.start_calls == []


# ---------------------------------------------------------------------------
# Failure propagation
# ---------------------------------------------------------------------------


def test_scoring_failure_blocks_culling_and_keywords(orch, runners, stub):
    scoring, tagging, selection = runners
    root_id = orch.start(FOLDER, target_phases=PHASES_SKC, force_rerun=True)
    scoring.finish("failed", log="boom")
    orch.on_tick()
    assert selection.start_calls == []
    assert tagging.start_calls == []
    assert orch.get_status()["active"] is False
    phase_states = {p["phase_code"]: p["state"] for p in stub.get_job_phases(root_id)}
    assert phase_states["scoring"] == "failed"
    assert phase_states["culling"] == "pending"
    assert phase_states["keywords"] == "pending"


def test_culling_failure_blocks_keywords(orch, runners, stub):
    scoring, tagging, selection = runners
    root_id = orch.start(FOLDER, target_phases=PHASES_SKC, force_rerun=True)
    scoring.finish("completed")
    orch.on_tick()
    selection.finish("failed", log="cull failed")
    orch.on_tick()
    assert tagging.start_calls == []
    assert orch.get_status()["active"] is False
    phase_states = {p["phase_code"]: p["state"] for p in stub.get_job_phases(root_id)}
    assert phase_states["scoring"] == "completed"
    assert phase_states["culling"] == "failed"
    assert phase_states["keywords"] == "pending"


def test_keywords_failure_marks_phase_failed_and_stops(orch, runners, stub):
    scoring, tagging, selection = runners
    root_id = orch.start(FOLDER, target_phases=PHASES_SKC, force_rerun=True)
    scoring.finish("completed")
    orch.on_tick()
    selection.finish("completed")
    orch.on_tick()
    tagging.finish("failed", log="tag fail")
    orch.on_tick()
    assert orch.get_status()["active"] is False
    phase_states = {p["phase_code"]: p["state"] for p in stub.get_job_phases(root_id)}
    assert phase_states["keywords"] == "failed"


# ---------------------------------------------------------------------------
# Cancel propagation
# ---------------------------------------------------------------------------


def test_cancel_during_scoring_stops_active_runner(orch, runners, stub):
    scoring, tagging, selection = runners
    root_id = orch.start(FOLDER, target_phases=PHASES_SKC, force_rerun=True)
    msg = orch.stop(mode="cancel")
    assert "stopped" in msg.lower()
    assert scoring.stop_calls == 1
    assert selection.stop_calls == 0
    assert tagging.stop_calls == 0
    assert orch.get_status()["active"] is False
    assert stub.jobs[root_id]["status"] == "cancelled"
    assert stub.jobs[root_id]["runner_state"] == "cancelled"


def test_cancel_during_culling_only_stops_current_runner(orch, runners, stub):
    scoring, tagging, selection = runners
    root_id = orch.start(FOLDER, target_phases=PHASES_SKC, force_rerun=True)
    scoring.finish("completed")
    orch.on_tick()
    assert selection.is_running
    orch.stop(mode="cancel")
    assert scoring.stop_calls == 0  # already finished; not current
    assert selection.stop_calls == 1
    assert tagging.stop_calls == 0
    assert stub.jobs[root_id]["status"] == "cancelled"


def test_stop_when_idle_reports_not_running(orch):
    assert orch.stop() == "Pipeline wasn't running."


def test_phase_job_cancelled_status_stops_pipeline(orch, runners, stub):
    scoring, tagging, selection = runners
    root_id = orch.start(FOLDER, target_phases=PHASES_SKC, force_rerun=True)
    scoring.finish("cancelled", log="user cancel")
    orch.on_tick()
    assert selection.start_calls == []
    assert tagging.start_calls == []
    assert orch.get_status()["active"] is False
    phase_states = {p["phase_code"]: p["state"] for p in stub.get_job_phases(root_id)}
    assert phase_states["scoring"] in ("cancelled", "canceled")


# ---------------------------------------------------------------------------
# Start guards / skip / empty plan
# ---------------------------------------------------------------------------


def test_second_start_while_active_returns_same_root(orch, runners):
    scoring, _, _ = runners
    first = orch.start(FOLDER, target_phases=["scoring"], force_rerun=True)
    second = orch.start(FOLDER + "/other", target_phases=["scoring"], force_rerun=True)
    assert first == second
    assert len(scoring.start_calls) == 1


def test_empty_plan_when_phases_already_done(orch, stub, runners):
    stub.folder_summaries[FOLDER] = [
        {"code": "scoring", "status": "done"},
        {"code": "culling", "status": "done"},
        {"code": "keywords", "status": "done"},
    ]
    scoring, tagging, selection = runners
    result = orch.start(FOLDER, target_phases=PHASES_SKC, force_rerun=False)
    assert result is None
    assert orch.get_status()["active"] is False
    assert scoring.start_calls == []
    assert selection.start_calls == []
    assert tagging.start_calls == []


def test_missing_runner_skips_phase_and_advances(monkeypatch, stub):
    """Phase in plan with runner=None is skipped; next phase still starts."""
    scoring = ControllableRunner("scoring", stub)
    tagging = ControllableRunner("keywords", stub)

    monkeypatch.setattr("modules.pipeline_orchestrator.db", stub)
    monkeypatch.setattr("modules.pipeline_orchestrator.log_phase_transition", lambda *a, **k: None)
    monkeypatch.setattr("modules.pipeline_orchestrator.config.get_config_value", lambda *a, **k: False)
    monkeypatch.setattr("modules.pipeline_orchestrator.config.get_config_section", lambda *a, **k: {})

    o = PipelineOrchestrator(
        scoring_runner=scoring,
        tagging_runner=tagging,
        selection_runner=None,  # culling missing
        enable_background_tick=False,
    )
    monkeypatch.setattr(o, "_count_non_terminal_phase_rows", lambda *a, **k: 0)

    root_id = o.start(FOLDER, target_phases=PHASES_SKC, force_rerun=True)
    assert root_id is not None
    scoring.finish("completed")
    o.on_tick()
    # culling skipped → keywords should start
    assert tagging.start_calls, "keywords should start after culling skipped"
    phase_states = {p["phase_code"]: p["state"] for p in stub.get_job_phases(root_id)}
    assert phase_states["culling"] == "skipped"


def test_force_rerun_includes_done_phases(orch, stub, runners):
    stub.folder_summaries[FOLDER] = [
        {"code": "scoring", "status": "done"},
        {"code": "culling", "status": "done"},
        {"code": "keywords", "status": "done"},
    ]
    scoring, _, _ = runners
    root_id = orch.start(FOLDER, target_phases=["scoring"], force_rerun=True)
    assert root_id is not None
    assert scoring.start_calls


def test_root_job_terminal_cancelled_matches_stop(orch, runners, stub):
    scoring, _, _ = runners
    root_id = orch.start(FOLDER, target_phases=["scoring", "culling"], force_rerun=True)
    orch.stop()
    job = stub.jobs[root_id]
    assert job["status"] == "cancelled"
    assert job["runner_state"] == "cancelled"
    assert scoring.stop_calls == 1
