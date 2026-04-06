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

  regenerateThumbnails: () => api.post<ApiEnvelope>('/maintenance/regenerate-thumbnails'),

  repairThumbnailPaths: () => api.post<ApiEnvelope>('/maintenance/repair-thumbnail-paths'),
}

export function formatToolError(err: unknown): string {
  if (err instanceof ApiError) {
    return parseApiErrorDetail(err.message)
  }
  if (err instanceof Error) return err.message
  return String(err)
}
