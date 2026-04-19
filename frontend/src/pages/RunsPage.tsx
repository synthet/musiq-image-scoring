import { useEffect, useRef, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { runsApi } from '@/api/runs'
import { RunCard } from '@/components/runs/RunCard'
import { Button } from '@/components/ui/button'
import { useWsStore } from '@/stores/wsStore'
import { useUiStore } from '@/stores/uiStore'
import { ChevronLeft, ChevronRight, Inbox, Plus } from 'lucide-react'
import type { Run } from '@/types/api'
import { RunsToolsTab } from '@/components/runs/RunsToolsTab'

type TabFilter = 'active' | 'queue' | 'history' | 'tools'

const HISTORY_PAGE_SIZE = 25

export function RunsPage() {
  const { openNewRun } = useUiStore()
  const runsVersion = useWsStore((s) => s.runsVersion)
  const [tab, setTab] = useState<TabFilter>('active')
  const [historyPage, setHistoryPage] = useState(0)
  const stableTotal = useRef(0)

  const { data: activeRuns, isLoading: activeLoading } = useQuery({
    queryKey: ['runs', 'active', runsVersion],
    queryFn: () => runsApi.list({ limit: 200, status: 'running,paused,queued,pending' }),
    refetchInterval: 30000, // watchdog only; WS invalidation is primary
  })

  const { data: overviewPayload, isLoading: overviewLoading } = useQuery({
    queryKey: ['runs', 'list', runsVersion],
    queryFn: () => runsApi.list({ limit: 120 }),
    refetchInterval: 30000, // watchdog only; WS invalidation is primary
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
    if (t === stableTotal.current) return  // no change, skip
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
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-5">
        <h1 className="text-lg font-semibold text-[#cccccc]">Runs</h1>
        {tab !== 'tools' && (
          <Button variant="primary" size="sm" onClick={() => openNewRun()}>
            <Plus size={13} />
            New Run
          </Button>
        )}
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 mb-5 border-b border-[#3c3c3c]">
        <TabButton label="Active" count={active.length} active={tab === 'active'} onClick={() => setTab('active')} />
        <TabButton label="Queued" count={queued.length} active={tab === 'queue'} onClick={() => setTab('queue')} />
        <TabButton
          label="History"
          count={historyTotal}
          active={tab === 'history'}
          onClick={() => setTab('history')}
        />
        <TabButton label="Tools" active={tab === 'tools'} onClick={() => setTab('tools')} />
      </div>

      {tab === 'tools' && <RunsToolsTab />}

      {tab !== 'tools' && listLoading && (
        <div className="text-sm text-[#6d6d6d]">Loading…</div>
      )}

      {tab !== 'tools' && !listLoading && displayed.length === 0
        && (tab !== 'history' || historyPayload !== undefined)
        && (<EmptyState tab={tab} onNewRun={() => openNewRun()} />)
      }

      {tab !== 'tools' && (
        <div className="space-y-3">
          {displayed.map((run) => (
            <RunCard key={run.id} run={run} />
          ))}
        </div>
      )}

      {tab === 'history' && !listLoading && historyPayload && 'total' in historyPayload && historyPayload.total > 0 && (
        <div className="flex items-center justify-between mt-6 pt-4 border-t border-[#3c3c3c]">
          <span className="text-xs text-[#9d9d9d]">
            {rangeStart}–{rangeEnd} of {historyPayload.total}
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              disabled={!historyHasPrev}
              onClick={() => setHistoryPage((p) => Math.max(0, p - 1))}
              className="text-[#cccccc]"
            >
              <ChevronLeft size={16} />
              Previous
            </Button>
            <Button
              variant="ghost"
              size="sm"
              disabled={!historyHasNext}
              onClick={() => setHistoryPage((p) => p + 1)}
              className="text-[#cccccc]"
            >
              Next
              <ChevronRight size={16} />
            </Button>
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
      onClick={onClick}
      className={`
        flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px
        ${active
          ? 'border-[#4fc1ff] text-[#cccccc]'
          : 'border-transparent text-[#9d9d9d] hover:text-[#cccccc]'
        }
      `}
    >
      {label}
      {typeof count === 'number' && count > 0 && (
        <span className="bg-[#474747] text-[#9d9d9d] text-xs rounded-full px-1.5 py-0.5 min-w-[20px] text-center">
          {count}
        </span>
      )}
    </button>
  )
}

function EmptyState({ tab, onNewRun }: { tab: Exclude<TabFilter, 'tools'>; onNewRun: () => void }) {
  const messages: Record<Exclude<TabFilter, 'tools'>, string> = {
    active: 'No active runs. Start a new run to begin processing.',
    queue: 'Queue is empty.',
    history: 'No completed runs yet.',
  }
  return (
    <div className="flex flex-col items-center gap-3 py-16 text-center">
      <Inbox size={32} className="text-[#474747]" />
      <p className="text-sm text-[#6d6d6d]">{messages[tab]}</p>
      {tab === 'active' && (
        <Button variant="primary" size="sm" onClick={onNewRun}>
          <Plus size={13} />
          New Run
        </Button>
      )}
    </div>
  )
}
