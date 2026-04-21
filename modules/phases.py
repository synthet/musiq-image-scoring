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
from typing import Optional, List, Callable, Any, Tuple, Dict
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

# Allowed transitions: from_status -> set of to_statuses
ALLOWED_TRANSITIONS = {
    PhaseStatus.NOT_STARTED: {PhaseStatus.QUEUED, PhaseStatus.RUNNING},
    PhaseStatus.QUEUED:      {PhaseStatus.RUNNING, PhaseStatus.CANCEL_REQUESTED, PhaseStatus.SKIPPED},
    PhaseStatus.RUNNING:     {PhaseStatus.PAUSED, PhaseStatus.DONE, PhaseStatus.FAILED, PhaseStatus.SKIPPED, PhaseStatus.CANCEL_REQUESTED, PhaseStatus.RESTARTING},
    PhaseStatus.PAUSED:      {PhaseStatus.RUNNING, PhaseStatus.CANCEL_REQUESTED, PhaseStatus.RESTARTING},
    PhaseStatus.CANCEL_REQUESTED: {PhaseStatus.SKIPPED, PhaseStatus.FAILED, PhaseStatus.NOT_STARTED},
    PhaseStatus.RESTARTING:  {PhaseStatus.QUEUED, PhaseStatus.RUNNING, PhaseStatus.FAILED},
    PhaseStatus.DONE:        {PhaseStatus.RESTARTING, PhaseStatus.RUNNING},      # rerun
    PhaseStatus.FAILED:      {PhaseStatus.RESTARTING, PhaseStatus.RUNNING},      # retry
    PhaseStatus.SKIPPED:     {PhaseStatus.RESTARTING, PhaseStatus.RUNNING},      # explicit rerun
}


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
