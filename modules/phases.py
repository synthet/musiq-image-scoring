"""
Pipeline Phase Architecture — Configurable, data-driven processing phases.

Phases are registered in the DB (PIPELINE_PHASES table) and bound to
executors at runtime via PhaseRegistry.  A phase that exists in the DB
but has no registered executor will appear in the UI but cannot be triggered.

Status values (for IMAGE_PHASE_STATUS):
    not_started | running | done | skipped | failed

Folder-level summaries are computed live (no stored table).
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Callable, Any, Tuple, Dict, Iterable
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Phase code enum — canonical identifiers
# ---------------------------------------------------------------------------

class PhaseCode(str, Enum):
    """
    Canonical phase codes.  Must match pipeline_phases.code in the DB.

    Using ``str`` mixin so values serialise cleanly to JSON / SQL.
    """
    INDEXING  = "indexing"
    METADATA  = "metadata"
    SCORING   = "scoring"
    CULLING   = "culling"
    KEYWORDS  = "keywords"
    BIRD_SPECIES = "bird_species"


# Same execution order as PipelineOrchestrator.PHASE_ORDER — UI and job_phases must follow this.
PIPELINE_PHASE_ORDER: Tuple[PhaseCode, ...] = (
    PhaseCode.INDEXING,
    PhaseCode.METADATA,
    PhaseCode.SCORING,
    PhaseCode.CULLING,
    PhaseCode.KEYWORDS,
    PhaseCode.BIRD_SPECIES,
)

_PHASE_ORDER_INDEX = {p: i for i, p in enumerate(PIPELINE_PHASE_ORDER)}

# Direct prerequisites per pipeline stage (must stay aligned with ``phase_executors.register_all``).
PHASE_PREREQUISITES: Dict[str, Tuple[str, ...]] = {
    PhaseCode.INDEXING.value: (),
    PhaseCode.METADATA.value: (PhaseCode.INDEXING.value,),
    PhaseCode.SCORING.value: (PhaseCode.METADATA.value,),
    PhaseCode.CULLING.value: (PhaseCode.SCORING.value,),
    PhaseCode.KEYWORDS.value: (PhaseCode.SCORING.value,),
    PhaseCode.BIRD_SPECIES.value: (PhaseCode.KEYWORDS.value,),
}

SCORING_EXECUTOR_VERSION = "5.0.0"


def missing_prerequisites(
    requested: Iterable[str],
    satisfied: Iterable[str],
) -> Dict[str, List[str]]:
    """Return phases whose direct prerequisites are not met.

    A prerequisite *pre* for requested phase *P* is satisfied when *pre* is in
    ``satisfied`` (e.g. scope preview marks stage ``done``) or when *pre* is
    also listed in ``requested`` (same-run inclusion).
    """
    requested_norm: List[str] = []
    seen_req: set[str] = set()
    for raw in requested:
        c = (str(raw or "")).strip().lower()
        if not c or c in seen_req:
            continue
        seen_req.add(c)
        requested_norm.append(c)

    requested_set = set(requested_norm)
    satisfied_set = {(str(s or "")).strip().lower() for s in satisfied}

    missing_map: Dict[str, List[str]] = {}
    for phase in requested_norm:
        prereqs = PHASE_PREREQUISITES.get(phase)
        if prereqs is None:
            continue
        missing_list = [
            pre for pre in prereqs
            if pre not in satisfied_set and pre not in requested_set
        ]
        if missing_list:
            missing_map[phase] = missing_list
    return missing_map


def compute_satisfied_phases_for_scope(scope_paths: Iterable[str]) -> set[str]:
    """Aggregate per-stage status across folders and return phases counted as satisfied.

    A phase is satisfied for the scope when, summed across all folders:
      - total_count == 0 (no images to gate on), OR
      - done + skipped == total AND failed == 0

    Mirrors the semantics of ``api._compute_scope_preview_for_resolved_paths``
    so submit-time gating and heal-time gating cannot disagree.
    """
    from modules import db  # lazy: db imports phases

    stage_total: Dict[str, int] = {}
    stage_done_or_skipped: Dict[str, int] = {}
    stage_failed: Dict[str, int] = {}

    for raw_path in scope_paths or []:
        path = (str(raw_path or "")).strip()
        if not path:
            continue
        try:
            summary = db.get_folder_phase_summary(path, force_refresh=False)
        except Exception:
            logger.exception("compute_satisfied_phases_for_scope: summary failed for %s", path)
            continue
        for row in summary or []:
            code = (row.get("code") or "").strip()
            if not code:
                continue
            stage_total[code] = stage_total.get(code, 0) + int(row.get("total_count") or 0)
            stage_done_or_skipped[code] = (
                stage_done_or_skipped.get(code, 0)
                + int(row.get("done_count") or 0)
                + int(row.get("skipped_count") or 0)
            )
            stage_failed[code] = stage_failed.get(code, 0) + int(row.get("failed_count") or 0)

    satisfied: set[str] = set()
    for code, total in stage_total.items():
        if total <= 0:
            satisfied.add(code)
            continue
        if stage_done_or_skipped.get(code, 0) >= total and stage_failed.get(code, 0) == 0:
            satisfied.add(code)
    return satisfied


def assert_prereqs_for_scope(
    phase_values: Iterable[str],
    scope_paths: Iterable[str],
) -> Dict[str, List[str]]:
    """Return the {phase: [missing_prereqs]} map for the given scope.

    Empty dict means all requested phases have their prereqs satisfied (or
    co-requested in the same submission). Callers decide policy: ``submit_run``
    raises 400 on a non-empty result; heal records a per-folder skip and
    continues.
    """
    satisfied = compute_satisfied_phases_for_scope(scope_paths)
    return missing_prerequisites(phase_values or [], satisfied)


def sort_phase_codes_canonical(phases: List[PhaseCode]) -> List[PhaseCode]:
    """Order phase codes in pipeline sequence (not insertion order)."""
    return sorted(phases, key=lambda ph: _PHASE_ORDER_INDEX.get(ph, 999))


def phase_string_sort_key(code: str) -> int:
    """Sort key for persisted phase_code strings; bird_species runs after keywords."""
    c = (code or "").strip()
    if c == "bird_species":
        return len(PIPELINE_PHASE_ORDER)
    try:
        return _PHASE_ORDER_INDEX[PhaseCode(c)]
    except ValueError:
        return 999


def sort_phase_value_strings(codes: List[str]) -> List[str]:
    """Sort phase_code strings in canonical pipeline order (bird_species after keywords)."""
    if not codes:
        return []
    return sorted(codes, key=lambda s: phase_string_sort_key(s))


def pipeline_prefix_through(phase: str) -> List[str]:
    """Return the canonical contiguous prefix of required phases up to and
    including ``phase`` (transitive closure over :data:`PHASE_PREREQUISITES`).

    ``keywords`` and ``culling`` are siblings under ``scoring``, so this walks
    the dependency DAG rather than slicing a linear order::

        pipeline_prefix_through("keywords") -> ["indexing", "metadata", "scoring", "keywords"]
        pipeline_prefix_through("culling")  -> ["indexing", "metadata", "scoring", "culling"]

    Used by the legacy single-phase ``/start`` endpoints so a downstream phase
    can never be enqueued ahead of its prerequisites. An unknown phase returns
    ``[phase]`` unchanged.
    """
    target = (str(phase or "")).strip().lower()
    if not target:
        return []
    collected: set[str] = set()
    stack = [target]
    while stack:
        cur = stack.pop()
        if cur in collected:
            continue
        collected.add(cur)
        for pre in PHASE_PREREQUISITES.get(cur, ()):
            if pre not in collected:
                stack.append(pre)
    return sort_phase_value_strings(list(collected))


def sort_job_phase_rows_for_display(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort job_phases rows for API/UI; renumbers phase_order to match display order."""
    if not rows:
        return []
    sorted_rows = sorted(rows, key=lambda r: phase_string_sort_key(str(r.get("phase_code") or "")))
    out: List[Dict[str, Any]] = []
    for i, r in enumerate(sorted_rows):
        d = dict(r)
        d["phase_order"] = i
        out.append(d)
    return out


