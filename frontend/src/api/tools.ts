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

  /**
   * Start a data backfill maintenance job.
   */
  backfillStart: (action: string) =>
    api.post<ApiEnvelope>(`/maintenance/start`, { action }),

  /**
   * Start a cleanup maintenance job (prune_missing, reconcile, ...).
   * Same /maintenance/start endpoint, but passes optional dry_run / input_path.
   */
  cleanupStart: (
    action: string,
    body?: { dry_run?: boolean; input_path?: string | null },
  ) =>
    api.post<ApiEnvelope>(`/maintenance/start`, {
      action,
      ...(body?.dry_run !== undefined ? { dry_run: body.dry_run } : {}),
      ...(body?.input_path ? { input_path: body.input_path } : {}),
      trigger: 'runs_tools_tab',
    }),
}

export function formatToolError(err: unknown): string {
  if (err instanceof ApiError) {
    return parseApiErrorDetail(err.message)
  }
  if (err instanceof Error) return err.message
  return String(err)
}
