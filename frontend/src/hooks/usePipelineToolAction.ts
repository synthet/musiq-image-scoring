import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  toolsApi,
  formatToolError,
  type HealPhaseData,
} from '@/api/tools'
import { RUNS_QUERY_ROOT } from '@/queryKeys/runs'

export type PipelineToolAction =
  | {
      kind: 'heal'
      trackingId: string
      phaseCode: string
      rootPath?: string
      budget: number
      dryRun: boolean
      runMode: string
    }
  | {
      kind: 'backfill'
      trackingId: string
      actionName: string
    }

export type UsePipelineToolActionOptions = {
  /** After a heal run is spawned, optionally reveal path in sidebar */
  onHealSpawned?: (folderPath: string) => void
}

export function usePipelineToolAction(options?: UsePipelineToolActionOptions) {
  const queryClient = useQueryClient()
  const [lastBanner, setLastBanner] = useState<{ ok: boolean; text: string } | null>(null)
  const [healStats, setHealStats] = useState<HealPhaseData | null>(null)

  const mutation = useMutation<unknown, Error, PipelineToolAction>({
    mutationFn: async (action: PipelineToolAction): Promise<unknown> => {
      switch (action.kind) {
        case 'heal':
          return toolsApi.healPhase(action.phaseCode, {
            root_path: action.rootPath,
            budget: action.budget,
            dry_run: action.dryRun,
            run_mode: action.runMode,
          })
        case 'backfill':
          return toolsApi.backfillStart(action.actionName)
        default: {
          const _x: never = action
          return _x
        }
      }
    },
    onSuccess: (data, variables) => {
      if (variables.kind === 'heal') {
        if (
          !data ||
          typeof data !== 'object' ||
          !('success' in data) ||
          !('message' in data)
        ) {
          setLastBanner({ ok: false, text: 'Unexpected response' })
          setHealStats(null)
          return
        }
        const envelope = data as {
          success: boolean
          message: string
          data?: HealPhaseData
        }
        if (envelope.data && envelope.data.scheduled) {
          setHealStats(envelope.data)
          setLastBanner({ ok: envelope.success, text: envelope.message })
          if (envelope.data.scheduled.length > 0) {
            options?.onHealSpawned?.(envelope.data.scheduled[0].folder_path)
          }
        } else {
          setHealStats(null)
          setLastBanner({ ok: envelope.success, text: envelope.message })
        }
        void queryClient.invalidateQueries({ queryKey: RUNS_QUERY_ROOT })
      } else if (variables.kind === 'backfill') {
        const envelope = data as { success: boolean; message: string }
        setLastBanner({ ok: envelope.success, text: envelope.message })
        void queryClient.invalidateQueries({ queryKey: RUNS_QUERY_ROOT })
      }
    },
    onError: (e) => {
      setLastBanner({ ok: false, text: formatToolError(e) })
      setHealStats(null)
    },
  })

  const run = (action: PipelineToolAction) => mutation.mutate(action)
  const pendingId = mutation.variables?.trackingId

  return {
    run,
    isPending: mutation.isPending,
    pendingId,
    lastBanner,
    setLastBanner,
    healStats,
    setHealStats,
  }
}
