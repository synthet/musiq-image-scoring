/**
 * Run-level Retry (POST /api/runs/{id}/retry) enqueues a new `jobs` row and the SPA
 * navigates to that id. Stage-level retry uses a different endpoint and keeps the same id.
 */
const RUN_LEVEL_RETRY_TOOLTIP_BASE =
  'Creates a new run (new #) from this job and opens it. The original run stays in history. Loading a run URL does not enqueue work—only actions like Retry or Submit do.'

/** Tooltip on run cards and compact lists (no stage panel). */
export const RUN_LEVEL_RETRY_TOOLTIP = RUN_LEVEL_RETRY_TOOLTIP_BASE

/** Tooltip on run detail header (includes pointer to stage-level Retry). */
export const RUN_LEVEL_RETRY_TOOLTIP_DETAIL = `${RUN_LEVEL_RETRY_TOOLTIP_BASE} To redo one stage on this same run, use Retry in the stage panel.`
