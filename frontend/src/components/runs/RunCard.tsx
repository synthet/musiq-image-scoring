import { useNavigate } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { FolderOpen, XCircle, Pause, Play, RotateCcw, Zap } from 'lucide-react'
import { runsApi } from '@/api/runs'
import { RunBadge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Button } from '@/components/ui/button'
import { useWsStore } from '@/stores/wsStore'
import { STAGE_DISPLAY } from '@/types/api'
import { RUNS_QUERY_ROOT } from '@/queryKeys/runs'
import type { Run } from '@/types/api'

interface RunCardProps {
  run: Run
  compact?: boolean
}

export function RunCard({ run, compact = false }: RunCardProps) {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const progress = useWsStore((s) => s.runProgress[run.id])

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: RUNS_QUERY_ROOT })
  }

  const pauseMut = useMutation({ mutationFn: () => runsApi.pause(run.id), onSuccess: invalidate })
  const resumeMut = useMutation({ mutationFn: () => runsApi.resume(run.id), onSuccess: invalidate })
  const cancelMut = useMutation({ mutationFn: () => runsApi.cancel(run.id), onSuccess: invalidate })
  const retryMut = useMutation({
    mutationFn: () => runsApi.retry(run.id),
    onSuccess: (data) => {
      invalidate()
      if (data?.run_id != null && data.run_id !== run.id) {
        navigate(`/runs/${data.run_id}`)
      }
    },
  })
  const forceMut = useMutation({
    mutationFn: () => runsApi.force(run.id),
    onSuccess: (data) => {
      invalidate()
      if (data?.actions?.some(a => a.includes('no ghost runners'))) {
        console.info('Force: dispatcher should recover normally')
      }
    },
  })

  const scopePaths = Array.isArray(run.scope_paths) && run.scope_paths.length > 0
    ? run.scope_paths
    : [run.input_path ?? '']
  const scopeLabel = scopePaths[0] ?? '(unknown)'
  const extraPaths = scopePaths.length - 1

  const pct = progress
    ? (progress.items_total > 0 ? Math.max(0, Math.min(100, Math.round((progress.items_done / progress.items_total) * 100))) : 0)
    : null

  const currentStageDisplay =
    run.current_phase && STAGE_DISPLAY[run.current_phase as keyof typeof STAGE_DISPLAY]?.name

  return (
    <div
      className={clsx(
        'rounded-md border border-[#474747] bg-[#252526] transition-colors',
        'hover:border-[#4fc1ff] cursor-pointer',
        compact ? 'p-3' : 'p-4',
      )}
      onClick={() => navigate(`/runs/${run.id}`)}
    >
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-[#6d6d6d] text-xs font-mono shrink-0">#{run.id}</span>
          <FolderOpen size={13} className="text-[#9d9d9d] shrink-0" />
          <span className="text-sm font-medium text-[#cccccc] truncate" title={scopeLabel}>
            {scopeLabel}
          </span>
          {extraPaths > 0 && (
            <span className="text-xs text-[#6d6d6d] shrink-0">+{extraPaths} more</span>
          )}
        </div>
        <RunBadge status={run.status} />
      </div>
      {run.description?.trim() && (
        <p className="text-[11px] text-[#8d8d8d] mb-2 line-clamp-2" title={run.description.trim()}>
          {run.description.trim()}
        </p>
      )}

      {run.status === 'running' && (
        <div className="mb-2 space-y-1">
          {currentStageDisplay && (
            <div className="text-xs text-[#9d9d9d]">
              Stage: <span className="text-[#4fc1ff]">{currentStageDisplay}</span>
              {progress && progress.items_total > 0 && (
                <span className="ml-2 text-[#6d6d6d]">
                  {progress.items_done.toLocaleString()} / {progress.items_total.toLocaleString()}
                  {progress.throughput > 0 && ` · ${progress.throughput.toFixed(1)} img/s`}
                  {progress.eta_seconds > 0 && ` · ETA ${formatEta(progress.eta_seconds)}`}
                </span>
              )}
            </div>
          )}
          {pct != null && <Progress value={pct} size="sm" color="blue" showLabel />}
        </div>
      )}

      <div className="flex items-center justify-between">
        <span className="text-xs text-[#6d6d6d]">
          {formatRelative(run.created_at)}
          {run.started_at && run.finished_at && (
            <> · {formatDuration(run.started_at, run.finished_at)}</>
          )}
        </span>

        <div
          className="flex items-center gap-1"
          onClick={(e) => e.stopPropagation()}
        >
          {run.status === 'running' && (
            <Button
              size="xs"
              variant="ghost"
              onClick={() => pauseMut.mutate()}
              loading={pauseMut.isPending}
              title="Soft pause (finish current image)"
            >
              <Pause size={11} />
            </Button>
          )}
          {run.status === 'paused' && (
            <Button
              size="xs"
              variant="ghost"
              onClick={() => resumeMut.mutate()}
              loading={resumeMut.isPending}
            >
              <Play size={11} />
              Resume
            </Button>
          )}
          {(run.status === 'failed' || run.status === 'interrupted') && (
            <Button
              size="xs"
              variant="ghost"
              onClick={() => retryMut.mutate()}
              loading={retryMut.isPending}
            >
              <RotateCcw size={11} />
              Retry
            </Button>
          )}
          {(run.status === 'running' || run.status === 'queued') && (
            <Button
              size="xs"
              variant="ghost"
              onClick={() => forceMut.mutate()}
              loading={forceMut.isPending}
              className="text-[#cca700] hover:text-[#cca700]"
              title="Force-unstick this run"
            >
              <Zap size={11} />
            </Button>
          )}
          {(run.status === 'pending' || run.status === 'running' || run.status === 'queued' || run.status === 'paused') && (
            <Button
              size="xs"
              variant="ghost"
              onClick={() => cancelMut.mutate()}
              loading={cancelMut.isPending}
              className="text-[#f44747] hover:text-[#f44747]"
            >
              <XCircle size={11} />
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}

function formatRelative(ts: string | null): string {
  if (!ts) return 'unknown'
  const diff = Date.now() - new Date(ts).getTime()
  if (diff < 60000) return 'just now'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`
  return `${Math.floor(diff / 86400000)}d ago`
}

function formatDuration(start: string, end: string): string {
  const ms = new Date(end).getTime() - new Date(start).getTime()
  if (ms < 60000) return `${(ms / 1000).toFixed(0)}s`
  return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`
}

function formatEta(sec: number): string {
  if (sec < 60) return `${Math.round(sec)}s`
  return `${Math.floor(sec / 60)}m`
}
