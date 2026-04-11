"""
Tier A helpers: phase plan generation, job enqueue helpers, dispatcher pump loop.

The Cartesian product of (phase_plan x submit_mode x skip_existing x intervention)
is filtered to remove invalid combinations (e.g. culling-only without prior indexing).
"""
from __future__ import annotations

import itertools
import json
import time
from typing import Any, Dict, List, Optional, Tuple

from modules import db
from modules.db import job_type_for_phase_dispatch
from modules.job_dispatcher import JobDispatcher

# ---------------------------------------------------------------------------
# Phase plan generation
# ---------------------------------------------------------------------------

# Canonical phase order (pipeline_phases.sort_order in the DB)
ALL_PHASES = ("indexing", "metadata", "scoring", "keywords", "culling")

# Phases that are valid standalone entry points (data already present in DB)
STANDALONE_OK = {"scoring", "keywords", "culling"}

# Minimum sane plans (prefix chains + selected mid-pipeline combos)
_SEED_PLANS: List[Tuple[str, ...]] = [
    ("indexing",),
    ("indexing", "metadata"),
    ("indexing", "metadata", "scoring"),
    ("indexing", "metadata", "scoring", "keywords"),
    ("indexing", "metadata", "scoring", "keywords", "culling"),
    # Partial mid-pipeline (assume data exists)
    ("scoring",),
    ("keywords",),
    ("culling",),
    ("scoring", "keywords"),
    ("scoring", "keywords", "culling"),
    ("scoring", "culling"),
    ("keywords", "culling"),
    ("indexing", "metadata", "scoring", "culling"),
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
    import os

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

        if not queued and not running and not any_runner_busy:
            # One more tick to let any just-completed phase continuation fire
            dispatcher.tick_for_tests()
            time.sleep(tick_sleep_s)
            dispatcher.tick_for_tests()
            # Re-check
            queued = db.get_queued_jobs(limit=1)
            running = db.get_running_job_for_phase_continuation()
            if not queued and not running and not dispatcher._any_runner_busy():
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
