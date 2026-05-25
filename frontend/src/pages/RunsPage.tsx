import { useEffect, useRef, useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { runsApi } from '@/api/runs'
import { RunCard } from '@/components/runs/RunCard'
import { Button } from '@/components/ui/button'
import { useWsStore } from '@/stores/wsStore'
import { useUiStore } from '@/stores/uiStore'
import { ChevronLeft, ChevronRight, Inbox, Plus, Square, Zap } from 'lucide-react'
import type { Run } from '@/types/api'
import { FULL_PIPELINE_STAGE_CODES } from '@/constants/pipeline'
import { RUNS_DRIVE_STATUS_KEY, RUNS_QUERY_ROOT } from '@/queryKeys/runs'

type TabFilter = 'active' | 'queue' | 'history'

const HISTORY_PAGE_SIZE = 25

export function RunsPage() {
  const navigate = useNavigate()
  const { openNewRun } = useUiStore()
  const selectedScopePath = useUiStore((s) => s.selectedScopePath)
  const queryClient = useQueryClient()
  const runsVersion = useWsStore((s) => s.runsVersion)
  const driveVersion = useWsStore((s) => s.driveVersion)
  const [tab, setTab] = useState<TabFilter>('active')
  const [historyPage, setHistoryPage] = useState(0)
  const [confirmDrive, setConfirmDrive] = useState(false)
  const stableTotal = useRef(0)

  const driveScope = selectedScopePath?.trim() || undefined

  const driveStatusQuery = useQuery({
    queryKey: RUNS_DRIVE_STATUS_KEY,
    queryFn: () => runsApi.drive.status(),
    refetchInterval: 5000,
  })
  const driving = Boolean(driveStatusQuery.data?.state.enabled)

  const invalidateDrive = () => {
    void queryClient.invalidateQueries({ queryKey: RUNS_DRIVE_STATUS_KEY })
    void queryClient.invalidateQueries({ queryKey: RUNS_QUERY_ROOT })
  }

  useEffect(() => {
    if (driveVersion === 0) return
    invalidateDrive()
  }, [driveVersion, queryClient])

  const startDriveMutation = useMutation({
    mutationFn: runsApi.drive.start,
    onSuccess: () => {
      invalidateDrive()
      setConfirmDrive(false)
      navigate('/dashboard')
    },
  })
  const stopDriveMutation = useMutation({ mutationFn: runsApi.drive.stop, onSuccess: invalidateDrive })

  const onConfirmDrive = () => {
    startDriveMutation.mutate({
      root_path: driveScope,
      target_phases: FULL_PIPELINE_STAGE_CODES,
      generate_captions: true,
    })
  }

  const { data: activeRuns, isLoading: activeLoading } = useQuery({
    queryKey: ['runs', 'active', runsVersion],
    queryFn: () => runsApi.list({ limit: 200, status: 'running,paused,queued,pending' }),
    refetchInterval: 30000,
  })

  const { data: overviewPayload, isLoading: overviewLoading } = useQuery({
    queryKey: ['runs', 'list', runsVersion],
    queryFn: () => runsApi.list({ limit: 120 }),
    refetchInterval: 30000,
  })
  const overview: Run[] = Array.isArray(overviewPayload) ? overviewPayload : []

  const { data: historyPayload, isLoading: historyLoading } = useQuery({
    queryKey: ['runs', 'history', historyPage, runsVersion],
    queryFn: () =>
      runsApi.list({
        limit: HISTORY_PAGE_SIZE,
        offset: historyPage * HISTORY_PAGE_SIZE,
        history: true,
      }),
    enabled: tab === 'history',
    refetchInterval: tab === 'history' ? 5000 : false,
    placeholderData: keepPreviousData,
  })

  const active = (Array.isArray(activeRuns) ? activeRuns : []).filter((r) => r.status === 'running' || r.status === 'paused')
  const queued = (Array.isArray(activeRuns) ? activeRuns : []).filter((r) => r.status === 'queued' || r.status === 'pending')
  const runs: Run[] = overview
  const overviewHistory = runs.filter(
    (r) =>
      r.status === 'completed' ||
      r.status === 'failed' ||
      r.status === 'canceled' ||
      r.status === 'interrupted',
  )

  const historyTotal =
    tab === 'history' && historyPayload && 'total' in historyPayload
      ? historyPayload.total
      : overviewHistory.length

  const historyRuns: Run[] =
    tab === 'history' && historyPayload && 'runs' in historyPayload ? historyPayload.runs : []

  useEffect(() => {
    if (tab !== 'history' || !historyPayload || !('total' in historyPayload)) return
    const t = historyPayload.total
    if (t === stableTotal.current) return
    stableTotal.current = t
    const maxPage = Math.max(0, Math.ceil(t / HISTORY_PAGE_SIZE) - 1)
    if (historyPage > maxPage) setHistoryPage(maxPage)
  }, [tab, historyPayload, historyPage])

  const displayed: Run[] =
    tab === 'active'
      ? [...active, ...queued]
      : tab === 'queue'
        ? queued
        : tab === 'history'
          ? historyRuns
          : []

  const listLoading = tab === 'history' ? historyLoading : (tab === 'active' || tab === 'queue' ? activeLoading : overviewLoading)
  const historyHasPrev = tab === 'history' && historyPage > 0
  const historyHasNext =
    tab === 'history' && historyPayload && 'total' in historyPayload
      ? (historyPage + 1) * HISTORY_PAGE_SIZE < historyPayload.total
      : false

  const rangeStart = tab === 'history' && historyPayload && 'total' in historyPayload && historyPayload.total > 0
    ? historyPage * HISTORY_PAGE_SIZE + 1
    : 0
  const rangeEnd =
    tab === 'history' && historyPayload && 'total' in historyPayload
      ? Math.min((historyPage + 1) * HISTORY_PAGE_SIZE, historyPayload.total)
      : 0

  return (
    <div className="mx-auto w-full max-w-5xl p-6">
      <div className="mb-5 flex items-center justify-between">
        <h1 className="text-lg font-semibold text-[var(--color-text-primary)]">Runs</h1>
        <div className="flex items-center gap-2">
          {driving ? (
            <Button variant="outline" size="sm" onClick={() => stopDriveMutation.mutate()} loading={stopDriveMutation.isPending}>
              <Square size={14} />
              Stop Driving
            </Button>
          ) : (
            <Button variant="secondary" size="sm" onClick={() => setConfirmDrive(true)}>
              <Zap size={14} />
              Drive to Complete
            </Button>
          )}
          <Button variant="primary" size="sm" onClick={() => openNewRun()}>
            <Plus size={14} />
            New Run
          </Button>
        </div>
      </div>

      <div className="mb-5 flex items-center gap-1 border-b border-[var(--color-border-muted)]">
        <TabButton label="Active" count={active.length} active={tab === 'active'} onClick={() => setTab('active')} />
        <TabButton label="Queued" count={queued.length} active={tab === 'queue'} onClick={() => setTab('queue')} />
        <TabButton
          label="History"
          count={historyTotal}
          active={tab === 'history'}
          onClick={() => setTab('history')}
        />
      </div>

      {listLoading && (
        <div className="text-sm text-[var(--color-text-muted)]">Loading…</div>
      )}

      {!listLoading && displayed.length === 0
        && (tab !== 'history' || historyPayload !== undefined) && (
        <EmptyState tab={tab} onNewRun={() => openNewRun()} />
      )}

      {!listLoading && displayed.length > 0 && (
        <div className="space-y-3">
          {displayed.map((run) => (
            <RunCard key={run.id} run={run} />
          ))}
        </div>
      )}

      {tab === 'history' && !listLoading && historyPayload && 'total' in historyPayload && historyPayload.total > 0 && (
        <div className="mt-6 flex items-center justify-between border-t border-[var(--color-border-muted)] pt-4">
          <span className="text-xs text-[var(--color-text-secondary)]">
            {rangeStart}–{rangeEnd} of {historyPayload.total}
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              disabled={!historyHasPrev}
              onClick={() => setHistoryPage((p) => Math.max(0, p - 1))}
              className="text-[var(--color-text-primary)]"
            >
              <ChevronLeft size={16} />
              Previous
            </Button>
            <Button
              variant="ghost"
              size="sm"
              disabled={!historyHasNext}
              onClick={() => setHistoryPage((p) => p + 1)}
              className="text-[var(--color-text-primary)]"
            >
              Next
              <ChevronRight size={16} />
            </Button>
          </div>
        </div>
      )}

      {confirmDrive && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-[min(460px,92vw)] rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)] p-4 text-sm text-[var(--color-text-primary)] shadow-2xl">
            <div className="mb-2 flex items-center gap-2 font-semibold">
              <Zap size={16} className="text-[var(--color-accent-bright)]" />
              Drive to Complete
            </div>
            <p className="mb-2 text-xs text-[var(--color-text-secondary)]">
              Queue the full pipeline (through Bird Species) for every unfinished folder in{' '}
              <span className="font-mono text-[var(--color-text-primary)]">{driveScope ?? 'the whole library'}</span>, and
              keep scheduling the next phase as each run finishes — even if you close this page.
            </p>
            <p className="mb-4 text-[11px] text-[var(--color-text-muted)]">
              Folders already complete or actively running are skipped. You can stop the drive from the Dashboard or here.
            </p>
            <div className="flex justify-end gap-2">
              <Button
                variant="ghost"
                size="sm"
                disabled={startDriveMutation.isPending}
                onClick={() => setConfirmDrive(false)}
              >
                Cancel
              </Button>
              <Button variant="primary" size="sm" loading={startDriveMutation.isPending} onClick={onConfirmDrive}>
                <Zap size={14} />
                Start Driving
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function TabButton({
  label, count, active, onClick,
}: {
  label: string
  count?: number
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`
        -mb-px flex items-center gap-1.5 border-b-2 px-4 py-2 text-sm font-medium transition-colors
        ${active
          ? 'border-[var(--color-accent-bright)] text-[var(--color-text-primary)]'
          : 'border-transparent text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]'
        }
      `}
    >
      {label}
      {typeof count === 'number' && count > 0 && (
        <span className="min-w-[20px] rounded-full bg-[var(--color-bg-elevated)] px-1.5 py-0.5 text-center text-xs text-[var(--color-text-secondary)]">
          {count}
        </span>
      )}
    </button>
  )
}

function EmptyState({ tab, onNewRun }: { tab: TabFilter; onNewRun: () => void }) {
  const messages: Record<TabFilter, string> = {
    active: 'No active runs. Start a new run to begin processing.',
    queue: 'Queue is empty.',
    history: 'No completed runs yet.',
  }
  return (
    <div className="flex flex-col items-center gap-3 py-16 text-center">
      <Inbox size={32} className="text-[var(--color-border)]" />
      <p className="text-sm text-[var(--color-text-muted)]">{messages[tab]}</p>
      {tab === 'active' && (
        <Button variant="primary" size="sm" onClick={onNewRun}>
          <Plus size={14} />
          New Run
        </Button>
      )}
    </div>
  )
}
