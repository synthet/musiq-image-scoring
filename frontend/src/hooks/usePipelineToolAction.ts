import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  toolsApi,
  formatToolError,
  type ApiEnvelope,
  type RecalculateStatusSummary,
  type ScheduleFolderQualityRunsData,
} from '@/api/tools'
import { runsApi } from '@/api/runs'
import { FULL_PIPELINE_STAGE_CODES } from '@/constants/pipeline'
import { SCHEDULE_FOLDER_QUALITY, TOOLS_API } from '@/constants/pipelineTools'

export type PipelineToolAction =
  | {
      kind: 'maintenance'
      /** Stable id for matching loading state to a control */
      trackingId: string
      action: string
      label: string
      limit?: number
      invalidateStalePhases?: boolean
    }
  | {
      kind: 'envelope'
      trackingId: string
      label: string
      request: () => Promise<ApiEnvelope>
      invalidateRuns?: boolean
      invalidateFolders?: boolean
      invalidateStalePhases?: boolean
    }
  | {
      kind: 'scheduleFolderQuality'
      trackingId: string
      rootPath?: string
      healThumbnailsGlobal: boolean
    }
  | { kind: 'fullPipeline'; trackingId: string; path: string }
  | { kind: 'recalculate'; trackingId: string; scope: 'all' | 'selected_folder'; scopePath?: string }

type MaintenanceStartResult = { run_id: number }

function isApiEnvelope(x: unknown): x is ApiEnvelope {
  return typeof x === 'object' && x !== null && 'success' in x && 'message' in x
}

export type UsePipelineToolActionOptions = {
  /** After a full-pipeline run is queued successfully (folder scope). */
  onFullPipelineQueued?: (folderPath: string) => void
  /** After recalculate-status-from-data succeeds (e.g. close confirm dialog). */
  onRecalculateSuccess?: () => void
}

