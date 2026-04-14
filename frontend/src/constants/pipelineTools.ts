/**
 * Pipeline Tools tab: copy, limits, and machine-readable tool lists (single source of truth).
 * Related CLIs: folder_data_quality_report, schedule_folder_quality_fix_runs, backfill_hashes, queue_scoring_incomplete_by_folder.
 */

export const PIPELINE_TOOLS_HEADER = {
  title: 'Pipeline Tools',
  subtitle: 'Maintain data integrity and perform batch repairs.',
} as const

export const SECTION = {
  reconciliation: {
    title: 'Reconciliation & Phase Fixes',
    subtitle: 'Low-impact tools to fix UI drift and structural inconsistencies.',
  },
  recalculate: {
    title: 'Recalculate status from data',
    subtitle:
      'Recomputes derivable per-image phase states and rebuilds folder rollups. Use after crashes, import drifts, or legacy migrations when badges look inconsistent. Replaces the old “Legacy Phase Backfill” control (index/metadata only).',
  },
  backfill: {
    title: 'Backfill & Repair',
    subtitle: 'Job-based tools that process large sets of images to repair data.',
  },
  cleanup: {
    title: 'Maintenance & Cleanup',
    subtitle: 'Maintenance tasks for library management.',
  },
} as const

/** Stale-phase probe (GET /maintenance/stale-running-phases). */
export const STALE_PHASE = {
  minAgeSeconds: 3600,
  probeLimit: 50,
  refetchIntervalMs: 30_000,
} as const

export const RECONCILE = {
  name: 'Reconcile Finished Phases',
  description:
    "Scans for images stuck in 'running' belonging to jobs that are already finished. Fixes UI badge drift.",
  action: 'reconcile',
  limit: 5000,
} as const

/** POST /api/maintenance/start — queued maintenance runner */
export const MAINTENANCE_QUEUED = [
  {
    id: 'healThumbnails',
    name: 'Heal Thumbnails',
    description:
      'Scans for images with missing or broken thumbnail files and regenerates them in the background.',
    action: 'heal_thumbnails',
    limit: 500,
    button: 'Heal',
    variant: 'primary' as const,
  },
  {
    id: 'backfillExif',
    name: 'Backfill EXIF Dates',
    description: 'Re-extracts EXIF metadata for images missing timestamps due to legacy bugs.',
    action: 'backfill_exif',
    limit: 1000,
    button: 'Backfill',
    variant: 'primary' as const,
  },
] as const

/** POST /api/maintenance/start — prune */
export const PRUNE_MISSING = {
  name: 'Prune Missing Files',
  description: 'Removes database records for files that no longer exist on the filesystem.',
  action: 'prune_missing',
  limit: 10_000,
  button: 'Prune',
  variant: 'secondary' as const,
} as const

/** Direct API calls (not /maintenance/start) */
export const TOOLS_API = {
  fixDb: {
    name: 'Fix DB (re-score incomplete)',
    description:
      'Starts the scoring runner’s DB fix: re-scores images missing model scores or rating/label. Uses POST /api/scoring/fix-db (not the maintenance queue).',
    button: 'Start',
    variant: 'primary' as const,
  },
  backfillIndexMeta: {
    name: 'Backfill Index / Meta Status',
    description:
      'Queued maintenance job: sets indexing+metadata done for rows where scoring is already done but phase rows were missing (batched; repeat to drain).',
    limit: 1000,
    button: 'Queue',
    variant: 'primary' as const,
  },
  repairThumbnailPaths: {
    name: 'Repair Thumbnail Path Columns',
    description:
      'Synchronous batch: normalizes malformed thumbnail_path / thumbnail_path_win values (Docker paths, single-column pairs). Does not regenerate pixels — pair with Heal Thumbnails for missing files.',
    button: 'Repair paths',
    variant: 'secondary' as const,
  },
} as const

export const SCHEDULE_FOLDER_QUALITY = {
  name: 'Schedule folder quality fixes',
  description:
    'Queues validate-and-repair pipeline runs for leaf folders with open issues (incomplete scores, missing thumbs, stacks, bird species), worst-first. Spawns at most max(0, 10 − (running + queued jobs)) runs — one run per folder — same idea as schedule_folder_quality_fix_runs.py --top-folders-after-active.',
  budget: 10,
  button: 'Spawn jobs',
} as const

export const FULL_PIPELINE = {
  name: 'Run Full Pipeline (Missing)',
  description:
    'Submits all images with missing composite scores to the full Scoring + Tagging pipeline.',
  button: 'Queue Run',
} as const
