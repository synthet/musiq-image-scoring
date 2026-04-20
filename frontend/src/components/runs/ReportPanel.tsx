import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  ChevronDown, ChevronUp, ChevronLeft, ChevronRight,
  CheckCircle2, XCircle, SkipForward, FileText,
} from 'lucide-react'
import { runsApi } from '@/api/runs'
import { STAGE_DISPLAY } from '@/types/api'
import type { JobExecutionReport, PhaseExecutionReport, ImageAction } from '@/types/api'
import { imageInspectorPath } from '@/utils/routes'

const PAGE_SIZE = 20

interface ReportPanelProps {
  runId: number
  reportSupported?: boolean
}

function PhaseCard({ code, phase }: { code: string; phase: PhaseExecutionReport }) {
  const display = STAGE_DISPLAY[code as keyof typeof STAGE_DISPLAY]
  const total = phase.images_processed + phase.images_skipped + phase.images_failed
  const pctProcessed = total > 0 ? (phase.images_processed / total) * 100 : 0
  const pctSkipped = total > 0 ? (phase.images_skipped / total) * 100 : 0
  const pctFailed = total > 0 ? (phase.images_failed / total) * 100 : 0

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="flex items-center justify-between mb-2">
        <h4 className="font-medium text-sm">{display?.name ?? code}</h4>
        <span className="text-xs text-muted-foreground">
          {phase.duration_seconds.toFixed(1)}s
        </span>
      </div>

      {/* Stacked bar */}
      <div className="flex h-2 rounded-full overflow-hidden bg-muted mb-3">
        {pctProcessed > 0 && (
          <div className="bg-emerald-500" style={{ width: `${pctProcessed}%` }} />
        )}
        {pctSkipped > 0 && (
          <div className="bg-amber-500" style={{ width: `${pctSkipped}%` }} />
        )}
        {pctFailed > 0 && (
          <div className="bg-red-500" style={{ width: `${pctFailed}%` }} />
        )}
      </div>

      <div className="grid grid-cols-3 gap-2 text-xs">
        <div className="flex items-center gap-1">
          <CheckCircle2 className="h-3 w-3 text-emerald-500" />
          <span>{phase.images_processed} processed</span>
        </div>
        <div className="flex items-center gap-1">
          <SkipForward className="h-3 w-3 text-amber-500" />
          <span>{phase.images_skipped} skipped</span>
        </div>
        <div className="flex items-center gap-1">
          <XCircle className="h-3 w-3 text-red-500" />
          <span>{phase.images_failed} failed</span>
        </div>
      </div>

      {phase.incomplete_fields_breakdown && Object.keys(phase.incomplete_fields_breakdown).length > 0 && (
        <div className="mt-3 pt-2 border-t border-border">
          <p className="text-xs font-medium text-muted-foreground mb-1">Incomplete fields found:</p>
          <div className="flex flex-wrap gap-1">
            {Object.entries(phase.incomplete_fields_breakdown)
              .sort(([, a], [, b]) => b - a)
              .map(([field, count]) => (
                <span
                  key={field}
                  className="inline-flex items-center px-1.5 py-0.5 rounded text-xs bg-muted text-muted-foreground"
                >
                  {field}: {count}
                </span>
              ))}
          </div>
        </div>
      )}
    </div>
  )
}

