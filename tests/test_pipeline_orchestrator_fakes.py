"""
Tier A: PipelineOrchestrator with fake runners and enable_background_tick=False.
"""
import os
import shutil
import time
import uuid

import pytest

from modules import db
from modules.pipeline_orchestrator import PipelineOrchestrator
from tests.support.fake_runners import FakePhaseRunner

pytestmark = pytest.mark.firebird


@pytest.fixture(scope="module")
def orch_db(tmp_path_factory):
    template = os.path.abspath("template.fdb")
    if not os.path.exists(template):
        pytest.skip("template.fdb not found - Firebird tests unavailable")

    tmp = tmp_path_factory.mktemp("orch_fakes")
    db_path = str(tmp / f"orch_{uuid.uuid4().hex}.fdb")
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
def clean_jobs(orch_db):
    conn = db.get_db()
    c = conn.cursor()
    try:
        c.execute("DELETE FROM job_phases")
    except Exception:
        pass
    c.execute("DELETE FROM jobs")
    conn.commit()
    conn.close()


def _drain_orchestrator(orch: PipelineOrchestrator, max_ticks: int = 80):
    for _ in range(max_ticks):
        orch.on_tick()
        st = orch.get_status()
        if not st.get("active"):
            break
        time.sleep(0.02)


def test_orchestrator_single_indexing_phase_completes(orch_db):
    delay = 0.06
    indexing = FakePhaseRunner(delay_s=delay)
    metadata = FakePhaseRunner(delay_s=delay)
    scoring = FakePhaseRunner(delay_s=delay)
    tagging = FakePhaseRunner(delay_s=delay)
    selection = FakePhaseRunner(delay_s=delay)

    orch = PipelineOrchestrator(
        scoring_runner=scoring,
        tagging_runner=tagging,
        selection_runner=selection,
        indexing_runner=indexing,
        metadata_runner=metadata,
        enable_background_tick=False,
    )
    folder = "D:/orch_fake/single_idx"
    root_id = orch.start(folder, target_phases=["indexing"], force_rerun=True)
    assert root_id is not None
    assert orch.get_status()["active"] is True
    _drain_orchestrator(orch)
    assert orch.get_status()["active"] is False
    root = db.get_job_by_id(root_id)
    assert root["status"] == "completed"


def test_orchestrator_two_phases_sequence(orch_db):
    delay = 0.05

    def mk_runner():
        return FakePhaseRunner(delay_s=delay)

    indexing, metadata = mk_runner(), mk_runner()
    scoring, tagging, selection = mk_runner(), mk_runner(), mk_runner()
    orch = PipelineOrchestrator(
        scoring_runner=scoring,
        tagging_runner=tagging,
        selection_runner=selection,
        indexing_runner=indexing,
        metadata_runner=metadata,
        enable_background_tick=False,
    )
    folder = "D:/orch_fake/two"
    root_id = orch.start(folder, target_phases=["indexing", "metadata"], force_rerun=True)
    assert root_id is not None
    _drain_orchestrator(orch, max_ticks=120)
    assert orch.get_status()["active"] is False
    root = db.get_job_by_id(root_id)
    assert root["status"] == "completed"
    phases = db.get_job_phases(root_id) or []
    codes = [p.get("phase_code") for p in phases]
    assert "indexing" in codes and "metadata" in codes
    for p in phases:
        if p.get("phase_code") in ("indexing", "metadata"):
            assert p.get("state") == "completed"


def test_orchestrator_reopens_indexing_when_summary_done_but_indexing_pct_low(monkeypatch, orch_db):
    """INDEXING in phase plan when rollup says done but fulfillment stats show gaps (IPS)."""

    def fake_summary(path):
        return [
            {"code": "indexing", "status": "done"},
            {"code": "metadata", "status": "done"},
            {"code": "scoring", "status": "done"},
            {"code": "culling", "status": "done"},
            {"code": "keywords", "status": "done"},
        ]

    def fake_all_phases(enabled_only=True):
        return [
            {"code": "indexing", "optional": False, "default_skip": False},
            {"code": "metadata", "optional": False, "default_skip": False},
            {"code": "scoring", "optional": False, "default_skip": False},
            {"code": "culling", "optional": False, "default_skip": False},
            {"code": "keywords", "optional": True, "default_skip": False},
        ]

    stats = {
        "total": 100,
        "scored": 100,
        "thumbnails": 100,
        "keywords": 100,
        "indexing_done": 50,
        "score_pct": 100.0,
        "thumbnail_pct": 100.0,
        "indexing_pct": 50.0,
    }
    captured = {}

    monkeypatch.setattr(db, "get_folder_phase_summary", fake_summary)
    monkeypatch.setattr(db, "get_all_phases", fake_all_phases)
    monkeypatch.setattr(db, "get_folder_fulfillment_stats_for_path", lambda p: dict(stats))
    monkeypatch.setattr(db, "get_or_create_folder", lambda p: 1)
    monkeypatch.setattr(db, "create_job", lambda *a, **k: 4242)
    monkeypatch.setattr(
        db,
        "create_job_phases",
        lambda job_id, phase_plan: captured.setdefault("phase_plan", list(phase_plan)),
    )

    delay = 0.01

    def mk_runner():
        return FakePhaseRunner(delay_s=delay)

    orch = PipelineOrchestrator(
        scoring_runner=mk_runner(),
        tagging_runner=mk_runner(),
        selection_runner=mk_runner(),
        indexing_runner=mk_runner(),
        metadata_runner=mk_runner(),
        enable_background_tick=False,
    )
    monkeypatch.setattr(orch, "_start_next_phase", lambda self: None)

    jid = orch.start("D:/orch_fake/heal_indexing", force_rerun=False)
    assert jid == 4242
    plan = captured.get("phase_plan", [])
    assert plan, "create_job_phases should have been called"
    assert plan[0] == "indexing"
    assert "indexing" in plan
