"""
Tier A helpers: phase plan generation, job enqueue helpers, dispatcher pump loop.

The Cartesian product of (phase_plan x submit_mode x skip_existing x intervention)
is filtered to remove invalid combinations (e.g. culling-only without prior indexing).

Submit-matrix helpers support POST ``/api/runs/submit`` parametrized integration tests.
"""
from __future__ import annotations

import itertools
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from modules import db
from modules.db import job_type_for_phase_dispatch
from modules.job_dispatcher import JobDispatcher

# ---------------------------------------------------------------------------
# Phase plan generation
# ---------------------------------------------------------------------------

# Canonical pipeline order (matches ``modules.phases.PIPELINE_PHASE_ORDER``).
ALL_PHASES = ("indexing", "metadata", "scoring", "culling", "keywords", "bird_species")

# Phases that are valid standalone entry points (data already present in DB)
STANDALONE_OK = {"scoring", "keywords", "culling"}

# Minimum sane plans (prefix chains + selected mid-pipeline combos)
_SEED_PLANS: List[Tuple[str, ...]] = [
    ("indexing",),
    ("indexing", "metadata"),
    ("indexing", "metadata", "scoring"),
    ("indexing", "metadata", "scoring", "culling"),
    ("indexing", "metadata", "scoring", "culling", "keywords"),
    ("indexing", "metadata", "scoring", "culling", "keywords", "bird_species"),
    ("scoring",),
    ("keywords",),
    ("culling",),
    ("scoring", "culling"),
    ("scoring", "keywords"),
    ("scoring", "culling", "keywords"),
    ("scoring", "keywords", "bird_species"),
    ("keywords", "bird_species"),
    ("culling", "keywords"),
    ("indexing", "metadata", "scoring", "keywords"),
    ("indexing", "metadata", "keywords"),
    ("metadata", "scoring"),
]


def _is_valid_plan(plan: Tuple[str, ...]) -> bool:
    """Reject plans that violate ordering constraints."""
    if not plan:
        return False
    idx_map = {p: i for i, p in enumerate(ALL_PHASES)}
    positions = [idx_map.get(p) for p in plan]
    if any(pos is None for pos in positions):
        return False
    # Must be strictly increasing (respects pipeline order)
    return all(a < b for a, b in zip(positions, positions[1:]))


def iter_valid_phase_plans(
    max_plans: int = 0,
) -> List[Tuple[str, ...]]:
    """Return de-duplicated, order-valid phase plans.

    If ``max_plans`` > 0, truncate to that many plans (stable order).
    Expand via env ``PIPELINE_MATRIX_MAX_PLANS``.
    """
    env_max = os.environ.get("PIPELINE_MATRIX_MAX_PLANS")
    if env_max:
        max_plans = int(env_max)

    plans = list(dict.fromkeys(p for p in _SEED_PLANS if _is_valid_plan(p)))

    # Optionally expand with all valid subsets (combinatorial, for thorough mode)
    if max_plans == 0 or max_plans > len(plans):
        for r in range(1, len(ALL_PHASES) + 1):
            for combo in itertools.combinations(ALL_PHASES, r):
                if _is_valid_plan(combo) and combo not in plans:
                    plans.append(combo)

    if max_plans > 0:
        plans = plans[:max_plans]
    return plans


# ---------------------------------------------------------------------------
# Submit modes
# ---------------------------------------------------------------------------

SUBMIT_MODES = ("monolithic", "sequential")
SKIP_EXISTING_OPTIONS = (True, False)

# Interventions the test matrix exercises
INTERVENTIONS = (
    "none",
    "cancel_queued",
    "fail_then_restart",
    "resume_after_interrupt",
)


# ---------------------------------------------------------------------------
# Job enqueue helpers
# ---------------------------------------------------------------------------

