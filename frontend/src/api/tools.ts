import { api, ApiError, parseApiErrorDetail } from '@/api/client'

export interface ApiEnvelope {
  success: boolean
  message: string
  data?: Record<string, unknown>
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

  backfillIndexMeta: (limit = 1000) =>
    api.post<ApiEnvelope>(
      `/maintenance/backfill-index-meta?limit=${encodeURIComponent(String(limit))}`,
    ),

  /** Quick path repair (≤1000 row updates) then missing raster regen (≤500). */
  healThumbnails: () => api.post<ApiEnvelope>('/maintenance/heal-thumbnails'),

  /** @param repairAll Full-table deep normalize (slower); default uses Postgres quick candidate filter */
  repairThumbnailPaths: (opts?: { repairAll?: boolean }) => {
    const q = opts?.repairAll ? '?repair_all=true' : ''
    return api.post<ApiEnvelope>(`/maintenance/repair-thumbnail-paths${q}`)
  },
}

export function formatToolError(err: unknown): string {
  if (err instanceof ApiError) {
    return parseApiErrorDetail(err.message)
  }
  if (err instanceof Error) return err.message
  return String(err)
}
