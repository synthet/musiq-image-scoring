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
    refetchInterval: 5000,
  })

  const { data: stagesData, isLoading: stagesLoading } = useQuery({
    queryKey: runStagesQueryKey(id),
    queryFn: () => runsApi.getStages(id),
    refetchInterval: run?.status === 'running' ? 5000 : false,
  })
  const stages = Array.isArray(stagesData) ? stagesData : []

  useEffect(() => {
    if (runsVersion === 0) return
    qc.invalidateQueries({ queryKey: runDetailQueryKey(id) })
    qc.invalidateQueries({ queryKey: runStagesQueryKey(id) })
  }, [runsVersion, id, qc])

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
    stages[stages.length - 1]?.phase_code ??
    null

  const selectedStageData = stages.find((s) => s.phase_code === activeStage)

  const scopePaths = run && Array.isArray(run.scope_paths) && run.scope_paths.length > 0
    ? run.scope_paths
    : run ? [run.input_path ?? ''] : []

  if (runLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 size={20} className="text-[#4fc1ff] animate-spin" />
      </div>
    )
  }

  if (!run) {
    return (
      <div className="p-6">
        <p className="text-sm text-[#f44747]">Run #{id} not found</p>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex items-start gap-3">
        <Button variant="ghost" size="sm" onClick={() => navigate('/runs')} className="shrink-0 mt-0.5">
          <ArrowLeft size={13} />
        </Button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 mb-1">
            <h1 className="text-base font-semibold text-[#cccccc]">
              Run <span className="text-[#6d6d6d]">#{run.id}</span>
            </h1>
            <RunBadge status={run.status} />
          </div>
          <div className="flex items-center gap-2 text-sm text-[#9d9d9d]">
            <FolderOpen size={13} />
            <span className="truncate">{scopePaths.join(', ')}</span>
          </div>
          {run.description?.trim() && (
            <p className="text-xs text-[#b8b8b8] mt-2 leading-relaxed max-w-3xl">{run.description.trim()}</p>
          )}
          <div className="flex gap-3 text-xs text-[#6d6d6d] mt-1">
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
              <Pause size={12} />
              Pause
            </Button>
          )}
          {run.status === 'paused' && (
            <Button size="sm" variant="primary" onClick={() => resumeMut.mutate()} loading={resumeMut.isPending}>
              <Play size={12} />
              Resume
            </Button>
          )}
          {(run.status === 'failed' || run.status === 'interrupted') && (
            <Button size="sm" variant="secondary" onClick={() => retryMut.mutate()} loading={retryMut.isPending}>
              <RotateCcw size={12} />
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
              <XCircle size={12} />
              Cancel
            </Button>
          )}
        </div>
      </div>

      {/* Workflow graph */}
      <div className="rounded-md border border-[#474747] bg-[#1e1e1e] p-4">
        <div className="text-[10px] font-semibold uppercase tracking-wider text-[#6d6d6d] mb-3">
          Workflow
        </div>
        {stagesLoading ? (
          <div className="flex items-center gap-2 text-sm text-[#6d6d6d]">
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
          <p className="text-xs text-[#6d6d6d]">No stages recorded for this run</p>
        )}
      </div>

      {/* Selected stage detail */}
      {selectedStageData && (
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-[#6d6d6d] mb-2">
            {STAGE_DISPLAY[selectedStageData.phase_code as StageCode]?.name ?? selectedStageData.phase_code}
          </div>
          <StagePanel runId={id} stage={selectedStageData} />
        </div>
      )}

      {/* Queued flags / mode (jobs.queue_payload) */}
      <RunQueuePayloadPanel jobType={run.job_type} queuePayload={run.queue_payload} />

      {/* Post-run data quality audit (queue_payload.post_run_audit) */}
      {run.queue_payload && typeof run.queue_payload.post_run_audit === 'object' && run.queue_payload.post_run_audit != null && (
        <div className="rounded-md border border-[#474747] bg-[#1e1e1e] p-4">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-[#6d6d6d] mb-2">
            Data quality (post-run)
          </div>
          <PostRunAuditSummary audit={run.queue_payload.post_run_audit as Record<string, unknown>} runId={id} />
        </div>
      )}

      {/* Execution report (for terminal jobs) */}
      {(run.status === 'completed' || run.status === 'failed' || run.status === 'canceled' || run.status === 'interrupted') && (
        <ReportPanel runId={id} />
      )}

      {/* Log panel */}
      <div>
        <div className="text-[10px] font-semibold uppercase tracking-wider text-[#6d6d6d] mb-2">
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

function PostRunAuditSummary({ audit, runId }: { audit: Record<string, unknown>; runId: number }) {
  const status = String(audit.status ?? '—')
  const severity = String(audit.severity ?? '')
  const counts = audit.issue_counts
  const note = typeof audit.notes === 'string' ? audit.notes : null
  return (
    <div className="space-y-2 text-xs text-[#cccccc]">
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        <span>
          Status: <span className="text-[#9d9d9d]">{status}</span>
        </span>
        {severity ? (
          <span>
            Severity: <span className="text-[#9d9d9d]">{severity}</span>
          </span>
        ) : null}
      </div>
      {counts != null && typeof counts === 'object' ? (
        <pre className="text-[10px] text-[#9d9d9d] whitespace-pre-wrap break-words max-h-32 overflow-auto rounded bg-[#252526] p-2 border border-[#3c3c3c]">
          {JSON.stringify(counts, null, 2)}
        </pre>
      ) : null}
      {note ? <p className="text-[#6d6d6d] leading-relaxed">{note}</p> : null}
      <p className="text-[#6d6d6d]">
        Full JSON: <code className="text-[#4fc1ff]">GET /api/runs/{runId}/diagnostics</code>
      </p>
    </div>
  )
}
