import { useEffect } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { clsx } from 'clsx'
import {
  PanelLeft,
  Zap,
  Workflow,
  LayoutDashboard,
  Stethoscope,
  ScrollText,
  MapPin,
  ChartScatter,
  Image,
  Table2,
} from 'lucide-react'
import { dispatchDbExplorerToggleTables } from '@/pages/DbPage'
import { Sidebar } from './Sidebar'
import { ConnectionStatus } from './ConnectionStatus'
import { useUiStore } from '@/stores/uiStore'
import { useWsStore } from '@/stores/wsStore'
import { useWebSocket } from '@/hooks/useWebSocket'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { runsApi } from '@/api/runs'
import { RUNS_ACTIVE_QUERY_KEY, RUNS_DRIVE_STATUS_KEY } from '@/queryKeys/runs'
import { useConfig } from '@/hooks/useConfig'

export function Shell() {
  useWebSocket()

  const { sidebarOpen, toggleSidebar } = useUiStore()
  const runsVersion = useWsStore((s) => s.runsVersion)
  const qc = useQueryClient()
  const { isEmbeddingMapEnabled, isDbExplorerEnabled } = useConfig()
  const location = useLocation()
  const isDbPage = location.pathname.startsWith('/db')

  const handlePanelLeft = () => {
    if (isDbPage) {
      dispatchDbExplorerToggleTables()
    } else {
      toggleSidebar()
    }
  }

  const { data: runsRaw } = useQuery({
    queryKey: RUNS_ACTIVE_QUERY_KEY,
    queryFn: () => runsApi.list({ limit: 50 }),
    refetchInterval: 5000,
  })
  const runs = Array.isArray(runsRaw) ? runsRaw : []

  const { data: driveStatus } = useQuery({
    queryKey: RUNS_DRIVE_STATUS_KEY,
    queryFn: () => runsApi.drive.status(),
    refetchInterval: 5000,
  })
  const driving = Boolean(driveStatus?.state?.enabled)

  useEffect(() => {
    if (runsVersion === 0) return
    qc.invalidateQueries({ queryKey: RUNS_ACTIVE_QUERY_KEY })
  }, [runsVersion, qc])

  const activeCount = runs?.filter((r) => r.status === 'running').length ?? 0
  const queuedCount = runs?.filter((r) => r.status === 'queued' || r.status === 'pending').length ?? 0

  return (
    <div className="flex h-full flex-col bg-[var(--color-bg-primary)]">
      <header className="flex h-12 items-center gap-3 border-b border-[var(--color-border-muted)] bg-[var(--color-bg-secondary)] px-4 shrink-0">
        <button
          type="button"
          onClick={handlePanelLeft}
          title={isDbPage ? 'Toggle table list' : 'Toggle folder sidebar'}
          className="p-1 rounded text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-bg-elevated)] transition-colors"
        >
          <PanelLeft size={16} />
        </button>

        <div className="flex items-center gap-2 mr-4">
          <Zap size={16} className="text-[var(--color-accent-bright)]" />
          <span className="text-sm font-semibold text-[var(--color-text-primary)]">Vexlum Scoring</span>
        </div>

        <nav className="flex items-center gap-1">
          <NavItem to="/runs" icon={<Workflow size={14} />} label="Runs" />
          <NavItem to="/dashboard" icon={<LayoutDashboard size={14} />} label="Dashboard" />
          <NavItem to="/images" icon={<Image size={14} />} label="Images" />
          {isEmbeddingMapEnabled && (
            <NavItem to="/embeddings" icon={<ChartScatter size={14} />} label="Atlas" />
          )}
          {isDbExplorerEnabled && (
            <NavItem to="/db" icon={<Table2 size={14} />} label="DB" />
          )}
          <NavItem to="/map" icon={<MapPin size={14} />} label="Map" />
          <NavItem to="/diagnostics" icon={<Stethoscope size={14} />} label="Health" />
          <NavItem to="/logs" icon={<ScrollText size={14} />} label="Logs" />
        </nav>

        <div className="ml-auto flex items-center gap-3">
          {(driving || activeCount > 0 || queuedCount > 0) && (
            <div className="flex items-center gap-2 text-xs text-[var(--color-text-secondary)]">
              {driving && (
                <NavLink to="/dashboard" className="font-medium text-[var(--color-accent-bright)] hover:underline">
                  Driving
                </NavLink>
              )}
              {(activeCount > 0 || queuedCount > 0) && (
                <NavLink to="/runs" className="hover:text-[var(--color-accent-bright)] transition-colors">
                  {driving && <span className="mr-1">·</span>}
                  {activeCount > 0 && (
                    <span className="text-[var(--color-accent-bright)] font-medium">{activeCount} active</span>
                  )}
                  {activeCount > 0 && queuedCount > 0 && <span className="mx-1">·</span>}
                  {queuedCount > 0 && <span>{queuedCount} queued</span>}
                </NavLink>
              )}
            </div>
          )}

          <ConnectionStatus />
        </div>
      </header>

      <div className="flex flex-1 min-h-0">
        {sidebarOpen && !isDbPage && <Sidebar />}
        <main className={clsx('flex-1 min-h-0 min-w-0', isDbPage ? 'overflow-hidden' : 'overflow-y-auto')}>
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
            ? 'text-[var(--color-text-primary)] bg-[var(--color-bg-elevated)]'
            : 'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-bg-elevated)]',
        )
      }
    >
      {icon}
      {label}
    </NavLink>
  )
}
