import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Bot,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ListFilter,
  Pause,
  Play,
  RefreshCw,
  Search,
  TriangleAlert,
} from 'lucide-react'
import { runsApi } from '@/api/runs'
import { FULL_PIPELINE_STAGE_CODES } from '@/constants/pipeline'
import { RUNS_QUERY_ROOT } from '@/queryKeys/runs'
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

function PhaseProgress({ phase }: { phase: RunFolderBucketPhase }) {
  return (
    <div className="min-w-[92px]">
      <div className="flex items-center justify-between gap-2 text-[10px]">
        <span className="truncate text-[var(--color-text-secondary)]">{stageName(phase.code)}</span>
        <span className="tabular-nums text-[var(--color-text-muted)]">{Math.round(phase.percent)}%</span>
      </div>
      <div className="mt-1 h-1.5 rounded-full bg-[var(--color-bg-elevated)] overflow-hidden">
        <div
          className={`h-full rounded-full ${
            phase.status === 'failed'
              ? 'bg-[var(--color-danger)]'
              : phase.status === 'running' || phase.status === 'queued'
                ? 'bg-[var(--color-accent-bright)]'
                : 'bg-[var(--color-success)]'
          }`}
          style={{ width: `${Math.max(0, Math.min(100, phase.percent))}%` }}
        />
      </div>
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
  const canQueue = item.next_phases.length > 0 && item.bucket !== 'blocked' && item.bucket !== 'in_flight'

  return (
    <div className="grid grid-cols-1 gap-3 border-t border-[var(--color-border-muted)] px-3 py-3 lg:grid-cols-[minmax(0,1.4fr)_150px_minmax(240px,1fr)_150px] lg:items-center">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-medium text-[var(--color-text-primary)]">{path.leaf}</span>
          <Badge size="sm" variant={bucketVariant(item.bucket)}>{bucketLabel(item.bucket)}</Badge>
        </div>
        <div className="mt-1 truncate text-[11px] text-[var(--color-text-muted)]">{path.parent}</div>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-[var(--color-text-secondary)]">
          <span>{item.image_count} images</span>
          <span>{item.overall_percent}% overall</span>
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {item.next_phases.length > 0 ? (
          item.next_phases.map((code) => (
            <Badge key={code} size="sm" variant="info">
              {stageName(code)}
            </Badge>
          ))
        ) : (
          <Badge size="sm" variant="muted">{item.bucket === 'complete' ? 'Done' : 'Waiting'}</Badge>
        )}
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {item.phase_statuses.map((phase) => (
          <PhaseProgress key={phase.code} phase={phase} />
        ))}
      </div>

      <div className="flex items-center justify-start gap-2 lg:justify-end">
        <Button
          size="sm"
          variant="primary"
          onClick={() => onQueue(item.path)}
          disabled={!canQueue || queueing}
          loading={queueing}
        >
          <Play size={14} />
          Queue
        </Button>
      </div>
    </div>
  )
}

export function RunsBucketsPanel() {
  const queryClient = useQueryClient()
  const runsVersion = useWsStore((s) => s.runsVersion)
  const selectedScopePath = useUiStore((s) => s.selectedScopePath)
  const [page, setPage] = useState(0)
  const [search, setSearch] = useState('')
  const deferredSearch = useDeferredValue(search)
  const [bucket, setBucket] = useState('all')
  const [useSelectedScope, setUseSelectedScope] = useState(false)
  const [includeComplete, setIncludeComplete] = useState(false)
  const [driveLimit, setDriveLimit] = useState(50)
  const [autoDrive, setAutoDrive] = useState(false)
  const [lastResult, setLastResult] = useState<RunsAutoDriveResult | null>(null)
  const [queueingPath, setQueueingPath] = useState<string | null>(null)
  const drivePendingRef = useRef(false)

  const rootPath = useSelectedScope ? selectedScopePath?.trim() || undefined : undefined

  useEffect(() => {
    setPage(0)
  }, [bucket, deferredSearch, rootPath, includeComplete])

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
    refetchInterval: autoDrive ? 15000 : 30000,
  })

  const driveMutation = useMutation({
    mutationFn: runsApi.autoDrive,
    onSuccess: (result) => {
      setLastResult(result)
      void queryClient.invalidateQueries({ queryKey: RUNS_QUERY_ROOT })
      if (result.total_outstanding === 0 || (result.loop_detected > 0 && result.scheduled.length === 0)) {
        setAutoDrive(false)
      }
    },
  })

  const queueOneMutation = useMutation({
    mutationFn: runsApi.autoDrive,
    onSuccess: (result) => {
      setLastResult(result)
      void queryClient.invalidateQueries({ queryKey: RUNS_QUERY_ROOT })
    },
    onSettled: () => setQueueingPath(null),
  })

  useEffect(() => {
    drivePendingRef.current = driveMutation.isPending
  }, [driveMutation.isPending])

  const driveMutate = driveMutation.mutate
  const runDrive = useCallback(
    (dryRun: boolean) => {
      driveMutate({
        root_path: rootPath,
        limit: driveLimit,
        dry_run: dryRun,
        target_phases: FULL_PIPELINE_STAGE_CODES,
        max_repeats: 2,
        generate_captions: true,
      })
    },
    [driveLimit, driveMutate, rootPath],
  )

  useEffect(() => {
    if (!autoDrive) return
    const tick = () => {
      if (!drivePendingRef.current) runDrive(false)
    }
    tick()
    const timer = window.setInterval(tick, 30000)
    return () => window.clearInterval(timer)
  }, [autoDrive, runDrive])

  const total = bucketsQuery.data?.total ?? 0
  const hasPrev = page > 0
  const hasNext = (page + 1) * PAGE_SIZE < total
  const selectedScopeLabel = rootPath ? rootPath : 'Library'
  const bucketCounts = bucketsQuery.data?.bucket_counts ?? {}
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
      <section className="rounded-lg border border-[var(--color-border-muted)] bg-[var(--color-bg-secondary)] p-4">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Bot size={18} className="text-[var(--color-accent-bright)]" />
              <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">Auto Queue</h2>
              {autoDrive && <Badge size="sm" variant="running" dot>Driving</Badge>}
            </div>
            <div className="mt-1 text-xs text-[var(--color-text-secondary)]">
              Scope: <span className="font-mono text-[var(--color-text-primary)]">{selectedScopeLabel}</span>
            </div>
          </div>

          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-[10px] font-bold uppercase text-[var(--color-text-muted)]">Batch</span>
              <input
                type="number"
                min={1}
                max={500}
                value={driveLimit}
                onChange={(e) => setDriveLimit(Number(e.target.value))}
                className="h-8 w-20 rounded border border-[var(--color-border-muted)] bg-[var(--color-bg-primary)] px-2 text-xs text-[var(--color-text-primary)]"
              />
            </label>

            <Button size="sm" variant="secondary" onClick={() => runDrive(true)} loading={driveMutation.isPending && lastResult?.dry_run}>
              <ListFilter size={14} />
              Preview
            </Button>
            <Button size="sm" variant={autoDrive ? 'outline' : 'primary'} onClick={() => setAutoDrive((v) => !v)}>
              {autoDrive ? <Pause size={14} /> : <Play size={14} />}
              {autoDrive ? 'Pause' : 'Auto Drive'}
            </Button>
          </div>
        </div>
        <div className="mt-4">
          <ResultBanner result={lastResult} />
        </div>
      </section>

      <section className="rounded-lg border border-[var(--color-border-muted)] bg-[var(--color-bg-secondary)]">
        <div className="flex flex-col gap-3 border-b border-[var(--color-border-muted)] p-3">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="relative max-w-xl flex-1">
              <Search size={14} className="absolute left-2.5 top-2.5 text-[var(--color-text-muted)]" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Filter folders"
                className="h-9 w-full rounded border border-[var(--color-border-muted)] bg-[var(--color-bg-primary)] pl-8 pr-3 text-sm text-[var(--color-text-primary)] outline-none focus:border-[var(--color-accent)]"
              />
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={bucket}
                onChange={(e) => setBucket(e.target.value)}
                className="h-9 rounded border border-[var(--color-border-muted)] bg-[var(--color-bg-primary)] px-2 text-xs text-[var(--color-text-primary)]"
              >
                {BUCKET_FILTERS.map((f) => (
                  <option key={f.value} value={f.value}>{f.label}</option>
                ))}
              </select>
              <label className="flex h-9 items-center gap-2 rounded border border-[var(--color-border-muted)] px-2 text-xs text-[var(--color-text-secondary)]">
                <input
                  type="checkbox"
                  checked={includeComplete}
                  onChange={(e) => setIncludeComplete(e.target.checked)}
                />
                Complete
              </label>
              <label className="flex h-9 items-center gap-2 rounded border border-[var(--color-border-muted)] px-2 text-xs text-[var(--color-text-secondary)]">
                <input
                  type="checkbox"
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

          <div className="flex flex-wrap gap-2">
            {Object.entries(bucketCounts).map(([name, count]) => (
              <Badge key={name} size="sm" variant={bucketVariant(name)}>
                {bucketLabel(name)}: {count}
              </Badge>
            ))}
            {Object.keys(bucketCounts).length === 0 && (
              <span className="text-xs text-[var(--color-text-muted)]">No outstanding folders in this filter.</span>
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 px-3 py-2 text-[11px] font-semibold uppercase text-[var(--color-text-muted)] lg:grid-cols-[minmax(0,1.4fr)_150px_minmax(240px,1fr)_150px]">
          <span>Folder</span>
          <span>Next Chain</span>
          <span>Phase Progress</span>
          <span className="lg:text-right">Action</span>
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

      {lastResult?.skipped && lastResult.skipped.length > 0 && (
        <section className="rounded-lg border border-[var(--color-border-muted)] bg-[var(--color-bg-secondary)] p-3">
          <div className="mb-2 text-xs font-semibold text-[var(--color-text-primary)]">Skipped Plans</div>
          <div className="max-h-44 overflow-auto space-y-1">
            {lastResult.skipped.slice(0, 20).map((row, idx) => (
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
