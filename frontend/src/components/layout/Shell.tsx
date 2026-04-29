import { useEffect } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { clsx } from 'clsx'
import {
  PanelLeft,
  Zap,
  Workflow,
  Stethoscope,
  ScrollText,
  Database,
  DatabaseZap,
  Search,
  MapPin,
} from 'lucide-react'
import { Sidebar } from './Sidebar'
import { useUiStore } from '@/stores/uiStore'
import { useWsStore } from '@/stores/wsStore'
import { useWebSocket } from '@/hooks/useWebSocket'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { runsApi } from '@/api/runs'
import { RUNS_ACTIVE_QUERY_KEY } from '@/queryKeys/runs'

export function Shell() {
  useWebSocket()

  const { sidebarOpen, toggleSidebar } = useUiStore()
  const connected = useWsStore((s) => s.connected)
  const runsVersion = useWsStore((s) => s.runsVersion)
  const qc = useQueryClient()

  const { data: runsRaw } = useQuery({
    queryKey: RUNS_ACTIVE_QUERY_KEY,
    queryFn: () => runsApi.list({ limit: 50 }),
    refetchInterval: 5000,
  })
  const runs = Array.isArray(runsRaw) ? runsRaw : []

  useEffect(() => {
    if (runsVersion === 0) return
    qc.invalidateQueries({ queryKey: RUNS_ACTIVE_QUERY_KEY })
  }, [runsVersion, qc])

  const activeCount = runs?.filter((r) => r.status === 'running').length ?? 0
  const queuedCount = runs?.filter((r) => r.status === 'queued' || r.status === 'pending').length ?? 0

  return (
    <div className="flex h-full flex-col bg-[#1e1e1e]">
      {/* Top nav */}
      <header className="flex h-12 items-center gap-3 border-b border-[#3c3c3c] bg-[#252526] px-4 shrink-0">
        <button
          onClick={toggleSidebar}
          className="p-1 rounded text-[#9d9d9d] hover:text-[#cccccc] hover:bg-[#3c3c3c] transition-colors"
        >
          <PanelLeft size={16} />
        </button>

        <div className="flex items-center gap-2 mr-4">
          <Zap size={16} className="text-[#4fc1ff]" />
          <span className="text-sm font-semibold text-[#cccccc]">Vexlum Scoring</span>
        </div>

        <nav className="flex items-center gap-1">
          <NavItem to="/runs" icon={<Workflow size={14} />} label="Runs" />
          <NavItem to="/images" icon={<Database size={14} />} label="Images" />
          <NavItem to="/embeddings" icon={<DatabaseZap size={14} />} label="Vector DB" />
          <NavItem to="/search" icon={<Search size={14} />} label="Search" />
          <NavItem to="/map" icon={<MapPin size={14} />} label="Map" />
          <NavItem to="/diagnostics" icon={<Stethoscope size={14} />} label="Health" />
          <NavItem to="/logs" icon={<ScrollText size={14} />} label="Logs" />
        </nav>

        <div className="ml-auto flex items-center gap-3">
          {(activeCount > 0 || queuedCount > 0) && (
            <NavLink to="/runs" className="text-xs text-[#9d9d9d] hover:text-[#4fc1ff] transition-colors">
              {activeCount > 0 && (
                <span className="text-[#4fc1ff] font-medium">{activeCount} active</span>
              )}
              {activeCount > 0 && queuedCount > 0 && <span className="mx-1">·</span>}
              {queuedCount > 0 && <span>{queuedCount} queued</span>}
            </NavLink>
          )}

          <div className="flex items-center gap-1.5">
            <div
              className={clsx(
                'w-2 h-2 rounded-full',
                connected ? 'bg-[#89d185]' : 'bg-[#6d6d6d]',
              )}
              title={connected ? 'Live updates active' : 'Disconnected'}
            />
            <span className="text-xs text-[#6d6d6d]">{connected ? 'Live' : 'Offline'}</span>
          </div>
        </div>
      </header>

      {/* Body */}
      <div className="flex flex-1 min-h-0">
        {sidebarOpen && <Sidebar />}
        <main className="flex-1 min-w-0 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

function NavItem({
  to,
  icon,
  label,
  end,
}: {
  to: string
  icon: React.ReactNode
  label: string
  end?: boolean
}) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        clsx(
          'flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors',
          isActive
            ? 'text-[#cccccc] bg-[#3c3c3c]'
            : 'text-[#9d9d9d] hover:text-[#cccccc] hover:bg-[#3c3c3c]',
        )
      }
    >
      {icon}
      {label}
    </NavLink>
  )
}
