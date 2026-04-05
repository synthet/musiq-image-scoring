import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { runsApi } from '@/api/runs'
import { RunCard } from '@/components/runs/RunCard'
import { Button } from '@/components/ui/button'
import { useWsStore } from '@/stores/wsStore'
import { useUiStore } from '@/stores/uiStore'
import { Plus, Inbox } from 'lucide-react'
import type { Run } from '@/types/api'
import { RunsToolsTab } from '@/components/runs/RunsToolsTab'

type TabFilter = 'active' | 'queue' | 'history' | 'tools'

export function RunsPage() {
  const { openNewRun } = useUiStore()
  const runsVersion = useWsStore((s) => s.runsVersion)
  const [tab, setTab] = useState<TabFilter>('active')

  const { data, isLoading } = useQuery({
    queryKey: ['runs', runsVersion],
    queryFn: () => runsApi.list({ limit: 100 }),
    refetchInterval: 5000,
  })
  const runs: Run[] = Array.isArray(data) ? data : []

  const active = runs.filter((r) => r.status === 'running' || r.status === 'paused')
  const queued = runs.filter((r) => r.status === 'queued' || r.status === 'pending')
  const history = runs.filter(
    (r) =>
      r.status === 'completed' ||
      r.status === 'failed' ||
      r.status === 'canceled' ||
      r.status === 'interrupted',
  )

  const displayed: Run[] =
    tab === 'active' ? [...active, ...queued] : tab === 'queue' ? queued : history

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
        <TabButton label="History" count={history.length} active={tab === 'history'} onClick={() => setTab('history')} />
        <TabButton label="Tools" active={tab === 'tools'} onClick={() => setTab('tools')} />
      </div>

      {tab === 'tools' && <RunsToolsTab />}

      {tab !== 'tools' && isLoading && (
        <div className="text-sm text-[#6d6d6d]">Loading…</div>
      )}

      {tab !== 'tools' && !isLoading && displayed.length === 0 && (
        <EmptyState tab={tab} onNewRun={() => openNewRun()} />
      )}

      {tab !== 'tools' && (
        <div className="space-y-3">
          {displayed.map((run) => (
            <RunCard key={run.id} run={run} />
          ))}
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