function ActionBadge({ action }: { action: string }) {
  const styles: Record<string, string> = {
    processed: 'bg-emerald-500/10 text-emerald-500',
    skipped: 'bg-amber-500/10 text-amber-500',
    failed: 'bg-red-500/10 text-red-500',
    unchanged: 'bg-muted text-muted-foreground',
  }
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${styles[action] ?? styles.unchanged}`}>
      {action}
    </span>
  )
}

function ImageActionsTable({ runId, report }: { runId: number; report: JobExecutionReport }) {
  const [expanded, setExpanded] = useState(false)
  const [page, setPage] = useState(0)
  const [filterAction, setFilterAction] = useState<string | undefined>(undefined)
  const [filterPhase, setFilterPhase] = useState<string | undefined>(undefined)

  const { data } = useQuery({
    queryKey: ['run-report-images', runId, filterPhase, filterAction, page],
    queryFn: () =>
      runsApi.getReportImages(runId, {
        phase_code: filterPhase,
        action: filterAction,
        offset: page * PAGE_SIZE,
        limit: PAGE_SIZE,
      }),
    enabled: expanded,
  })

  const phaseCodes = Object.keys(report.phases)
  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0

  return (
    <div className="rounded-lg border border-border bg-card">
      <button
        className="w-full flex items-center justify-between p-3 text-sm font-medium hover:bg-muted/50 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <span>Per-image action log</span>
        {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
      </button>

      {expanded && (
        <div className="px-3 pb-3 space-y-2">
          {/* Filters */}
          <div className="flex gap-2 text-xs">
            <select
              className="bg-muted rounded px-2 py-1 text-xs"
              value={filterPhase ?? ''}
              onChange={(e) => { setFilterPhase(e.target.value || undefined); setPage(0) }}
            >
              <option value="">All phases</option>
              {phaseCodes.map((c) => (
                <option key={c} value={c}>{STAGE_DISPLAY[c as keyof typeof STAGE_DISPLAY]?.name ?? c}</option>
              ))}
            </select>
            <select
              className="bg-muted rounded px-2 py-1 text-xs"
              value={filterAction ?? ''}
              onChange={(e) => { setFilterAction(e.target.value || undefined); setPage(0) }}
            >
              <option value="">All actions</option>
              <option value="processed">Processed</option>
              <option value="skipped">Skipped</option>
              <option value="failed">Failed</option>
              <option value="unchanged">Unchanged</option>
            </select>
            {data && (
              <span className="ml-auto text-muted-foreground self-center">{data.total} items</span>
            )}
          </div>

          {/* Table */}
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border text-muted-foreground">
                  <th className="text-left py-1.5 px-2">Image</th>
                  <th className="text-left py-1.5 px-2">Phase</th>
                  <th className="text-left py-1.5 px-2">Action</th>
                  <th className="text-left py-1.5 px-2">Reason</th>
                  <th className="text-right py-1.5 px-2">Score Before</th>
                  <th className="text-right py-1.5 px-2">Score After</th>
                </tr>
              </thead>
              <tbody>
                {(data?.items ?? []).map((item: ImageAction) => {
                  const scoreBefore = item.before_snapshot?.score
                  const scoreAfter = item.after_snapshot?.score
                  return (
                    <tr key={item.id} className="border-b border-border/50 hover:bg-muted/30">
                      <td className="py-1.5 px-2 max-w-[200px] truncate" title={item.file_path ?? ''}>
                        <Link
                          to={imageInspectorPath(item.image_id)}
                          className="hover:text-primary hover:underline"
                        >
                          {item.file_path ? item.file_path.split(/[/\\]/).pop() : `#${item.image_id}`}
                        </Link>
                      </td>
                      <td className="py-1.5 px-2">
                        {STAGE_DISPLAY[item.phase_code as keyof typeof STAGE_DISPLAY]?.name ?? item.phase_code}
                      </td>
                      <td className="py-1.5 px-2">
                        <ActionBadge action={item.action} />
                      </td>
                      <td className="py-1.5 px-2 max-w-[250px] truncate text-muted-foreground" title={item.reason ?? ''}>
                        {item.reason || '—'}
                      </td>
                      <td className="py-1.5 px-2 text-right tabular-nums">
                        {scoreBefore != null ? Number(scoreBefore).toFixed(3) : '—'}
                      </td>
                      <td className="py-1.5 px-2 text-right tabular-nums">
                        {scoreAfter != null ? Number(scoreAfter).toFixed(3) : '—'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between text-xs text-muted-foreground pt-1">
              <button
                disabled={page === 0}
                onClick={() => setPage(page - 1)}
                className="flex items-center gap-1 disabled:opacity-40"
              >
                <ChevronLeft className="h-3 w-3" /> Prev
              </button>
              <span>Page {page + 1} of {totalPages}</span>
              <button
                disabled={page >= totalPages - 1}
                onClick={() => setPage(page + 1)}
                className="flex items-center gap-1 disabled:opacity-40"
              >
                Next <ChevronRight className="h-3 w-3" />
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function ReportPanel({ runId, reportSupported = true }: ReportPanelProps) {
  const { data, isLoading } = useQuery({
    queryKey: ['run-report', runId],
    queryFn: () => runsApi.getReport(runId),
    enabled: reportSupported,
    retry: false,
  })

  if (!reportSupported) {
    return (
      <div className="rounded-md border border-border bg-card/40 p-3 text-xs text-muted-foreground">
        <span className="inline-flex items-center rounded px-1.5 py-0.5 bg-muted mr-2">
          Report unavailable
        </span>
        This run type does not produce an execution report.
      </div>
    )
  }
  if (isLoading) return null
  if (!data?.available || !data.report) {
    return (
      <div className="rounded-md border border-border bg-card/40 p-3 text-xs text-muted-foreground">
        <span className="inline-flex items-center rounded px-1.5 py-0.5 bg-muted mr-2">
          Report unavailable
        </span>
        {data?.message ?? 'Execution report is not available for this run.'}
      </div>
    )
  }

  const report = data.report

  const phases = Object.entries(report.phases ?? {})

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <FileText className="h-4 w-4 text-muted-foreground" />
        <h3 className="text-sm font-semibold">Execution Report</h3>
        {report.run_mode && (
          <span className="text-xs bg-muted text-muted-foreground px-1.5 py-0.5 rounded">
            {report.run_mode}
          </span>
        )}
      </div>

      {/* Phase summary cards */}
      <div className="grid gap-3 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
        {phases.map(([code, phase]) => (
          <PhaseCard key={code} code={code} phase={phase} />
        ))}
      </div>

      {/* Before/After aggregate */}
      {report.aggregate_before && report.aggregate_after && (
        <div className="rounded-lg border border-border bg-card p-3">
          <p className="text-xs font-medium text-muted-foreground mb-2">Score Impact</p>
          <div className="grid grid-cols-3 gap-4 text-sm tabular-nums">
            <div>
              <span className="text-xs text-muted-foreground">Before</span>
              <p>{report.aggregate_before.score_mean.toFixed(3)}</p>
            </div>
            <div>
              <span className="text-xs text-muted-foreground">After</span>
              <p>{report.aggregate_after.score_mean.toFixed(3)}</p>
            </div>
            <div>
              <span className="text-xs text-muted-foreground">Incomplete</span>
              <p>
                {report.aggregate_before.incomplete_count} &rarr; {report.aggregate_after.incomplete_count}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Per-image drill-down */}
      <ImageActionsTable runId={runId} report={report} />
    </div>
  )
}