def enqueue_monolithic(
    input_path: str,
    phase_plan: Tuple[str, ...],
    skip_existing: bool = True,
    extra_payload: Optional[Dict[str, Any]] = None,
) -> int:
    """Enqueue a single job with multiple job_phases rows (one job, full plan)."""
    first_phase = phase_plan[0]
    jt = job_type_for_phase_dispatch(first_phase)
    payload = {"input_path": input_path, "skip_existing": skip_existing}
    if extra_payload:
        payload.update(extra_payload)

    job_id, _pos = db.enqueue_job(
        input_path,
        phase_code=first_phase,
        job_type=jt,
        queue_payload=payload,
    )
    if phase_plan:
        db.create_job_phases(job_id, list(phase_plan), first_phase_state="queued")
    return job_id


def enqueue_sequential(
    input_path: str,
    phase_plan: Tuple[str, ...],
    skip_existing: bool = True,
    extra_payload: Optional[Dict[str, Any]] = None,
) -> List[int]:
    """Enqueue N independent jobs, one per phase (sequential execution via queue order)."""
    job_ids = []
    for phase_code in phase_plan:
        jt = job_type_for_phase_dispatch(phase_code)
        payload = {"input_path": input_path, "skip_existing": skip_existing}
        if extra_payload:
            payload.update(extra_payload)
        jid, _ = db.enqueue_job(
            input_path,
            phase_code=phase_code,
            job_type=jt,
            queue_payload=payload,
        )
        job_ids.append(jid)
    return job_ids


# ---------------------------------------------------------------------------
# Dispatcher pump loop
# ---------------------------------------------------------------------------

def _any_jobs_status_running() -> bool:
    """True if any ``jobs`` row is still ``running`` (multi-phase handoff gap).

    ``get_running_job_for_phase_continuation()`` requires a *phase* in ``running``;
    briefly, ``jobs.status`` can still be ``running`` with no matching phase row
    while the dispatcher advances — do not treat the pump as quiet in that window.
    """
    from modules.db import get_connector

    row = get_connector().query_one(
        "SELECT 1 AS ok FROM jobs WHERE LOWER(TRIM(COALESCE(status, ''))) = 'running' "
        "FETCH FIRST 1 ROWS ONLY"
    )
    return row is not None


def run_dispatcher_until_quiet(
    dispatcher: JobDispatcher,
    deadline_s: float = 8.0,
    tick_sleep_s: float = 0.02,
) -> None:
    """Tick the dispatcher until no queued/running jobs remain or deadline expires.

    Also waits for all fake runner background threads to finish, preventing
    deadlocks when the next test truncates tables.
    """
    end = time.time() + deadline_s
    while time.time() < end:
        dispatcher.tick_for_tests()

        queued = db.get_queued_jobs(limit=1)
        running = db.get_running_job_for_phase_continuation()
        any_runner_busy = dispatcher._any_runner_busy()

        if (
            not queued
            and not running
            and not any_runner_busy
            and not _any_jobs_status_running()
        ):
            # One more tick to let any just-completed phase continuation fire
            dispatcher.tick_for_tests()
            time.sleep(tick_sleep_s)
            dispatcher.tick_for_tests()
            # Re-check
            queued = db.get_queued_jobs(limit=1)
            running = db.get_running_job_for_phase_continuation()
            if (
                not queued
                and not running
                and not dispatcher._any_runner_busy()
                and not _any_jobs_status_running()
            ):
                break

        time.sleep(tick_sleep_s)

    # Wait for all runner background threads to finish (prevents deadlocks
    # when the next test's clean_postgres truncates tables)
    _drain_runner_threads(dispatcher)


def _drain_runner_threads(dispatcher: JobDispatcher, timeout: float = 5.0) -> None:
    """Join all runner background threads to ensure DB writes are complete."""
    runners = [
        dispatcher.indexing_runner,
        dispatcher.metadata_runner,
        dispatcher.scoring_runner,
        dispatcher.tagging_runner,
        dispatcher.clustering_runner,
        dispatcher.selection_runner,
        dispatcher.bird_species_runner,
    ]
    for runner in runners:
        if runner is None:
            continue
        thread = getattr(runner, "_thread", None)
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)


def wait_for_job_status(
    job_id: int,
    target_status: str,
    deadline_s: float = 5.0,
    poll_s: float = 0.02,
) -> Dict[str, Any]:
    """Poll until job reaches target status or deadline."""
    end = time.time() + deadline_s
    while time.time() < end:
        row = db.get_job(job_id)
        if row and (row.get("status") or "").lower() == target_status.lower():
            return row
        time.sleep(poll_s)
    return db.get_job(job_id) or {}