export function usePipelineToolAction(options?: UsePipelineToolActionOptions) {
  const queryClient = useQueryClient()
  const [lastBanner, setLastBanner] = useState<{ ok: boolean; text: string } | null>(null)
  const [recalcSummary, setRecalcSummary] = useState<RecalculateStatusSummary | null>(null)
  const [scheduleQualityStats, setScheduleQualityStats] = useState<ScheduleFolderQualityRunsData | null>(null)

  const mutation = useMutation<unknown, Error, PipelineToolAction>({
    mutationFn: async (action: PipelineToolAction): Promise<unknown> => {
      switch (action.kind) {
        case 'maintenance':
          return runsApi.maintenanceStart({
            action: action.action,
            limit: action.limit,
            job_name: action.label,
          })
        case 'envelope':
          return action.request()
        case 'scheduleFolderQuality':
          return toolsApi.scheduleFolderQualityRuns({
            budget: SCHEDULE_FOLDER_QUALITY.budget,
            run_mode: 'validate_and_repair',
            root_path: action.rootPath,
            heal_thumbnails_global: action.healThumbnailsGlobal,
          })
        case 'fullPipeline':
          return runsApi.submit({
            scope_type: 'folder_recursive',
            scope_paths: [action.path],
            stages: [...FULL_PIPELINE_STAGE_CODES],
            skip_done: true,
          })
        case 'recalculate':
          return toolsApi.recalculateStatusFromData({
            scope: action.scope,
            scopePath: action.scopePath,
          })
        default: {
          const _x: never = action
          return _x
        }
      }
    },
    onSuccess: (data, variables) => {
      if (variables.kind === 'maintenance') {
        const r = data as MaintenanceStartResult
        setLastBanner({
          ok: true,
          text: `${variables.label} job queued (Run ID: ${r.run_id}). Track progress in history.`,
        })
        void queryClient.invalidateQueries({ queryKey: ['runs'] })
        if (variables.invalidateStalePhases) {
          void queryClient.invalidateQueries({ queryKey: ['maintenance-stale-phases'] })
        }
        return
      }
      if (variables.kind === 'envelope') {
        if (!isApiEnvelope(data)) {
          setLastBanner({ ok: false, text: 'Unexpected response' })
          return
        }
        const extra =
          data.data && typeof data.data === 'object'
            ? ` ${JSON.stringify(data.data)}`
            : ''
        setLastBanner({ ok: data.success, text: `${variables.label}: ${data.message}${extra}` })
        if (variables.invalidateRuns !== false) {
          void queryClient.invalidateQueries({ queryKey: ['runs'] })
        }
        if (variables.invalidateFolders) {
          void queryClient.invalidateQueries({ queryKey: ['folders-tree'] })
        }
        if (variables.invalidateStalePhases) {
          void queryClient.invalidateQueries({ queryKey: ['maintenance-stale-phases'] })
        }
        return
      }
      if (variables.kind === 'scheduleFolderQuality') {
        if (!isApiEnvelope(data)) {
          setLastBanner({ ok: false, text: 'Unexpected response' })
          setScheduleQualityStats(null)
          return
        }
        const d = data.data as ScheduleFolderQualityRunsData | undefined
        if (d && typeof d === 'object') {
          setScheduleQualityStats(d)
          const extra = ` Active jobs: ${d.active_jobs}; slots this round: ${d.capacity_slots}; scheduled: ${d.scheduled_this_round}; folders left: ${d.folders_remaining_after}.`
          setLastBanner({ ok: data.success, text: `${data.message}${extra}` })
        } else {
          setScheduleQualityStats(null)
          setLastBanner({ ok: data.success, text: data.message })
        }
        void queryClient.invalidateQueries({ queryKey: ['runs'] })
        return
      }
      if (variables.kind === 'fullPipeline') {
        const r = data as { run_id: number; queue_position: number }
        setLastBanner({
          ok: true,
          text: `Full pipeline queued for folder (Run ID: ${r.run_id}). Position: ${r.queue_position}`,
        })
        void queryClient.invalidateQueries({ queryKey: ['runs'] })
        void queryClient.invalidateQueries({ queryKey: ['folders-tree'] })
        options?.onFullPipelineQueued?.(variables.path)
        return
      }
      if (variables.kind === 'recalculate') {
        if (!isApiEnvelope(data)) {
          setLastBanner({ ok: false, text: 'Unexpected response' })
          return
        }
        const extra =
          data.data && typeof data.data === 'object' ? ` ${JSON.stringify(data.data)}` : ''
        setLastBanner({ ok: data.success, text: `Recalculate status: ${data.message}${extra}` })
        const summaryCandidate = data.data && (data.data as { summary?: unknown }).summary
        if (summaryCandidate && typeof summaryCandidate === 'object') {
          setRecalcSummary(summaryCandidate as RecalculateStatusSummary)
        } else {
          setRecalcSummary(null)
        }
        void queryClient.invalidateQueries({ queryKey: ['maintenance-stale-phases'] })
        void queryClient.invalidateQueries({ queryKey: ['folders-tree'] })
        void queryClient.invalidateQueries({ queryKey: ['runs'] })
        options?.onRecalculateSuccess?.()
      }
    },
    onError: (e, variables) => {
      setLastBanner({ ok: false, text: formatToolError(e) })
      if (variables.kind === 'recalculate') setRecalcSummary(null)
      if (variables.kind === 'scheduleFolderQuality') setScheduleQualityStats(null)
    },
  })

  const run = (action: PipelineToolAction) => mutation.mutate(action)

  const envelope = {
    fixDb: (): void =>
      run({
        kind: 'envelope',
        trackingId: 'fixDb',
        label: TOOLS_API.fixDb.name,
        request: () => toolsApi.fixDatabase(),
        invalidateRuns: true,
      }),
    backfillIndexMeta: (): void =>
      run({
        kind: 'envelope',
        trackingId: 'backfillIndexMeta',
        label: TOOLS_API.backfillIndexMeta.name,
        request: () => toolsApi.backfillIndexMeta(TOOLS_API.backfillIndexMeta.limit),
        invalidateRuns: true,
      }),
    repairThumbnailPaths: (): void =>
      run({
        kind: 'envelope',
        trackingId: 'repairThumbnailPaths',
        label: TOOLS_API.repairThumbnailPaths.name,
        request: () => toolsApi.repairThumbnailPaths(),
      }),
  }

  const pendingId = mutation.variables?.trackingId

  return {
    run,
    envelope,
    isPending: mutation.isPending,
    pendingId,
    lastBanner,
    setLastBanner,
    recalcSummary,
    setRecalcSummary,
    scheduleQualityStats,
    setScheduleQualityStats,
  }
}