PHASE_CODE_ALIASES = {
    "score": PhaseCode.SCORING.value,
    "tag": PhaseCode.KEYWORDS.value,
    "cluster": PhaseCode.CULLING.value,
}


def normalize_phase_codes(phase_codes: Optional[List[Any]]) -> List[PhaseCode]:
    """Normalize API/job payload phase codes into canonical PhaseCode values."""
    normalized: List[PhaseCode] = []
    for phase in phase_codes or []:
        if isinstance(phase, PhaseCode):
            candidate = phase
        else:
            raw = str(phase or "").strip()
            if not raw:
                continue
            if raw.startswith("PhaseCode."):
                raw = raw.split(".", 1)[1]
            raw = PHASE_CODE_ALIASES.get(raw.lower(), raw.lower())
            # Separate job type (API / job_phases), not a PhaseCode enum value.
            if raw == "bird_species":
                continue
            try:
                candidate = PhaseCode(raw)
            except ValueError:
                logger.warning("Ignoring unknown phase code: %s", phase)
                continue
        if candidate not in normalized:
            normalized.append(candidate)
    return sort_phase_codes_canonical(normalized)


# ---------------------------------------------------------------------------
# Phase status enum
# ---------------------------------------------------------------------------

class PhaseStatus(str, Enum):
    NOT_STARTED = "not_started"
    QUEUED      = "queued"
    RUNNING     = "running"
    PAUSED      = "paused"
    CANCEL_REQUESTED = "cancel_requested"
    RESTARTING  = "restarting"
    DONE        = "done"
    SKIPPED     = "skipped"
    FAILED      = "failed"

