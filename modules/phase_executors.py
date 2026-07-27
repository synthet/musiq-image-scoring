"""
Phase Executor Registration — wires PhaseCode to actual runner logic.

Called once at app startup (after db.init_db, before UI build).
Each executor binds:
  - code:             PhaseCode enum value
  - executor_version: bumped when the underlying algorithm/model changes
  - run_folder:       fn(folder_path, job_id) -> None
  - depends_on:       list of phase codes that must be 'done' first
"""
import logging

from modules.phases import PhaseCode, PhaseExecutor, PhaseRegistry

logger = logging.getLogger(__name__)


def register_all(
    scoring_runner=None,
    tagging_runner=None,
    clustering_runner=None,
    selection_runner=None,
    bird_species_runner=None,
    indexing_runner=None,
    metadata_runner=None,
):
    """
    Register all known phase executors.

    Runners are optional — if a runner is None, that phase will appear in the
    UI (from the DB) but its button will be disabled (no executor registered).
    """

    # Phase A — Indexing
    if indexing_runner:
        PhaseRegistry.register(PhaseExecutor(
            code=PhaseCode.INDEXING,
            executor_version="1.0.0",
            run_folder=indexing_runner.start_batch,
            depends_on=[],
        ))
    else:
        PhaseRegistry.register(PhaseExecutor(
            code=PhaseCode.INDEXING,
            executor_version="1.0.0",
            run_folder=None,
            depends_on=[],
        ))

    # Phase B — Metadata Prep
    if metadata_runner:
        PhaseRegistry.register(PhaseExecutor(
            code=PhaseCode.METADATA,
            executor_version="1.0.0",
            run_folder=metadata_runner.start_batch,
            depends_on=[PhaseCode.INDEXING],
        ))
    else:
        PhaseRegistry.register(PhaseExecutor(
            code=PhaseCode.METADATA,
            executor_version="1.0.0",
            run_folder=None,
            depends_on=[PhaseCode.INDEXING],
        ))

    # Phase C — Scoring
    if scoring_runner:
        PhaseRegistry.register(PhaseExecutor(
            code=PhaseCode.SCORING,
            executor_version=_get_scorer_version(scoring_runner),
            run_folder=scoring_runner.start_batch,
            depends_on=[PhaseCode.METADATA],
        ))

    # Phase D — Culling & Stacks (clustering OR selection)
    if selection_runner:
        PhaseRegistry.register(PhaseExecutor(
            code=PhaseCode.CULLING,
            executor_version="1.0.0",
            run_folder=selection_runner.start_batch,
            depends_on=[PhaseCode.SCORING],
        ))
    elif clustering_runner:
        PhaseRegistry.register(PhaseExecutor(
            code=PhaseCode.CULLING,
            executor_version="1.0.0",
            run_folder=clustering_runner.start_batch,
            depends_on=[PhaseCode.SCORING],
        ))

    # Phase E — Keywords
    if tagging_runner:
        PhaseRegistry.register(PhaseExecutor(
            code=PhaseCode.KEYWORDS,
            executor_version="1.0.0",
            run_folder=tagging_runner.start_batch,
            depends_on=[PhaseCode.SCORING],
        ))

    # Phase F — Bird Species
    if bird_species_runner:
        from modules.bird_species import BIRD_SPECIES_RUNNER_VERSION

        PhaseRegistry.register(PhaseExecutor(
            code=PhaseCode.BIRD_SPECIES,
            executor_version=BIRD_SPECIES_RUNNER_VERSION,
            run_folder=bird_species_runner.start_batch,
            depends_on=[PhaseCode.KEYWORDS],
        ))

    registered = [e.code for e in PhaseRegistry.get_all()]
    logger.info("Phase executors registered: %s", registered)


def _get_scorer_version(scoring_runner) -> str:
    """Phase-registry scoring version (must match IPS writes in pipeline runners).

    Do not use per-model ``shared_scorer.VERSION`` (e.g. topiq-nr-1) here — that tag
    describes the active backend, not the pipeline scoring phase generation stored in
    ``image_phase_status.executor_version``.
    """
    _ = scoring_runner
    from modules.phases import SCORING_EXECUTOR_VERSION

    return SCORING_EXECUTOR_VERSION
