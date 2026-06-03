import { api } from './client'
import { ApiError, parseApiErrorDetail } from './client'
import type {
  Run, Stage, Step, WorkItem, QueueEntry, JobExecutionReport, ImageActionsResponse, RunReportResponse,
  RunFolderBucketsResponse, RunsAutoDriveRequest, RunsAutoDriveResult,
  RunsDriveStartRequest, RunsDriveState, RunsDriveStatus,
} from '@/types/api'

export interface RunSubmitRequest {
  scope_type: 'file' | 'folder' | 'folder_recursive' | 'path_list'
  scope_paths: string[]
  stages?: string[]
  run_mode?: 'process_stale_or_missing'
  plan_dry_run?: boolean
  post_run_audit?: boolean
  description?: string
  generate_captions?: boolean
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
  image_phase_status_by_phase: Record<string, Record<string, number> | { _error: string }>
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

  folderBuckets: (params?: {
    root_path?: string
    q?: string
    bucket?: string
    limit?: number
    offset?: number
    include_complete?: boolean
  }) => {
    const query = new URLSearchParams()
    if (params?.root_path) query.set('root_path', params.root_path)
    if (params?.q) query.set('q', params.q)
    if (params?.bucket) query.set('bucket', params.bucket)
    if (params?.limit != null) query.set('limit', String(params.limit))
    if (params?.offset != null) query.set('offset', String(params.offset))
    if (params?.include_complete) query.set('include_complete', 'true')
    const qs = query.toString()
    return api.get<RunFolderBucketsResponse>(`/runs/folder-buckets${qs ? `?${qs}` : ''}`)
  },

  autoDrive: (body: RunsAutoDriveRequest) =>
    api.post<RunsAutoDriveResult>('/runs/auto-drive', body),

  /** Durable "Drive to Complete" loop (server-side; survives browser close). */
  drive: {
    start: (body: RunsDriveStartRequest) =>
      api.post<{ state: RunsDriveState; result: RunsDriveStatus['state']['last_result'] }>('/runs/drive/start', body),
    stop: () => api.post<{ state: RunsDriveState }>('/runs/drive/stop'),
    status: () => api.get<RunsDriveStatus>('/runs/drive/status'),
  },

  getReport: async (id: number): Promise<RunReportResponse> => {
    try {
      const res = await api.get<RunReportResponse | JobExecutionReport>(`/runs/${id}/report`)
      if (
        res
        && typeof res === 'object'
        && 'available' in res
        && typeof res.available === 'boolean'
      ) {
        return res as RunReportResponse
      }
      return {
        available: true,
        report: res as JobExecutionReport,
      }
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 404) {
          return {
            available: false,
            reason: 'not_available',
            message: parseApiErrorDetail(err.message) || 'Execution report not available.',
          }
        }
        return {
          available: false,
          reason: 'error',
          message: `Server error (${err.status})`,
        }
      }
      throw err
    }
  },
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
    job_name?: string
    description?: string
    trigger?: string
    tool_id?: string
    ui_selected_scope_path?: string
  }) => api.post<{ run_id: number }>('/maintenance/start', body),
}
