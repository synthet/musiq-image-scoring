import { clsx } from 'clsx'
import { useWsStore, type WsConnectionStatus } from '@/stores/wsStore'

function statusLabel(status: WsConnectionStatus, wasEverLive: boolean): string {
  if (status === 'live') return 'Live'
  if (status === 'connecting') return wasEverLive ? 'Reconnecting…' : 'Connecting…'
  return 'Offline'
}

function statusTitle(status: WsConnectionStatus, wasEverLive: boolean): string {
  if (status === 'live') return 'Live updates active'
  if (status === 'connecting') {
    return wasEverLive
      ? 'Reconnecting to live updates'
      : 'Connecting to live updates'
  }
  return 'Live updates unavailable'
}

export function ConnectionStatus() {
  const status = useWsStore((s) => s.connectionStatus)
  const wasEverLive = useWsStore((s) => s.wasEverLive)

  return (
    <div className="flex items-center gap-1.5">
      <div
        className={clsx(
          'w-2 h-2 rounded-full shrink-0',
          status === 'live' && 'bg-[var(--color-success)]',
          status === 'connecting' && 'bg-[var(--color-warning)] animate-pulse',
          status === 'offline' && 'bg-[var(--color-text-muted)]',
        )}
        title={statusTitle(status, wasEverLive)}
      />
      <span
        className={clsx(
          'text-xs',
          status === 'live' && 'text-[var(--color-text-muted)]',
          status === 'connecting' && 'text-[var(--color-text-secondary)]',
          status === 'offline' && 'text-[var(--color-text-muted)]',
        )}
      >
        {statusLabel(status, wasEverLive)}
      </span>
    </div>
  )
}