# Allowed transitions for ``set_image_phase_status`` updates: from_status -> set of to_statuses.
# Anything not in this map is treated as suspicious and logged at WARNING (or, when
# ``database.strict_phase_transitions`` is true, raised as a ValueError). The map is the
# state-machine contract; expand it consciously when adding a new code path.
#
# Notes on the explicit edges below:
#   - "X -> X" (idempotent): callers occasionally re-emit the same status and we do not
#     want to flag those as transition violations.
#   - "NOT_STARTED -> DONE/SKIPPED/FAILED": legitimate one-shot writes from backfill /
#     ad-hoc maintenance paths that never go through RUNNING.
#   - "RUNNING/DONE/FAILED/SKIPPED -> NOT_STARTED": heal reset paths (see
#     ``reset_image_phase_status``); kept here so direct callers also stay legal.
ALLOWED_TRANSITIONS = {
    PhaseStatus.NOT_STARTED: {
        PhaseStatus.NOT_STARTED, PhaseStatus.QUEUED, PhaseStatus.RUNNING,
        PhaseStatus.DONE, PhaseStatus.SKIPPED, PhaseStatus.FAILED,  # one-shot writes
    },
    PhaseStatus.QUEUED: {
        PhaseStatus.QUEUED, PhaseStatus.RUNNING, PhaseStatus.NOT_STARTED,
        PhaseStatus.CANCEL_REQUESTED, PhaseStatus.SKIPPED,
    },
    PhaseStatus.RUNNING: {
        PhaseStatus.RUNNING, PhaseStatus.PAUSED, PhaseStatus.DONE, PhaseStatus.FAILED,
        PhaseStatus.SKIPPED, PhaseStatus.CANCEL_REQUESTED, PhaseStatus.RESTARTING,
        PhaseStatus.NOT_STARTED,  # heal reset of in-flight ghost rows
    },
    PhaseStatus.PAUSED: {
        PhaseStatus.PAUSED, PhaseStatus.RUNNING, PhaseStatus.CANCEL_REQUESTED,
        PhaseStatus.RESTARTING, PhaseStatus.NOT_STARTED,
    },
    PhaseStatus.CANCEL_REQUESTED: {
        PhaseStatus.CANCEL_REQUESTED, PhaseStatus.SKIPPED, PhaseStatus.FAILED,
        PhaseStatus.NOT_STARTED,
    },
    PhaseStatus.RESTARTING: {
        PhaseStatus.RESTARTING, PhaseStatus.QUEUED, PhaseStatus.RUNNING,
        PhaseStatus.FAILED, PhaseStatus.NOT_STARTED,
    },
    PhaseStatus.DONE: {
        PhaseStatus.DONE, PhaseStatus.RESTARTING, PhaseStatus.RUNNING,
        PhaseStatus.NOT_STARTED,  # heal reset
    },
    PhaseStatus.FAILED: {
        PhaseStatus.FAILED, PhaseStatus.RESTARTING, PhaseStatus.RUNNING,
        PhaseStatus.NOT_STARTED,
    },
    PhaseStatus.SKIPPED: {
        PhaseStatus.SKIPPED, PhaseStatus.RESTARTING, PhaseStatus.RUNNING,
        PhaseStatus.NOT_STARTED,
    },
}


