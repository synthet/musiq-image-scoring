import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft, FolderOpen, Pause, Play, XCircle, RotateCcw, Loader2,
} from 'lucide-react'
import { runsApi } from '@/api/runs'
import { RunBadge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { WorkflowGraph } from '@/components/runs/WorkflowGraph'
import { StagePanel } from '@/components/runs/StagePanel'
import { LogPanel } from '@/components/runs/LogPanel'
import { RunQueuePayloadPanel } from '@/components/runs/RunQueuePayloadPanel'
import { ReportPanel } from '@/components/runs/ReportPanel'
import { useWsStore } from '@/stores/wsStore'
import type { StageCode } from '@/types/api'
import { STAGE_DISPLAY } from '@/types/api'
import { RUN_LEVEL_RETRY_TOOLTIP_DETAIL } from '@/constants/runRetry'
import { RUNS_QUERY_ROOT, runDetailQueryKey, runStagesQueryKey } from '@/queryKeys/runs'

export function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>()
  const id = parseInt(runId ?? '', 10)
  const navigate = useNavigate()
  const qc = useQueryClient()
  const runsVersion = useWsStore((s) => s.runsVersion)

  const [selectedStage, setSelectedStage] = useState<string | null>(null)

  const { data: run, isLoading: runLoading } = useQuery({
    queryKey: runDetailQueryKey(id),
    queryFn: () => runsApi.get(id),
    refetchInterval: 30000, // watchdog only; WS invalidation is primary
  })

  const { data: stagesData, isLoading: stagesLoading } = useQuery({
    queryKey: runStagesQueryKey(id),
    queryFn: () => runsApi.getStages(id),
    refetchInterval: 30000, // watchdog only; WS invalidation is primary
  })
  const stages = Array.isArray(stagesData) ? stagesData : []

  useEffect(() => {
    if (runsVersion === 0) return
    qc.invalidateQueries({ queryKey: runDetailQueryKey(id) })
    qc.invalidateQueries({ queryKey: runStagesQueryKey(id) })
  }, [runsVersion, id, qc])

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      // Don't navigate if user is typing in an input or textarea
      const target = e.target as HTMLElement
      if (
        target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.isContentEditable
      ) {
        return
      }

      if (e.key === 'Escape') {
        navigate('/runs')
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [navigate])

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: runDetailQueryKey(id) })
    qc.invalidateQueries({ queryKey: runStagesQueryKey(id) })
    qc.invalidateQueries({ queryKey: RUNS_QUERY_ROOT })
  }

  const pauseMut = useMutation({ mutationFn: () => runsApi.pause(id), onSuccess: invalidate })
  const resumeMut = useMutation({ mutationFn: () => runsApi.resume(id), onSuccess: invalidate })
  const cancelMut = useMutation({ mutationFn: () => runsApi.cancel(id), onSuccess: invalidate })
  const retryMut = useMutation({
    mutationFn: () => runsApi.retry(id),
    onSuccess: (data) => {
      invalidate()
      if (data?.run_id != null && data.run_id !== id) {
        navigate(`/runs/${data.run_id}`)
      }
    },
  })

  const activeStage =
    selectedStage ??
    stages.find((s) => s.state === 'running')?.phase_code ??
    stages.find((s) => s.state === 'failed')?.phase_code ??
    stages.find((s) => s.state === 'queued' || s.state === 'pending')?.phase_code ??
    stages[stages.length - 1]?.phase_code ??
    null

  const selectedStageData = stages.find((s) => s.phase_code === activeStage)

  const scopePaths = run && Array.isArray(run.scope_paths) && run.scope_paths.length > 0
    ? run.scope_paths
    : run ? [run.input_path ?? ''] : []
  const reportSupported = run ? supportsExecutionReport(run) : false

  if (runLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 size={20} className="text-[var(--color-accent-bright)] animate-spin" />
      </div>
    )
  }

  if (!run) {
    return (
      <div className="p-6">
        <p className="text-sm text-[var(--color-danger)]">Run #{id} not found</p>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex items-start gap-3">
        <Button variant="ghost" size="sm" onClick={() => navigate('/runs')} className="shrink-0 mt-0.5">
          <ArrowLeft size={14} />
        </Button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 mb-1">
            <h1 className="text-base font-semibold text-[var(--color-text-primary)]">
              Run <span className="text-[var(--color-text-muted)]">#{run.id}</span>
            </h1>
            <RunBadge status={run.status} />
          </div>
          <div className="flex items-center gap-2 text-sm text-[var(--color-text-secondary)]">
            <FolderOpen size={14} />
            <span className="truncate">{scopePaths.join(', ')}</span>
          </div>
          {run.description?.trim() && (
            <p className="text-xs text-[var(--color-text-secondary)] mt-2 leading-relaxed max-w-3xl">{run.description.trim()}</p>
          )}
          <div className="flex gap-3 text-xs text-[var(--color-text-muted)] mt-1">
            {run.created_at && <span>Created {new Date(run.created_at).toLocaleString()}</span>}
            {run.started_at && <span>Started {new Date(run.started_at).toLocaleString()}</span>}
            {run.started_at && run.finished_at && (
              <span>
                Duration {formatDuration(run.started_at, run.finished_at)}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {run.status === 'running' && (
            <Button size="sm" variant="secondary" onClick={() => pauseMut.mutate()} loading={pauseMut.isPending}>
              <Pause size={14} />
              Pause
            </Button>
          )}
          {run.status === 'paused' && (
            <Button size="sm" variant="primary" onClick={() => resumeMut.mutate()} loading={resumeMut.isPending}>
              <Play size={14} />
              Resume
            </Button>
          )}
          {(run.status === 'failed' || run.status === 'interrupted') && (
            <Button
              size="sm"
              variant="secondary"
              onClick={() => retryMut.mutate()}
              loading={retryMut.isPending}
              title={RUN_LEVEL_RETRY_TOOLTIP_DETAIL}
            >
              <RotateCcw size={14} />
              Retry
            </Button>
          )}
          {(run.status === 'pending' || run.status === 'running' || run.status === 'queued' || run.status === 'paused') && (
            <Button
              size="sm"
              variant="danger"
              onClick={() => cancelMut.mutate()}
              loading={cancelMut.isPending}
            >
              <XCircle size={14} />
              Cancel
            </Button>
          )}
        </div>
      </div>

      {/* Workflow graph */}
      <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-primary)] p-4">
        <div className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)] mb-3">
          Workflow
        </div>
        {stagesLoading ? (
          <div className="flex items-center gap-2 text-sm text-[var(--color-text-muted)]">
            <Loader2 size={14} className="animate-spin" />
            Loading stages…
          </div>
        ) : stages.length > 0 ? (
          <WorkflowGraph
            runId={id}
            stages={stages}
            activeStage={activeStage}
            onSelectStage={(code) => setSelectedStage(code)}
          />
        ) : (
          <p className="text-xs text-[var(--color-text-muted)]">No stages recorded for this run</p>
        )}
      </div>

      {/* Selected stage detail */}
      {selectedStageData && (
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)] mb-2">
            {STAGE_DISPLAY[selectedStageData.phase_code as StageCode]?.name ?? selectedStageData.phase_code}
          </div>
          <StagePanel runId={id} stage={selectedStageData} />
        </div>
      )}

      {/* Queued flags / mode (jobs.queue_payload) */}
      <RunQueuePayloadPanel jobType={run.job_type} queuePayload={run.queue_payload} />

      {/* Post-run data quality audit (queue_payload.post_run_audit) */}
      {run.queue_payload && typeof run.queue_payload.post_run_audit === 'object' && run.queue_payload.post_run_audit != null && (
        <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-primary)] p-4">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)] mb-2">
            Data quality (post-run)
          </div>
          <PostRunAuditSummary audit={run.queue_payload.post_run_audit as Record<string, unknown>} runId={id} />
        </div>
      )}

      {/* Execution report (for terminal jobs) */}
      {(run.status === 'completed' || run.status === 'failed' || run.status === 'canceled' || run.status === 'interrupted') && (
        <ReportPanel runId={id} reportSupported={reportSupported} />
      )}

      {/* Log panel */}
      <div>
        <div className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)] mb-2">
          Run Log
        </div>
        <LogPanel
          runId={id}
          persistedLog={run.log}
          runStatus={run.status}
          startedAt={run.started_at}
        />
      </div>
    </div>
  )
}

