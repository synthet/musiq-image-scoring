import { api } from './client'
import type { Run, Stage, Step, WorkItem, QueueEntry, JobExecutionReport, ImageActionsResponse } from '@/types/api'

export interface RunSubmitRequest {
  scope_type: 'file' | 'folder' | 'folder_recursive' | 'path_list'
  scope_paths: string[]
  stages?: string[]
  skip_done?: boolean
  force_rerun?: boolean
  /** When true, backend limits scoring to incomplete images under scope (see API docs). */
  fix_incomplete_stages?: boolean
  /** Validation-repair pipeline mode: stage-specific issue scan + minimal repair actions. */
  validation_repair_mode?: boolean
  /** If true, run submits with dry-run repair actions (scan only). */
  validation_repair_dry_run?: boolean
  /** When true, force post-completion data-quality audit (see API / config). */
  post_run_audit?: boolean
  /** Stored as jobs.description for troubleshooting. */
  description?: string
}

export interface RunsListPayload {
  runs: Run[]
  total: number
}

/** GET /api/runs/:id/diagnostics */
export interface RunDiagnosticsResponse {
  job_id: number
  job_status: string
  post_run_audit: Record<string, unknown> | null
  image_phase_status_by_phase: Record<string, Record<string, number>>
  execution_report: JobExecutionReport | null
  endpoints: {
    stages: string
    stage_items_template: string
    stage_steps_template: string
    report_images?: string
  }
}

export const runsApi = {
  /** Default list (active overview). With `history: true`, returns `{ runs, total }` for terminal jobs only. */
  list: async (
    params?: { status?: string; limit?: number; offset?: number; history?: boolean },
  ): Promise<Run[] | RunsListPayload> => {
    const q = new URLSearchParams()
    if (params?.status) q.set('status', params.status)
    if (params?.limit != null) q.set('limit', String(params.limit))
    if (params?.offset != null) q.set('offset', String(params.offset))
    if (params?.history) q.set('history', 'true')
    const qs = q.toString()
    const res = await api.get<Run[] | RunsListPayload | { runs?: Run[]; total?: number }>(
      `/jobs/recent?${qs}`,
    )
    if (params?.history) {
      if (res && typeof res === 'object' && !Array.isArray(res) && Array.isArray(res.runs)) {
        return {
          runs: res.runs,
          total: typeof res.total === 'number' ? res.total : 0,
        }
      }
      return { runs: [], total: 0 }
    }
    return Array.isArray(res) ? res : res && 'runs' in res && Array.isArray(res.runs) ? res.runs : []
  },
  get: (id: number) => api.get<Run>(`/jobs/${id}`),
  submit: (body: RunSubmitRequest) => api.post<{ run_id: number; queue_position: number }>('/runs/submit', body),
  pause: (id: number) => api.post<void>(`/runs/${id}/pause`),
  resume: (id: number) => api.post<void>(`/runs/${id}/resume`),
  cancel: (id: number) => api.post<void>(`/runs/${id}/cancel`),
  retry: (id: number) =>
    api.post<{ success: boolean; run_id: number; queue_position: number }>(`/runs/${id}/retry`),
  force: (id: number) => api.post<{ success: boolean; run_id: number; actions: string[] }>(`/runs/${id}/force`, { confirm: true }),

  getStages: (id: number) => api.get<Stage[]>(`/runs/${id}/stages`),
  retryStage: (id: number, code: string) => api.post<void>(`/runs/${id}/stages/${code}/retry`),
  skipStage: (id: number, code: string) => api.post<void>(`/runs/${id}/stages/${code}/skip`),

  getSteps: (id: number, code: string) => api.get<Step[]>(`/runs/${id}/stages/${code}/steps`),
  getWorkItems: (id: number, code: string, offset = 0, limit = 50) =>
    api.get<{ items: WorkItem[]; total: number }>(`/runs/${id}/stages/${code}/items?offset=${offset}&limit=${limit}`),

  getDiagnostics: (id: number) =>
    api.get<RunDiagnosticsResponse>(`/runs/${id}/diagnostics`),

  getReport: (id: number) => api.get<JobExecutionReport>(`/runs/${id}/report`),
  getReportImages: (id: number, params?: { phase_code?: string; action?: string; offset?: number; limit?: number }) => {
    const q = new URLSearchParams()
    if (params?.phase_code) q.set('phase_code', params.phase_code)
    if (params?.action) q.set('action', params.action)
    if (params?.offset != null) q.set('offset', String(params.offset))
    if (params?.limit != null) q.set('limit', String(params.limit))
    const qs = q.toString()
    return api.get<ImageActionsResponse>(`/runs/${id}/report/images${qs ? `?${qs}` : ''}`)
  },

  queue: () => api.get<QueueEntry[]>('/queue'),
  reorderQueue: (runId: number, newPosition: number) =>
    api.post<void>('/queue/reorder', { run_id: runId, new_position: newPosition }),
  maintenanceStart: (body: {
    action: string
    input_path?: string
    limit?: number
    dry_run?: boolean
    /** Display name for the run (Tools tab); stored as the run's primary label. */
    job_name?: string
    /** Human-readable troubleshooting text (jobs.description). */
    description?: string
    trigger?: string
    tool_id?: string
    ui_selected_scope_path?: string
  }) => api.post<{ run_id: number }>('/maintenance/start', body),
}
