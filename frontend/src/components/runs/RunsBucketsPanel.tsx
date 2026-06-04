import { useDeferredValue, useEffect, useMemo, useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Bot,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ListFilter,
  Play,
  RefreshCw,
  Search,
  Square,
  TriangleAlert,
  Zap,
} from 'lucide-react'
import { runsApi } from '@/api/runs'
import { FULL_PIPELINE_STAGE_CODES } from '@/constants/pipeline'
import { RUNS_DRIVE_STATUS_KEY, RUNS_QUERY_ROOT } from '@/queryKeys/runs'
import { useUiStore } from '@/stores/uiStore'
import { useWsStore } from '@/stores/wsStore'
import type { RunFolderBucket, RunFolderBucketPhase, RunsAutoDriveResult, StageCode } from '@/types/api'
import { STAGE_DISPLAY } from '@/types/api'
import { Badge, statusLabel, statusVariant } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

const PAGE_SIZE = 20
const BUCKET_FILTERS = [
  { value: 'all', label: 'All Buckets' },
  { value: 'awaiting_indexing', label: 'Awaiting Discovery' },
  { value: 'awaiting_metadata', label: 'Awaiting Inspection' },
  { value: 'awaiting_scoring', label: 'Awaiting Scoring' },
  { value: 'awaiting_culling', label: 'Awaiting Culling' },
  { value: 'awaiting_keywords', label: 'Awaiting Tagging' },
  { value: 'awaiting_bird_species', label: 'Awaiting Birds' },
  { value: 'blocked', label: 'Blocked' },
  { value: 'in_flight', label: 'In Flight' },
  { value: 'complete', label: 'Complete' },
]

function stageName(code: string | null | undefined) {
  if (!code) return 'None'
  return STAGE_DISPLAY[code as StageCode]?.name ?? code.replace(/_/g, ' ')
}

function bucketLabel(bucket: string) {
  if (bucket.startsWith('awaiting_')) {
    return `Awaiting ${stageName(bucket.replace('awaiting_', ''))}`
  }
  if (bucket === 'in_flight') return 'In Flight'
  if (bucket === 'blocked') return 'Blocked'
  if (bucket === 'complete') return 'Complete'
  return bucket.replace(/_/g, ' ')
}

function bucketVariant(bucket: string) {
  if (bucket === 'complete') return 'success' as const
  if (bucket === 'blocked') return 'danger' as const
  if (bucket === 'in_flight') return 'running' as const
  return 'warning' as const
}

function splitPath(path: string) {
  const parts = path.split(/[\\/]/).filter(Boolean)
  return {
    leaf: parts[parts.length - 1] || path,
    parent: parts.slice(0, Math.max(0, parts.length - 1)).join('/'),
  }
}

function ResultBanner({ result }: { result: RunsAutoDriveResult | null }) {
  if (!result) return null
  const queued = result.scheduled.filter((x) => x.job_id).length
  const planned = result.scheduled.length
  const skipped = result.skipped.length
  const text = result.dry_run
    ? `Plan: ${planned} folder run(s), ${skipped} skipped.`
    : `Queued ${queued} folder run(s), ${skipped} skipped.`
  const ok = result.loop_detected === 0
  return (
    <div
      className={`flex items-start gap-2 rounded border px-3 py-2 text-xs ${
        ok
          ? 'bg-[var(--color-success-bg)] text-[var(--color-success)] border-[var(--color-success-border)]'
          : 'bg-[var(--color-warning-bg)] text-[var(--color-warning)] border-[var(--color-warning-border)]'
      }`}
    >
      {ok ? <CheckCircle2 size={14} className="mt-0.5 shrink-0" /> : <TriangleAlert size={14} className="mt-0.5 shrink-0" />}
      <div className="min-w-0">
        <div>{text}</div>
        {result.loop_detected > 0 && (
          <div className="mt-1 text-[11px]">Loop guard skipped {result.loop_detected} repeated folder plan(s).</div>
        )}
      </div>
    </div>
  )
}