def is_transition_allowed(from_status, to_status) -> bool:
    """Membership check against ``ALLOWED_TRANSITIONS``; tolerant to str inputs."""
    def _coerce(s):
        if isinstance(s, PhaseStatus):
            return s
        try:
            return PhaseStatus(str(s).strip().lower())
        except (ValueError, AttributeError):
            return None

    a = _coerce(from_status)
    b = _coerce(to_status)
    if a is None or b is None:
        return True  # unknown status — let caller proceed; not our place to gate
    return b in ALLOWED_TRANSITIONS.get(a, set())


# ---------------------------------------------------------------------------
# Folder-level summary status
# ---------------------------------------------------------------------------

class FolderPhaseStatus(str, Enum):
    NOT_STARTED = "not_started"
    PARTIAL     = "partial"
    DONE        = "done"
    FAILED      = "failed"


# ---------------------------------------------------------------------------
# Phase executor — binds a code to its run logic
# ---------------------------------------------------------------------------

@dataclass
class PhaseExecutor:
    """
    Binds a phase code to its actual execution logic.

    Attributes:
        code:             Phase code (must match PIPELINE_PHASES.code).
        executor_version: Version of the algo/model.  Bumped when the model
                          or algorithm changes — independent of APP_VERSION.
        run_folder:       ``fn(folder_path, job_id) -> None``
        run_image:        ``fn(image_path, job_id) -> None``  (optional)
        depends_on:       List of phase codes that must be ``done`` before
                          this phase can run.  (Enforcement deferred to v2.)
    """
    code:             str
    executor_version: str
    run_folder:       Optional[Callable[..., Any]] = None
    run_image:        Optional[Callable[..., Any]] = None
    depends_on:       List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Phase registry — runtime lookup
# ---------------------------------------------------------------------------

class PhaseRegistry:
    """
    Runtime registry mapping ``phase_code -> PhaseExecutor``.

    Executors are registered at app startup; the Folder Tree UI queries this
    to decide which buttons are active.
    """
    _executors: dict[str, PhaseExecutor] = {}

    @classmethod
    def register(cls, executor: PhaseExecutor):
        logger.info("PhaseRegistry: registered executor for '%s' (v%s)",
                     executor.code, executor.executor_version)
        cls._executors[executor.code] = executor

    @classmethod
    def get(cls, code: str) -> Optional[PhaseExecutor]:
        return cls._executors.get(code)

    @classmethod
    def get_all(cls) -> list[PhaseExecutor]:
        return list(cls._executors.values())

    @classmethod
    def is_registered(cls, code: str) -> bool:
        return code in cls._executors


# ---------------------------------------------------------------------------
# Seed data — inserted into PIPELINE_PHASES on first startup
# ---------------------------------------------------------------------------

SEED_PHASES = [
    {
        "code": PhaseCode.INDEXING,
        "name": "Indexing",
        "description": "Scan folder, create/update DB records, compute file hash and register image paths.",
        "sort_order": 1,
        "enabled": 1,
        "optional": 0,
        "default_skip": False,
    },
    {
        "code": PhaseCode.METADATA,
        "name": "Physical Metadata",
        "description": "Extract EXIF/XMP tags, generate thumbnails, and prepare files for scoring.",
        "sort_order": 2,
        "enabled": 1,
        "optional": 0,
        "default_skip": False,
    },
    {
        "code": PhaseCode.SCORING,
        "name": "Scoring",
        "description": "AI quality scoring (MUSIQ, SPAQ, AVA, LIQE, etc.)",
        "sort_order": 30,
        "optional": False,
        "default_skip": False,
    },
    {
        "code": PhaseCode.CULLING,
        "name": "Culling & Stacks",
        "description": "Clustering into stacks, cull/pick decisions",
        "sort_order": 40,
        "optional": True,
        "default_skip": False,
    },
    {
        "code": PhaseCode.KEYWORDS,
        "name": "Keywords",
        "description": "CLIP keyword tagging + BLIP captioning",
        "sort_order": 50,
        "optional": True,
        "default_skip": False,
    },
    {
        "code": PhaseCode.BIRD_SPECIES,
        "name": "Bird Species",
        "description": "Identify and classify bird species in images",
        "sort_order": 60,
        "optional": True,
        "default_skip": False,
    },
]
