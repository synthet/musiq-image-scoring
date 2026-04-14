import { api, ApiError, parseApiErrorDetail } from '@/api/client'

export interface ApiEnvelope<T = Record<string, unknown>> {
  success: boolean
  message: string
  data?: T
}

export interface StaleRunningPhasesResponse {
  min_age_seconds: number
  count_estimate: number
  reconcilable_count: number
  sample: Array<{
    image_id: number | null
    job_id: number | null
    phase_code: string
    started_at: string | null
    last_error: string | null
    file_path: string | null
  }>
}

export interface RecalculateStatusSummary {
  scope: 'all' | 'selected_folder'
  scope_path: string | null
  target_images: number
  per_image_changes: {
    indexing_metadata_backfilled_images: number
    keywords_phase_backfilled_rows: number
    culling_failed_to_done_rows: number
    total_rows_changed_estimate: number
  }
  folder_aggregate_changes: {
    folders_recomputed: number
    folders_marked_keywords_processed: number
  }
  before: {
    missing_indexing_or_metadata_with_scoring_done: number
    missing_keywords_status_with_keywords_data: number
    culling_failed_with_data_present: number
  }
  after: {
    missing_indexing_or_metadata_with_scoring_done: number
    missing_keywords_status_with_keywords_data: number
    culling_failed_with_data_present: number
  }
  warnings: string[]
}

export interface ScheduleFolderQualityRunsData {
  budget: number
  active_jobs: number
  capacity_slots: number
  folders_total_needing_work: number
  scheduled_this_round: number
  folders_remaining_after: number
  scheduled: Array<{
    folder_path: string
    stages: string[]
    run_id: number | null
    queue_position: number | null
  }>
  errors: string[]
  global_thumbnail_heal_run_id: number | null
  dry_run: boolean
}

export const toolsApi = {
  staleRunningPhases: (minAgeSeconds = 3600, limit = 50) =>
    api.get<StaleRunningPhasesResponse>(
      `/maintenance/stale-running-phases?min_age_seconds=${minAgeSeconds}&limit=${limit}`,
    ),

  reconcileTerminalJobPhases: (limit = 5000) =>
    api.post<ApiEnvelope>(
      `/maintenance/reconcile-terminal-job-phases?limit=${encodeURIComponent(String(limit))}`,
    ),

  fixDatabase: () => api.post<ApiEnvelope>('/scoring/fix-db'),

  /** Re-extract EXIF for rows with null date_time_original (batch). */
  backfillExifDates: (limit = 1000) =>
    api.post<ApiEnvelope>(
      `/maintenance/backfill-exif-dates?limit=${encodeURIComponent(String(limit))}`,
    ),

  /** Quick path repair (≤1000 row updates) then missing raster regen (≤500). */
  healThumbnails: () => api.post<ApiEnvelope>('/maintenance/heal-thumbnails'),

  /** @param repairAll Full-table deep normalize (slower); default uses Postgres quick candidate filter */
  repairThumbnailPaths: (opts?: { repairAll?: boolean }) => {
    const q = opts?.repairAll ? '?repair_all=true' : ''
    return api.post<ApiEnvelope>(`/maintenance/repair-thumbnail-paths${q}`)
  },

  recalculateStatusFromData: (opts?: { scope?: 'all' | 'selected_folder'; scopePath?: string }) => {
    const p = new URLSearchParams()
    if (opts?.scope) p.set('scope', opts.scope)
    if (opts?.scopePath?.trim()) p.set('scope_path', opts.scopePath.trim())
    const q = p.toString()
    return api.post<ApiEnvelope>(`/maintenance/recalculate-status-from-data${q ? `?${q}` : ''}`)
  },

  /** Global index/meta phase backfill (batched maintenance job). */
  backfillIndexMeta: (limit = 1000) =>
    api.post<ApiEnvelope>(`/maintenance/backfill-index-meta?limit=${encodeURIComponent(String(limit))}`),

  /**
   * Queue up to `max(0, budget - active_jobs)` validate-and-repair runs — one job per leaf folder
   * with data-quality issues (same rollup as folder_data_quality_report / schedule_folder_quality_fix_runs.py).
   */
  scheduleFolderQualityRuns: (body?: {
    root_path?: string | null
    stack_after_culling_only?: boolean
    budget?: number
    run_mode?: 'validate_and_repair' | 'process_unprocessed_or_empty' | 'process_all_overwrite'
    dry_run?: boolean
    heal_thumbnails_global?: boolean
  }) => api.post<ApiEnvelope<ScheduleFolderQualityRunsData>>(`/maintenance/schedule-folder-quality-runs`, body ?? {}),
}

export function formatToolError(err: unknown): string {
  if (err instanceof ApiError) {
    return parseApiErrorDetail(err.message)
  }
  if (err instanceof Error) return err.message
  return String(err)
}
