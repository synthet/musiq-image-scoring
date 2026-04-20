import { clsx } from 'clsx'
import {
  ChevronRight,
} from 'lucide-react'
import { STAGE_DISPLAY } from '@/types/api'
import type { Stage, StageState } from '@/types/api'
import { Progress } from '@/components/ui/progress'
import { PhaseStatusIcon, normalizePhaseStatus, getPhaseStatusMeta } from '@/components/status/PhaseStatusIcon'
import { useWsStore } from '@/stores/wsStore'

interface WorkflowGraphProps {
  runId: number
  stages: Stage[]
  activeStage: string | null
  onSelectStage: (code: string) => void
}

export function WorkflowGraph({ runId, stages, activeStage, onSelectStage }: WorkflowGraphProps) {
  const progress = useWsStore((s) => s.runProgress[runId])

  return (
    <div className="flex items-start gap-0 overflow-x-auto pb-2">
      {stages.map((stage, i) => {
        const isActive = activeStage === stage.phase_code
        const liveProgress =
          progress && progress.stage === stage.phase_code ? progress : null

        return (
          <div key={stage.phase_code} className="flex items-center">
            <StageNode
              stage={stage}
              liveProgress={liveProgress}
              isSelected={isActive}
              onClick={() => onSelectStage(stage.phase_code)}
            />
            {i < stages.length - 1 && (
              <ChevronRight size={16} className="text-[#474747] shrink-0 mx-0.5" />
            )}
          </div>
        )
      })}
    </div>
  )
}

interface StageNodeProps {
  stage: Stage
  liveProgress: { items_done: number; items_total: number; throughput: number; eta_seconds: number } | null
  isSelected: boolean
  onClick: () => void
}

function StageNode({ stage, liveProgress, isSelected, onClick }: StageNodeProps) {
  const display = STAGE_DISPLAY[stage.phase_code as keyof typeof STAGE_DISPLAY]
  const pct = liveProgress
    ? (liveProgress.items_total > 0 ? Math.round((liveProgress.items_done / liveProgress.items_total) * 100) : 0)
    : stage.items_done != null && stage.items_total != null && stage.items_total > 0
      ? Math.round((stage.items_done / stage.items_total) * 100)
      : null

  return (
    <button
      onClick={onClick}
      className={clsx(
        'flex flex-col items-center gap-1.5 rounded-md p-3 min-w-[110px] max-w-[140px] text-left transition-all border',
        'hover:border-[#4fc1ff]',
        isSelected
          ? 'border-[#4fc1ff] bg-[#003f6e]'
          : 'border-[#474747] bg-[#252526]',
      )}
    >
      <div className="flex items-center gap-1.5 w-full">
        <StateIcon state={stage.state} />
        <span className="text-xs font-medium text-[#cccccc] truncate">
          {display?.name ?? stage.phase_code}
        </span>
      </div>

      <div className="w-full">
        <div className="flex items-center justify-between mb-1">
          <StageBadgeText state={stage.state} />
          {pct != null && stage.state === 'running' && (
            <span className="text-[10px] text-[#9d9d9d]">{pct}%</span>
          )}
        </div>

        {stage.state === 'running' && pct != null && (
          <Progress value={pct} size="sm" color="blue" />
        )}

        {stage.state === 'completed' && <DurationText stage={stage} />}
        {stage.state === 'failed' && (
          <span className="text-[10px] text-[#f44747] truncate block">Failed</span>
        )}
        {stage.state === 'interrupted' && (
          <span className="text-[10px] text-[#cca700] truncate block">Interrupted</span>
        )}
      </div>

      {liveProgress && liveProgress.throughput > 0 && (
        <div className="text-[10px] text-[#6d6d6d]">
          {liveProgress.throughput.toFixed(1)} img/s · ETA {formatEta(liveProgress.eta_seconds)}
        </div>
      )}
    </button>
  )
}

function StateIcon({ state }: { state: StageState }) {
  return <PhaseStatusIcon status={state} size={14} animated />
}

function StageBadgeText({ state }: { state: StageState }) {
  const { colorClass } = getPhaseStatusMeta(state)
  const normalizedState = normalizePhaseStatus(state)
  const labels: Record<StageState, string> = {
    pending: 'Pending',
    queued: 'Queued',
    running: 'Running',
    paused: 'Paused',
    completed: 'Done',
    failed: 'Failed',
    skipped: 'Skipped',
    interrupted: 'Interrupted',
    cancel_requested: 'Cancel Requested',
    restarting: 'Restarting',
    canceled: 'Canceled',
  }
  const fallbackLabel = normalizedState.charAt(0).toUpperCase() + normalizedState.slice(1).replace('_', ' ')
  return <span className={clsx('text-[10px]', colorClass)}>{labels[state] ?? fallbackLabel}</span>
}

function DurationText({ stage }: { stage: Stage }) {
  if (!stage.started_at || !stage.completed_at) return null
  const ms = new Date(stage.completed_at).getTime() - new Date(stage.started_at).getTime()
  return <span className="text-[10px] text-[#6d6d6d]">{formatMs(ms)}</span>
}

function formatMs(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`
}

function formatEta(sec: number): string {
  if (sec < 60) return `${Math.round(sec)}s`
  return `${Math.floor(sec / 60)}m ${Math.round(sec % 60)}s`
}