const PHASE_ABBR: Record<string, string> = {
  indexing: 'IDX',
  metadata: 'META',
  scoring: 'SCORE',
  culling: 'CULL',
  keywords: 'TAGS',
  bird_species: 'BIRD',
}

function phaseFillClass(phase: RunFolderBucketPhase): string {
  if (phase.status === 'failed') return 'bg-[var(--color-danger)]'
  if (phase.status === 'running' || phase.status === 'queued') return 'bg-[var(--color-accent-bright)]'
  if (Math.round(phase.percent) >= 100 || phase.status === 'done' || phase.status === 'skipped') {
    return 'bg-[var(--color-success)]'
  }
  return 'bg-[var(--color-text-muted)]'
}

/** Compact, evenly-spaced pipeline strip: one labelled mini-bar per phase. */
function PhaseStrip({ phases }: { phases: RunFolderBucketPhase[] }) {
  return (
    <div className="grid auto-cols-fr grid-flow-col gap-1.5">
      {phases.map((phase) => {
        const pct = Math.round(phase.percent)
        const running = phase.status === 'running' || phase.status === 'queued'
        return (
          <div key={phase.code} className="min-w-0" title={`${stageName(phase.code)}: ${pct}% (${phase.status})`}>
            <div className="truncate text-center text-[9px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
              {PHASE_ABBR[phase.code] ?? stageName(phase.code).slice(0, 4)}
            </div>
            <div className="mt-1 h-1.5 rounded-full bg-[var(--color-bg-elevated)] overflow-hidden">
              <div
                className={`h-full rounded-full transition-[width] duration-300 ${phaseFillClass(phase)} ${running ? 'animate-pulse' : ''}`}
                style={{ width: `${pct <= 0 ? 0 : Math.max(6, Math.min(100, pct))}%` }}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}

function BucketRow({
  item,
  onQueue,
  queueing,
}: {
  item: RunFolderBucket
  onQueue: (path: string) => void
  queueing: boolean
}) {
  const path = splitPath(item.path)
  const plannerPhases =
    item.planner_next_phases && item.planner_next_phases.length > 0
      ? item.planner_next_phases
      : null
  const queuePhases = plannerPhases ?? item.next_phases
  const canQueue = queuePhases.length > 0 && item.bucket !== 'blocked' && item.bucket !== 'in_flight'
  const showPlannerSplit =
    plannerPhases != null &&
    (plannerPhases.length !== item.next_phases.length ||
      plannerPhases.some((code, i) => code !== item.next_phases[i]))

  return (
    <div className="group grid grid-cols-1 gap-4 border-t border-[var(--color-border-muted)] px-4 py-3.5 transition-colors hover:bg-[var(--color-bg-tertiary)]/60 lg:grid-cols-[minmax(0,1.25fr)_minmax(120px,0.55fr)_minmax(0,1.5fr)_7.5rem] lg:items-center lg:gap-3">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="truncate text-sm font-semibold text-[var(--color-text-primary)]">{path.leaf}</span>
          <Badge size="sm" variant={bucketVariant(item.bucket)}>{bucketLabel(item.bucket)}</Badge>
        </div>
        {path.parent ? (
          <div className="mt-1 truncate font-mono text-[11px] text-[var(--color-text-muted)]" title={item.path}>
            {path.parent}
          </div>
        ) : null}
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-[var(--color-text-secondary)]">
          <span>{item.image_count.toLocaleString()} images</span>
          <span className="tabular-nums">{item.overall_percent}% overall</span>
        </div>
      </div>

      <div className="flex flex-col gap-1.5 lg:py-0">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)] lg:hidden">
          Queue stages
        </span>
        {showPlannerSplit ? (
          <>
            <div>
              <span className="text-[9px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
                Would queue
              </span>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {plannerPhases!.map((code) => (
                  <Badge key={`plan-${code}`} size="sm" variant="success">
                    {stageName(code)}
                  </Badge>
                ))}
              </div>
            </div>
            <div>
              <span className="text-[9px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
                Aggregate hint
              </span>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {item.next_phases.map((code) => (
                  <Badge key={`agg-${code}`} size="sm" variant="muted">
                    {stageName(code)}
                  </Badge>
                ))}
              </div>
            </div>
          </>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {queuePhases.length > 0 ? (
              queuePhases.map((code) => (
                <Badge key={code} size="sm" variant="default">
                  {stageName(code)}
                </Badge>
              ))
            ) : (
              <Badge size="sm" variant="muted">{item.bucket === 'complete' ? 'Done' : 'Waiting'}</Badge>
            )}
          </div>
        )}
      </div>

      <div className="min-w-0">
        <span className="mb-2 block text-[10px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)] lg:hidden">
          Phase progress
        </span>
        <PhaseStrip phases={item.phase_statuses} />
      </div>

      <div className="flex items-center justify-start lg:justify-end">
        <Button
          size="sm"
          variant={canQueue ? 'primary' : 'secondary'}
          onClick={() => onQueue(item.path)}
          disabled={!canQueue || queueing}
          loading={queueing}
          className="w-full lg:w-auto"
        >
          <Play size={14} />
          Queue
        </Button>
      </div>
    </div>
  )
}

const DRIVE_STOP_REASON_LABEL: Record<string, string> = {
  complete: 'All outstanding work finished',
  stalled: 'Stopped — schedulable folders could not be queued (loop guard or enqueue failures)',
  blocked: 'Stopped — remaining folders are blocked by missing prerequisites',
  manual: 'Stopped manually',
}

const DRIVE_STOP_REASON_HINT: Record<string, string> = {
  blocked: 'Open the Blocked bucket filter and run prerequisite phases on those folders.',
  stalled: 'Check Preview for loop-guard skips, then retry Drive or queue folders individually.',
}

export function RunsBucketsPanel() {
  const queryClient = useQueryClient()
  const runsVersion = useWsStore((s) => s.runsVersion)
  const driveVersion = useWsStore((s) => s.driveVersion)
  const selectedScopePath = useUiStore((s) => s.selectedScopePath)
  const [page, setPage] = useState(0)
  const [search, setSearch] = useState('')
  const deferredSearch = useDeferredValue(search)
  const [bucket, setBucket] = useState('all')
  const [useSelectedScope, setUseSelectedScope] = useState(false)
  const [includeComplete, setIncludeComplete] = useState(false)
  const [driveLimit, setDriveLimit] = useState(50)
  const [lastPreview, setLastPreview] = useState<RunsAutoDriveResult | null>(null)
  const [queueingPath, setQueueingPath] = useState<string | null>(null)

  const rootPath = useSelectedScope ? selectedScopePath?.trim() || undefined : undefined

  useEffect(() => {
    setPage(0)
  }, [bucket, deferredSearch, rootPath, includeComplete])

  useEffect(() => {
    if (driveVersion === 0) return
    void queryClient.invalidateQueries({ queryKey: RUNS_DRIVE_STATUS_KEY })
    void queryClient.invalidateQueries({ queryKey: RUNS_QUERY_ROOT })
  }, [driveVersion, queryClient])

  const driveStatusQuery = useQuery({
    queryKey: RUNS_DRIVE_STATUS_KEY,
    queryFn: () => runsApi.drive.status(),
    refetchInterval: 5000,
  })
  const drive = driveStatusQuery.data?.state
  const driving = Boolean(drive?.enabled)

  const bucketsQuery = useQuery({
    queryKey: ['runs', 'folder-buckets', page, bucket, deferredSearch, rootPath, includeComplete, runsVersion],
    queryFn: () =>
      runsApi.folderBuckets({
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
        bucket: bucket === 'all' ? undefined : bucket,
        q: deferredSearch.trim() || undefined,
        root_path: rootPath,
        include_complete: includeComplete,
      }),
    placeholderData: keepPreviousData,
    refetchInterval: driving ? 10000 : 30000,
  })

  const invalidateDrive = () => {
    void queryClient.invalidateQueries({ queryKey: RUNS_DRIVE_STATUS_KEY })
    void queryClient.invalidateQueries({ queryKey: RUNS_QUERY_ROOT })
  }

  const startDriveMutation = useMutation({
    mutationFn: runsApi.drive.start,
    onSuccess: invalidateDrive,
  })
  const stopDriveMutation = useMutation({
    mutationFn: runsApi.drive.stop,
    onSuccess: invalidateDrive,
  })

  const previewMutation = useMutation({
    mutationFn: runsApi.autoDrive,
    onSuccess: (result) => setLastPreview(result),
  })

  const queueOneMutation = useMutation({
    mutationFn: runsApi.autoDrive,
    onSuccess: () => invalidateDrive(),
    onSettled: () => setQueueingPath(null),
  })

  const onStartDrive = () => {
    startDriveMutation.mutate({
      root_path: rootPath,
      limit: driveLimit,
      target_phases: FULL_PIPELINE_STAGE_CODES,
      generate_captions: true,
    })
  }

  const onPreview = () => {
    previewMutation.mutate({
      root_path: rootPath,
      limit: driveLimit,
      dry_run: true,
      target_phases: FULL_PIPELINE_STAGE_CODES,
      max_repeats: 2,
      generate_captions: true,
    })
  }

  const total = bucketsQuery.data?.total ?? 0
  const hasPrev = page > 0
  const hasNext = (page + 1) * PAGE_SIZE < total
  const selectedScopeLabel = rootPath ? rootPath : 'Library'
  const bucketCounts = bucketsQuery.data?.bucket_counts ?? {}
  const outstandingTotal = driveStatusQuery.data?.outstanding.total_outstanding
  const lastDriveResult = drive?.last_result ?? null
  const driveHealth = lastDriveResult?.health ?? driveStatusQuery.data?.outstanding.health
  const batchInProgress = Boolean(drive?.batch_in_progress)
  const lastBatchError = drive?.last_batch_error ?? driveStatusQuery.data?.outstanding.last_batch_error
  const visibleRange = useMemo(() => {
    if (total === 0) return '0 of 0'
    const start = page * PAGE_SIZE + 1
    const end = Math.min((page + 1) * PAGE_SIZE, total)
    return `${start}-${end} of ${total}`
  }, [page, total])

  const onQueueOne = (path: string) => {
    setQueueingPath(path)
    queueOneMutation.mutate({
      folder_paths: [path],
      limit: 1,
      dry_run: false,
      target_phases: FULL_PIPELINE_STAGE_CODES,
      max_repeats: 2,
      generate_captions: true,
    })
  }

  return (
    <div className="space-y-5">
      <section
        className={`rounded-lg border bg-[var(--color-bg-secondary)] p-4 transition-colors ${
          driving
            ? 'border-[var(--color-accent)] shadow-[inset_3px_0_0_0_var(--color-accent)]'
            : 'border-[var(--color-border-muted)]'
        }`}
      >
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <Bot size={18} className="shrink-0 text-[var(--color-accent-bright)]" aria-hidden />
              <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">Drive to Complete</h2>
              {driving && <Badge size="sm" variant="running" dot>Driving</Badge>}
            </div>
            <p className="mt-2 text-xs text-[var(--color-text-secondary)]">
              Scope:{' '}
              <span className="font-mono text-[var(--color-text-primary)]" title={rootPath}>
                {selectedScopeLabel}
              </span>
              {typeof outstandingTotal === 'number' && (
                <span className="text-[var(--color-text-muted)]"> · {outstandingTotal.toLocaleString()} folder(s) outstanding</span>
              )}
            </p>
            <p className="mt-2 max-w-2xl text-[11px] leading-relaxed text-[var(--color-text-muted)]">
              Runs the full pipeline through Bird Species on unfinished folders and schedules the next phase as each run
              finishes — continues in the background if you leave this page.
            </p>
          </div>

          <div
            className="flex shrink-0 flex-wrap items-end gap-2 rounded-md border border-[var(--color-border-muted)] bg-[var(--color-bg-primary)] p-2.5"
            role="group"
            aria-label="Drive controls"
          >
            <label className="flex flex-col gap-1">
              <span className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">Batch</span>
              <input
                type="number"
                min={1}
                max={500}
                value={driveLimit}
                onChange={(e) => setDriveLimit(Number(e.target.value))}
                disabled={driving}
                aria-label="Folders per drive batch"
                className="h-8 w-[4.5rem] rounded border border-[var(--color-border-muted)] bg-[var(--color-bg-secondary)] px-2 text-xs tabular-nums text-[var(--color-text-primary)] outline-none focus:border-[var(--color-accent)] disabled:opacity-50"
              />
            </label>

            <Button size="sm" variant="ghost" onClick={onPreview} loading={previewMutation.isPending} disabled={driving}>
              <ListFilter size={14} />
              Preview
            </Button>
            {driving ? (
              <Button size="sm" variant="outline" onClick={() => stopDriveMutation.mutate()} loading={stopDriveMutation.isPending}>
                <Square size={14} />
                Stop
              </Button>
            ) : (
              <Button size="sm" variant="primary" onClick={onStartDrive} loading={startDriveMutation.isPending}>
                <Zap size={14} />
                Start drive
              </Button>
            )}
          </div>
        </div>

        {(driving || lastDriveResult || drive?.stop_reason) && (
          <div className="mt-4 space-y-2">
            <div className="flex flex-wrap items-center gap-2 text-[11px] text-[var(--color-text-secondary)]">
            {driving && batchInProgress && !lastDriveResult && (
              <Badge size="sm" variant="running" dot>
                Scanning folders…
              </Badge>
            )}
            {driving && lastDriveResult && (
              <>
                <Badge size="sm" variant="running">
                  Last tick: queued {lastDriveResult.scheduled}, skipped {lastDriveResult.skipped}
                </Badge>
                {lastDriveResult.last_tick_reason && (
                  <Badge size="sm" variant="muted">
                    {lastDriveResult.last_tick_reason.replace(/_/g, ' ')}
                  </Badge>
                )}
                {lastDriveResult.loop_detected > 0 && (
                  <Badge size="sm" variant="warning">
                    Loop guard: {lastDriveResult.loop_detected} skipped
                  </Badge>
                )}
              </>
            )}
            {driving && !batchInProgress && !lastDriveResult && (
              <Badge size="sm" variant="muted">
                Waiting for first batch…
              </Badge>
            )}
            {!driving && drive?.stop_reason && (
              <Badge size="sm" variant={drive.stop_reason === 'complete' ? 'success' : 'warning'}>
                {DRIVE_STOP_REASON_LABEL[drive.stop_reason] ?? drive.stop_reason}
              </Badge>
            )}
            </div>
            {driveHealth && (
              <p className="text-[11px] text-[var(--color-text-muted)]">
                In flight {driveHealth.in_flight_folders.toLocaleString()} · schedulable{' '}
                {driveHealth.schedulable_folders.toLocaleString()} · blocked{' '}
                {driveHealth.blocked_folders.toLocaleString()}
                {lastDriveResult?.last_tick_reason === 'waiting_in_flight' && (
                  <span> · waiting for active runs to finish before next batch</span>
                )}
                {lastDriveResult?.last_tick_reason === 'no_enqueue_progress' && (
                  <span> · candidates found but none could be queued (see Logs)</span>
                )}
              </p>
            )}
            {lastBatchError && (
              <p className="text-[11px] text-[var(--color-error,#f44747)]">
                Last batch error ({lastBatchError.type}): {lastBatchError.message}
              </p>
            )}
            {driving && (
              <p className="text-[11px] text-[var(--color-text-muted)]">
                Activity is logged to webui.log — open the Logs tab and filter for{' '}
                <span className="font-mono text-[var(--color-text-secondary)]">runs_autodrive</span>.
              </p>
            )}
            {!driving && drive?.stop_reason && DRIVE_STOP_REASON_HINT[drive.stop_reason] && (
              <p className="text-[11px] text-[var(--color-text-secondary)]">
                {DRIVE_STOP_REASON_HINT[drive.stop_reason]}
              </p>
            )}
          </div>
        )}

        {lastPreview && (
          <div className="mt-4">
            <ResultBanner result={lastPreview} />
          </div>
        )}
      </section>

      <section className="overflow-hidden rounded-lg border border-[var(--color-border-muted)] bg-[var(--color-bg-secondary)]">
        <div className="flex flex-col gap-3 border-b border-[var(--color-border-muted)] p-3 sm:p-4">
          <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
            <div className="relative min-w-0 flex-1 xl:max-w-md">
              <Search size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Filter by folder name or path…"
                aria-label="Filter folders"
                className="h-9 w-full rounded-md border border-[var(--color-border-muted)] bg-[var(--color-bg-primary)] pl-8 pr-3 text-sm text-[var(--color-text-primary)] outline-none focus:border-[var(--color-accent)] focus:ring-1 focus:ring-[var(--color-accent)]/30"
              />
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={bucket}
                onChange={(e) => setBucket(e.target.value)}
                aria-label="Bucket filter"
                className="h-9 min-w-[9rem] rounded-md border border-[var(--color-border-muted)] bg-[var(--color-bg-primary)] px-2.5 text-xs text-[var(--color-text-primary)] outline-none focus:border-[var(--color-accent)]"
              >
                {BUCKET_FILTERS.map((f) => (
                  <option key={f.value} value={f.value}>{f.label}</option>
                ))}
              </select>
              <label className="flex h-9 cursor-pointer items-center gap-2 rounded-md border border-[var(--color-border-muted)] bg-[var(--color-bg-primary)] px-2.5 text-xs text-[var(--color-text-secondary)] hover:border-[var(--color-border)]">
                <input
                  type="checkbox"
                  className="accent-[var(--color-accent)]"
                  checked={includeComplete}
                  onChange={(e) => setIncludeComplete(e.target.checked)}
                />
                Complete
              </label>
              <label
                className={`flex h-9 items-center gap-2 rounded-md border px-2.5 text-xs ${
                  !selectedScopePath
                    ? 'cursor-not-allowed border-[var(--color-border-muted)] text-[var(--color-text-muted)] opacity-50'
                    : 'cursor-pointer border-[var(--color-border-muted)] bg-[var(--color-bg-primary)] text-[var(--color-text-secondary)] hover:border-[var(--color-border)]'
                }`}
              >
                <input
                  type="checkbox"
                  className="accent-[var(--color-accent)]"
                  checked={useSelectedScope}
                  onChange={(e) => setUseSelectedScope(e.target.checked)}
                  disabled={!selectedScopePath}
                />
                Selected scope
              </label>
              <Button size="sm" variant="ghost" onClick={() => bucketsQuery.refetch()} loading={bucketsQuery.isFetching}>
                <RefreshCw size={14} />
                Refresh
              </Button>
            </div>
          </div>

          {Object.keys(bucketCounts).length > 0 && (
            <div className="flex flex-wrap items-center gap-2" role="list" aria-label="Bucket summary">
              <span className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">Summary</span>
              {Object.entries(bucketCounts).map(([name, count]) => {
                const active = bucket === name
                return (
                  <button
                    key={name}
                    type="button"
                    onClick={() => setBucket(name)}
                    className={`rounded-full transition-opacity ${active ? 'ring-1 ring-[var(--color-accent)] ring-offset-1 ring-offset-[var(--color-bg-secondary)]' : 'opacity-90 hover:opacity-100'}`}
                    aria-pressed={active}
                    aria-label={`Filter to ${bucketLabel(name)}, ${count} folders`}
                  >
                    <Badge size="sm" variant={bucketVariant(name)}>
                      {bucketLabel(name)}: {count.toLocaleString()}
                    </Badge>
                  </button>
                )
              })}
            </div>
          )}
          {Object.keys(bucketCounts).length === 0 && !bucketsQuery.isLoading && (
            <span className="text-xs text-[var(--color-text-muted)]">No outstanding folders in this view.</span>
          )}
        </div>

        <div className="sticky top-0 z-[1] hidden border-b border-[var(--color-border-muted)] bg-[var(--color-bg-tertiary)] px-4 py-2 text-[10px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)] lg:grid lg:grid-cols-[minmax(0,1.25fr)_minmax(120px,0.55fr)_minmax(0,1.5fr)_7.5rem] lg:gap-3">
          <span>Folder</span>
          <span>Next chain</span>
          <span>Phase progress</span>
          <span className="text-right">Action</span>
        </div>

        {bucketsQuery.isLoading && (
          <div className="border-t border-[var(--color-border-muted)] px-3 py-10 text-center text-sm text-[var(--color-text-muted)]">
            Loading buckets...
          </div>
        )}

        {bucketsQuery.isError && (
          <div className="border-t border-[var(--color-border-muted)] px-3 py-10 text-center text-sm text-[var(--color-warning)]">
            Bucket API is unavailable. Restart the WebUI so the new Runs endpoints are loaded.
          </div>
        )}

        {!bucketsQuery.isLoading && !bucketsQuery.isError && bucketsQuery.data?.items.length === 0 && (
          <div className="border-t border-[var(--color-border-muted)] px-3 py-10 text-center text-sm text-[var(--color-text-muted)]">
            No folders match this bucket filter.
          </div>
        )}

        {!bucketsQuery.isLoading && !bucketsQuery.isError && bucketsQuery.data?.items.map((item) => (
          <BucketRow
            key={item.path}
            item={item}
            onQueue={onQueueOne}
            queueing={queueingPath === item.path && queueOneMutation.isPending}
          />
        ))}

        {total > 0 && (
          <div className="flex items-center justify-between border-t border-[var(--color-border-muted)] px-3 py-3">
            <span className="text-xs text-[var(--color-text-secondary)]">{visibleRange}</span>
            <div className="flex items-center gap-2">
              <Button size="sm" variant="ghost" disabled={!hasPrev} onClick={() => setPage((p) => Math.max(0, p - 1))}>
                <ChevronLeft size={16} />
                Previous
              </Button>
              <Button size="sm" variant="ghost" disabled={!hasNext} onClick={() => setPage((p) => p + 1)}>
                Next
                <ChevronRight size={16} />
              </Button>
            </div>
          </div>
        )}
      </section>

      {lastPreview?.skipped && lastPreview.skipped.length > 0 && (
        <section className="rounded-lg border border-[var(--color-border-muted)] bg-[var(--color-bg-secondary)] p-3">
          <div className="mb-2 text-xs font-semibold text-[var(--color-text-primary)]">Skipped Plans (preview)</div>
          <div className="max-h-44 overflow-auto space-y-1">
            {lastPreview.skipped.slice(0, 20).map((row, idx) => (
              <div key={`${row.folder_path}-${idx}`} className="flex items-center gap-2 text-[11px] text-[var(--color-text-secondary)]">
                <Badge size="sm" variant={statusVariant(row.reason)}>{statusLabel(row.reason)}</Badge>
                <span className="truncate font-mono">{row.folder_path}</span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
