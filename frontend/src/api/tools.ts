import { api, ApiError, parseApiErrorDetail } from '@/api/client'

export interface ApiEnvelope<T = Record<string, unknown>> {
  success: boolean
  message: string
  data?: T
}

export interface HealPhaseData {
  phase_code: string
  dry_run: boolean
  false_positives_found: number
  resets_performed: number
  folders_needing_work: number
  eligible_folders: number
  capacity_slots: number
  scheduled: Array<{
    folder_path: string
    job_id?: number
    queue_position?: number
  }>
  budget: number
}

export const toolsApi = {
  /**
   * Heal a specific workflow phase: identify false completions, reset, and spawn repair runs.
   */
  healPhase: (
    phaseCode: string,
    body?: {
      root_path?: string | null
      dry_run?: boolean
      budget?: number
      run_mode?: string
    },
  ) => api.post<ApiEnvelope<HealPhaseData>>(`/maintenance/heal/${phaseCode}`, body ?? {}),
}

export function formatToolError(err: unknown): string {
  if (err instanceof ApiError) {
    return parseApiErrorDetail(err.message)
  }
  if (err instanceof Error) return err.message
  return String(err)
}
