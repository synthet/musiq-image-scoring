import { api } from './client'
import type { RunFolderBucketPhase, StageCode } from '@/types/api'

export interface FolderDetail {
  id: number
  path: string
  parent_id: number | null
  is_fully_scored: boolean
  image_count: number
  created_at: string | null
}

export interface FolderPhaseStatusRow {
  code: string
  name: string
  status: string
  done_count: number
  failed_count: number
  running_count: number
  queued_count: number
  paused_count: number
  cancel_requested_count: number
  restarting_count: number
  skipped_count: number
  total_count: number
}

export interface FolderPhaseStatusResponse {
  folder_path: string
  phases: FolderPhaseStatusRow[]
}

export function folderPhasesToBucketPhases(phases: FolderPhaseStatusRow[]): RunFolderBucketPhase[] {
  return phases.map((p) => {
    const total = p.total_count || 0
    const done = p.done_count || 0
    const percent = total > 0 ? Math.round((done / total) * 100) : 0
    return {
      code: p.code as StageCode,
      name: p.name,
      status: p.status,
      done: p.done_count || 0,
      skipped: p.skipped_count || 0,
      failed: p.failed_count || 0,
      running: p.running_count || 0,
      queued: p.queued_count || 0,
      paused: p.paused_count || 0,
      cancel_requested: p.cancel_requested_count || 0,
      restarting: p.restarting_count || 0,
      total,
      percent,
    }
  })
}

export const foldersApi = {
  get: (folderId: number) => api.get<FolderDetail>(`/folders/${folderId}`),

  phaseStatus: (path: string, forceRefresh = false) => {
    const q = new URLSearchParams({ path })
    if (forceRefresh) q.set('force_refresh', 'true')
    return api.get<FolderPhaseStatusResponse>(`/folders/phase-status?${q.toString()}`)
  },
}