# ---------------------------------------------------------------------------
# Matrix generation
# ---------------------------------------------------------------------------

def build_matrix(
    max_plans: int = 0,
    include_interventions: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Build the filtered Cartesian product of test scenarios.

    Returns list of dicts with keys:
        phase_plan, submit_mode, skip_existing, intervention, test_id
    """
    plans = iter_valid_phase_plans(max_plans=max_plans)
    interventions = include_interventions or list(INTERVENTIONS)

    cases = []
    for plan, mode, skip, intervention in itertools.product(
        plans, SUBMIT_MODES, SKIP_EXISTING_OPTIONS, interventions,
    ):
        # Filter invalid combos
        if _should_skip(plan, mode, intervention):
            continue
        test_id = f"{'+'.join(plan)}|{mode}|skip={skip}|{intervention}"
        cases.append({
            "phase_plan": plan,
            "submit_mode": mode,
            "skip_existing": skip,
            "intervention": intervention,
            "test_id": test_id,
        })
    return cases


def _should_skip(plan: Tuple[str, ...], mode: str, intervention: str) -> bool:
    """Drop scenarios that are invalid or redundant."""
    # cancel_queued needs at least 2 jobs (sequential) or 2 phases (monolithic)
    if intervention == "cancel_queued":
        if mode == "sequential" and len(plan) < 2:
            return True
        if mode == "monolithic" and len(plan) < 2:
            return True

    # fail_then_restart needs at least 1 phase to fail
    # (always valid, but skip for single-phase sequential to avoid duplication)

    # resume_after_interrupt on monolithic single-phase is a no-op
    if intervention == "resume_after_interrupt" and len(plan) < 2:
        return True

    return False


# ---------------------------------------------------------------------------
# POST /api/runs/submit matrix (SPA-shaped)
# ---------------------------------------------------------------------------

CANONICAL_PIPELINE_PHASES: Tuple[str, ...] = ALL_PHASES

RUN_API_MODES = ("process_new", "process_all", "fix_incomplete", "validation_repair")


def _submit_run_legacy_flags(run_api_mode: str) -> Dict[str, bool]:
    if run_api_mode == "process_new":
        return {
            "skip_done": True,
            "force_rerun": False,
            "fix_incomplete_stages": False,
            "validation_repair_mode": False,
        }
    if run_api_mode == "process_all":
        return {
            "skip_done": False,
            "force_rerun": True,
            "fix_incomplete_stages": False,
            "validation_repair_mode": False,
        }
    if run_api_mode == "fix_incomplete":
        return {
            "skip_done": True,
            "force_rerun": False,
            "fix_incomplete_stages": True,
            "validation_repair_mode": False,
        }
    if run_api_mode == "validation_repair":
        return {
            "skip_done": True,
            "force_rerun": False,
            "fix_incomplete_stages": False,
            "validation_repair_mode": True,
        }
    raise ValueError(f"unknown run_api_mode: {run_api_mode!r}")


def submit_run_via_api(client, scope_paths, stages, run_api_mode: str = "process_new", scope_type: str = "folder_recursive"):
    """POST ``/api/runs/submit`` (``RunSubmitRequest`` — canonical ``run_mode`` only)."""
    _ = run_api_mode  # matrix axis retained for scenario ids / seed expectations
    body = {
        "scope_type": scope_type,
        "scope_paths": list(scope_paths),
        "stages": list(stages),
        "run_mode": "process_stale_or_missing",
        "generate_captions": False,
    }
    return client.post("/api/runs/submit", json=body)


def seed_partial_phase_state(scope_folder_abs: str, completed_phase_codes: Tuple[str, ...]) -> int:
    """Create folder + one dummy image; mark ``completed_phase_codes`` done. Returns ``image_id``."""
    root = os.path.normpath(scope_folder_abs)
    Path(root).mkdir(parents=True, exist_ok=True)
    fid = db.get_or_create_folder(root)
    file_path = os.path.join(root, "_matrix_seed.jpg")
    Path(file_path).touch()
    result = {
        "image_path": file_path,
        "image_name": "_matrix_seed.jpg",
        "folder_id": fid,
        "score_general": 0.5,
        "score_technical": 0.5,
        "score_aesthetic": 0.5,
        "summary": {
            "weighted_scores": {"general": 0.5, "technical": 0.5, "aesthetic": 0.5},
        },
        "models": {},
    }
    db.upsert_image(job_id=None, result=result)
    row = db.get_connector().query_one("SELECT id FROM images WHERE file_path = ?", (file_path,))
    assert row is not None
    image_id = int(row["id"])
    for code in completed_phase_codes:
        db.set_image_phase_status(image_id, code, "done", executor_version="test-1.0.0")
    # `_heal_stale_phase_flags` resets inconsistent done rows during runs; keep seeded rows coherent.
    if "indexing" in completed_phase_codes:
        import numpy as np

        emb = np.zeros(1280, dtype=np.float32)
        db.update_image_embedding(image_id, emb.tobytes())
    if "metadata" in completed_phase_codes:
        db.get_connector().execute(
            "UPDATE images SET rating = ?, label = ? WHERE id = ?",
            (3, "matrix_seed", image_id),
        )
    if "keywords" in completed_phase_codes:
        db.get_connector().execute(
            "UPDATE images SET keywords = ? WHERE id = ?",
            ("matrix_seed_kw", image_id),
        )
    return image_id


def _valid_prefix_plans() -> List[Tuple[str, ...]]:
    p = CANONICAL_PIPELINE_PHASES
    return [tuple(p[:k]) for k in range(1, len(p) + 1)]


_INVALID_SCRATCH_PLANS: Tuple[Tuple[str, ...], ...] = (
    ("keywords",),
    ("bird_species",),
    ("culling",),
    ("metadata",),
    ("scoring",),
    ("indexing", "keywords"),
    ("indexing", "metadata", "keywords"),
)


def build_submit_matrix(max_cases: int = 120) -> List[Dict[str, Any]]:
    """Scenarios for POST ``/api/runs/submit`` × run mode × seed state."""
    cases: List[Dict[str, Any]] = []
    for plan in _valid_prefix_plans():
        for rm in RUN_API_MODES:
            cases.append({
                "phase_plan": plan,
                "run_api_mode": rm,
                "seed_state": "from_scratch",
                "completed_prefix": (),
                "expect_status": 200,
                "test_id": f"submit|{'+'.join(plan)}|{rm}|scratch|200",
            })

    for plan in _INVALID_SCRATCH_PLANS:
        for rm in RUN_API_MODES:
            cases.append({
                "phase_plan": plan,
                "run_api_mode": rm,
                "seed_state": "from_scratch",
                "completed_prefix": (),
                "expect_status": 400,
                "test_id": f"submit|{'+'.join(plan)}|{rm}|scratch|400",
            })

    partial_specs = [
        {
            "completed_prefix": ("indexing", "metadata", "scoring"),
            "phase_plan": ("keywords",),
            "expect_status": 200,
        },
        {
            "completed_prefix": ("indexing", "metadata", "scoring"),
            "phase_plan": ("bird_species",),
            "expect_status": 400,
        },
        {
            "completed_prefix": ("indexing", "metadata", "scoring", "keywords"),
            "phase_plan": ("bird_species",),
            "expect_status": 200,
        },
    ]
    for spec in partial_specs:
        plan = spec["phase_plan"]
        for rm in RUN_API_MODES:
            cases.append({
                "phase_plan": plan,
                "run_api_mode": rm,
                "seed_state": "partial_prefix",
                "completed_prefix": spec["completed_prefix"],
                "expect_status": spec["expect_status"],
                "test_id": f"submit|{'+'.join(plan)}|{rm}|partial|{spec['expect_status']}",
            })

    env_max = os.environ.get("PIPELINE_SUBMIT_MATRIX_MAX_CASES")
    cap = int(env_max) if env_max else max_cases
    if cap > 0:
        cases = cases[:cap]
    return cases
