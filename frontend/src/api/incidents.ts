import { api } from './client'
import type { ImageIncident, ImageIncidentsListResponse } from '@/types/api'

export interface IncidentsListParams {
  limit?: number
  offset?: number
  folder_id?: number
  job_id?: number
  phase_code?: string
  kind?: string
  since?: string
}

export const incidentsApi = {
  list: (params?: IncidentsListParams) => {
    const q = new URLSearchParams()
    if (params?.limit != null) q.set('limit', String(params.limit))
    if (params?.offset != null) q.set('offset', String(params.offset))
    if (params?.folder_id != null) q.set('folder_id', String(params.folder_id))
    if (params?.job_id != null) q.set('job_id', String(params.job_id))
    if (params?.phase_code) q.set('phase_code', params.phase_code)
    if (params?.kind) q.set('kind', params.kind)
    if (params?.since) q.set('since', params.since)
    const qs = q.toString()
    return api.get<ImageIncidentsListResponse>(`/incidents${qs ? `?${qs}` : ''}`)
  },

  get: (id: number) => api.get<ImageIncident>(`/incidents/${id}`),
}