function formatDuration(start: string, end: string): string {
  const ms = new Date(end).getTime() - new Date(start).getTime()
  if (ms < 60000) return `${(ms / 1000).toFixed(0)}s`
  return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`
}

function supportsExecutionReport(run: { job_type?: string; capabilities?: { execution_report?: boolean } | null }): boolean {
  if (typeof run.capabilities?.execution_report === 'boolean') {
    return run.capabilities.execution_report
  }
  const jt = String(run.job_type ?? '').trim().toLowerCase()
  if (['indexing', 'metadata', 'scoring', 'pipeline'].includes(jt)) return true
  return false
}

function PostRunAuditSummary({ audit, runId }: { audit: Record<string, unknown>; runId: number }) {
  const status = String(audit.status ?? '—')
  const severity = String(audit.severity ?? '')
  const counts = audit.issue_counts
  const note = typeof audit.notes === 'string' ? audit.notes : null
  return (
    <div className="space-y-2 text-xs text-[var(--color-text-primary)]">
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        <span>
          Status: <span className="text-[var(--color-text-secondary)]">{status}</span>
        </span>
        {severity ? (
          <span>
            Severity: <span className="text-[var(--color-text-secondary)]">{severity}</span>
          </span>
        ) : null}
      </div>
      {counts != null && typeof counts === 'object' ? (
        <pre className="text-[10px] text-[var(--color-text-secondary)] whitespace-pre-wrap break-words max-h-32 overflow-auto rounded bg-[var(--color-bg-secondary)] p-2 border border-[var(--color-border-muted)]">
          {JSON.stringify(counts, null, 2)}
        </pre>
      ) : null}
      {note ? <p className="text-[var(--color-text-muted)] leading-relaxed">{note}</p> : null}
      <p className="text-[var(--color-text-muted)]">
        Full JSON: <code className="text-[var(--color-accent-bright)]">GET /api/runs/{runId}/diagnostics</code>
      </p>
    </div>
  )
}
