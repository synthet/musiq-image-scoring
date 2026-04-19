import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { clsx } from 'clsx'
import {
  AlertCircle, SkipForward, RefreshCw, ChevronDown, ChevronUp, ChevronLeft, ChevronRight,
  CheckCircle2, XCircle, Clock, Loader2, Circle, Square,
} from 'lucide-react'
import { runsApi } from '@/api/runs'
import { Button } from '@/components/ui/button'
import { StageBadge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { STAGE_DISPLAY, STEP_DISPLAY } from '@/types/api'
import type { Stage, Step, WorkItem } from '@/types/api'
import { useWsStore } from '@/stores/wsStore'
import { RUNS_QUERY_ROOT, runDetailQueryKey, runStagesQueryKey } from '@/queryKeys/runs'

const WORK_ITEMS_PAGE_SIZE = 50

interface StagePanelProps {
  runId: number
  stage: Stage
}

export function StagePanel({ runId, stage }: StagePanelProps) {
  const [showItems, setShowItems] = useState(false)
  const [workItemsPage, setWorkItemsPage] = useState(0)
  const qc = useQueryClient()
  const display = STAGE_DISPLAY[stage.phase_code as keyof typeof STAGE_DISPLAY]
  const liveProgress = useWsStore((s) => s.runProgress[runId])
  const activeLive = liveProgress?.stage === stage.phase_code ? liveProgress : null

  const { data: steps } = useQuery({
    queryKey: ['run-steps', runId, stage.phase_code],
    queryFn: () => runsApi.getSteps(runId, stage.phase_code),
    enabled: stage.state === 'running' || stage.state === 'completed' || stage.state === 'interrupted',
    refetchInterval: stage.state === 'running' ? 3000 : false,
  })

  const { data: workItems } = useQuery({
    queryKey: ['run-work-items', runId, stage.phase_code, workItemsPage],
    queryFn: () =>
      runsApi.getWorkItems(
        runId,
        stage.phase_code,
        workItemsPage * WORK_ITEMS_PAGE_SIZE,
        WORK_ITEMS_PAGE_SIZE,
      ),
    enabled: showItems,
    refetchInterval: showItems && stage.state === 'running' ? 3000 : false,
  })

  useEffect(() => {
    setWorkItemsPage(0)
    setShowItems(false)
  }, [runId, stage.phase_code])

  useEffect(() => {
    if (!workItems) return
    const t = workItems.total
    if (t <= 0) return
    const maxPage = Math.max(0, Math.ceil(t / WORK_ITEMS_PAGE_SIZE) - 1)
    if (workItemsPage > maxPage) setWorkItemsPage(maxPage)
  }, [workItems, workItemsPage])

  const retryMut = useMutation({
    mutationFn: () => runsApi.retryStage(runId, stage.phase_code),
    onSuccess: () => qc.invalidateQueries({ queryKey: runStagesQueryKey(runId) }),
  })
  const skipMut = useMutation({
    mutationFn: () => runsApi.skipStage(runId, stage.phase_code),
    onSuccess: () => qc.invalidateQueries({ queryKey: runStagesQueryKey(runId) }),
  })
  const cancelMut = useMutation({
    mutationFn: () => runsApi.cancel(runId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: runDetailQueryKey(runId) })
      qc.invalidateQueries({ queryKey: runStagesQueryKey(runId) })
      qc.invalidateQueries({ queryKey: RUNS_QUERY_ROOT })
    },
  })

  const done = activeLive?.items_done ?? stage.items_done ?? 0
  const total = activeLive?.items_total ?? stage.items_total ?? 0
  const pct = total > 0 ? Math.max(0, Math.min(100, Math.round((done / total) * 100))) : 0
  const throughput = activeLive?.throughput
  const eta = activeLive?.eta_seconds

  return (
    <div className="rounded-md border border-[#474747] bg-[#252526]">
      {/* Header */}
      <div className="flex items-center gap-3 p-4 border-b border-[#3c3c3c]">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span className="text-sm font-semibold text-[#cccccc]">
              {display?.name ?? stage.phase_code}
            </span>
            <StageBadge state={stage.state} />
          </div>
          {display?.description && (
            <p className="text-xs text-[#6d6d6d]">{display.description}</p>
          )}
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {stage.state === 'running' && (
            <Button
              size="xs"
              variant="danger"
              onClick={() => cancelMut.mutate()}
              loading={cancelMut.isPending}
            >
              <Square size={11} />
              Stop
            </Button>
          )}
          {(stage.state === 'failed' || stage.state === 'completed' || stage.state === 'interrupted') && (
            <Button
              size="xs"
              variant="secondary"
              onClick={() => retryMut.mutate()}
              loading={retryMut.isPending}
            >
              <RefreshCw size={11} />
              Re-run
            </Button>
          )}
          {(stage.state === 'pending' || stage.state === 'failed' || stage.state === 'interrupted') && (
            <Button
              size="xs"
              variant="ghost"
              onClick={() => skipMut.mutate()}
              loading={skipMut.isPending}
            >
              <SkipForward size={11} />
              Skip
            </Button>
          )}
        </div>
      </div>

      {/* Progress (running stage) */}
      {stage.state === 'running' && (
        <div className="px-4 py-3 border-b border-[#3c3c3c]">
          <div className="flex items-center justify-between mb-2 text-xs text-[#9d9d9d]">
            <span>
              {done.toLocaleString()} / {total.toLocaleString()} work items
            </span>
            <span className="flex items-center gap-3">
              {throughput != null && throughput > 0 && (
                <span>{throughput.toFixed(1)} img/s</span>
              )}
              {eta != null && eta > 0 && (
                <span>ETA {formatEta(eta)}</span>
              )}
            </span>
          </div>
          <Progress value={pct} size="md" color="blue" showLabel />
        </div>
      )}

      {/* Steps grid */}
      {steps && steps.length > 0 && (
        <div className="px-4 py-3 border-b border-[#3c3c3c]">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-[#6d6d6d] mb-2">Steps</div>
          <div className="flex flex-wrap gap-2">
            {steps.map((step) => (
              <StepChip key={step.step_code} step={step} />
            ))}
          </div>
        </div>
      )}

      {/* Error */}
      {stage.state === 'failed' && stage.error_message && (
        <div className="px-4 py-3 border-b border-[#3c3c3c]">
          <div className="flex items-start gap-2 text-xs text-[#f44747]">
            <AlertCircle size={13} className="shrink-0 mt-0.5" />
            <pre className="whitespace-pre-wrap font-mono text-[11px] overflow-auto max-h-24">
              {stage.error_message}
            </pre>
          </div>
        </div>
      )}
      {stage.state === 'interrupted' && (
        <div className="px-4 py-3 border-b border-[#3c3c3c]">
          <div className="flex items-start gap-2 text-xs text-[#cca700]">
            <AlertCircle size={13} className="shrink-0 mt-0.5" />
            <span>This stage was in progress when the server stopped (e.g. restart or crash).</span>
          </div>
        </div>
      )}

      {/* Work items toggle */}
      <button
        className="w-full flex items-center justify-between px-4 py-2.5 text-xs text-[#9d9d9d] hover:text-[#cccccc] hover:bg-[#2d2d30] transition-colors"
        onClick={() => {
          setShowItems((v) => {
            if (!v) setWorkItemsPage(0)
            return !v
          })
        }}
      >
        <span>Work Items {total > 0 && `(${total.toLocaleString()})`}</span>
        {showItems ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
      </button>

      {showItems && workItems && (
        <div className="border-t border-[#3c3c3c]">
          {(workItems.total ?? 0) === 0 && total > 0 && (
            <div className="px-4 py-2 text-xs text-[#cca700] border-b border-[#3c3c3c]">
              No per-file rows yet. The progress bar can advance from queued work before this table
              fills—that is normal. Use Run Log below for live file-by-file output; this list appears
              when per-image status is stored for this run.
            </div>
          )}
          <WorkItemsTable
            items={workItems.items}
            total={workItems.total}
            page={workItemsPage}
            pageSize={WORK_ITEMS_PAGE_SIZE}
            onPageChange={setWorkItemsPage}
          />
        </div>
      )}
    </div>
  )
}

function StepChip({ step }: { step: Step }) {
  const name = STEP_DISPLAY[step.step_code] ?? step.step_name
  const pct = step.items_total > 0 ? Math.round((step.items_done / step.items_total) * 100) : 0

  return (
    <div
      className={clsx(
        'flex items-center gap-1.5 rounded px-2.5 py-1.5 text-xs border min-w-[120px]',
        step.status === 'completed' && 'bg-[#1a3320] border-[#2d6a2d] text-[#89d185]',
        step.status === 'running' && 'bg-[#003f6e] border-[#007acc] text-[#4fc1ff]',
        step.status === 'failed' && 'bg-[#3a1515] border-[#7a2a2a] text-[#f44747]',
        step.status === 'skipped' && 'bg-[#252526] border-[#3c3c3c] text-[#6d6d6d]',
        step.status === 'pending' && 'bg-[#252526] border-[#3c3c3c] text-[#6d6d6d]',
      )}
    >
      <StepIcon status={step.status} />
      <div className="flex-1 min-w-0">
        <div className="truncate">{name}</div>
        {step.status === 'running' && step.items_total > 0 && (
          <Progress value={pct} size="sm" color="blue" className="mt-1" />
        )}
        {step.throughput_rps != null && step.throughput_rps > 0 && (
          <div className="text-[10px] opacity-75">{step.throughput_rps.toFixed(1)}/s</div>
        )}
      </div>
    </div>
  )
}

function StepIcon({ status }: { status: string }) {
  switch (status) {
    case 'completed':
      return <CheckCircle2 size={11} />
    case 'running':
      return <Loader2 size={11} className="animate-spin" />
    case 'failed':
      return <XCircle size={11} />
    case 'pending':
      return <Clock size={11} />
    default:
      return <Circle size={11} />
  }
}

function WorkItemsTable({
  items,
  total,
  page,
  pageSize,
  onPageChange,
}: {
  items: WorkItem[]
  total: number
  page: number
  pageSize: number
  onPageChange: (page: number) => void
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const canPrev = page > 0
  const canNext = (page + 1) * pageSize < total
  const rangeStart = total === 0 ? 0 : page * pageSize + 1
  const rangeEnd = Math.min((page + 1) * pageSize, total)

  return (
    <div>
      <div className="overflow-auto max-h-64">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-[#252526]">
            <tr className="text-[#6d6d6d] border-b border-[#3c3c3c]">
              <th className="text-left px-4 py-2 font-medium">File</th>
              <th className="text-left px-4 py-2 font-medium">Status</th>
              <th className="text-left px-4 py-2 font-medium">Details</th>
              <th className="text-right px-4 py-2 font-medium">Duration</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr
                key={item.image_id}
                className="border-b border-[#3c3c3c] hover:bg-[#2d2d30] transition-colors"
              >
                <td className="px-4 py-1.5 text-[#cccccc] truncate max-w-[300px]">
                  <Link
                    to={`/images/${item.image_id}`}
                    className="hover:text-[#4fc1ff] hover:underline"
                  >
                    {item.filename}
                  </Link>
                </td>
                <td className="px-4 py-1.5">
                  <WorkItemStatus status={item.status} />
                </td>
                <td
                  className="px-4 py-1.5 text-[#9d9d9d] max-w-[240px] truncate text-left"
                  title={
                    [item.error, item.skip_reason, item.skipped_by ? `by ${item.skipped_by}` : null]
                      .filter(Boolean)
                      .join(' · ') || undefined
                  }
                >
                  {item.error ?? item.skip_reason ?? (item.skipped_by ? `skipped by ${item.skipped_by}` : '—')}
                </td>
                <td className="px-4 py-1.5 text-[#9d9d9d] text-right">
                  {item.duration_ms != null ? `${(item.duration_ms / 1000).toFixed(2)}s` : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {total > 0 && (
        <div className="flex items-center justify-between gap-2 px-4 py-2.5 border-t border-[#3c3c3c] bg-[#252526] text-[11px] text-[#9d9d9d]">
          <span className="min-w-0 truncate">
            {rangeStart.toLocaleString()}–{rangeEnd.toLocaleString()} of {total.toLocaleString()}
          </span>
          <div className="flex items-center gap-1 shrink-0">
            <button
              type="button"
              className="inline-flex items-center justify-center rounded p-1 text-[#cccccc] hover:bg-[#3c3c3c] disabled:opacity-40 disabled:pointer-events-none"
              disabled={!canPrev}
              onClick={() => onPageChange(page - 1)}
              aria-label="Previous page"
            >
              <ChevronLeft size={16} strokeWidth={2.25} />
            </button>
            <span className="tabular-nums px-1 min-w-[5.5rem] text-center text-[#cccccc]">
              {page + 1} / {totalPages}
            </span>
            <button
              type="button"
              className="inline-flex items-center justify-center rounded p-1 text-[#cccccc] hover:bg-[#3c3c3c] disabled:opacity-40 disabled:pointer-events-none"
              disabled={!canNext}
              onClick={() => onPageChange(page + 1)}
              aria-label="Next page"
            >
              <ChevronRight size={16} strokeWidth={2.25} />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function WorkItemStatus({ status }: { status: string }) {
  const styles: Record<string, string> = {
    done: 'text-[#89d185]',
    running: 'text-[#4fc1ff]',
    failed: 'text-[#f44747]',
    skipped: 'text-[#6d6d6d]',
    pending: 'text-[#6d6d6d]',
  }
  const labels: Record<string, string> = {
    done: '✓ Done',
    running: '⟳ Running',
    failed: '✗ Failed',
    skipped: '— Skipped',
    pending: '○ Waiting',
  }
  return <span className={clsx('font-medium', styles[status] ?? 'text-[#6d6d6d]')}>{labels[status] ?? status}</span>
}

function formatEta(sec: number): string {
  if (sec < 60) return `${Math.round(sec)}s`
  return `${Math.floor(sec / 60)}m ${Math.round(sec % 60)}s`
}
