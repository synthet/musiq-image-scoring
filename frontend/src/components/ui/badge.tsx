import { type ReactNode } from 'react'
import { clsx } from 'clsx'
import type { RunStatus, StageState } from '@/types/api'

interface BadgeProps {
  children: ReactNode
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'info' | 'muted' | 'running'
  size?: 'sm' | 'md'
  dot?: boolean
  className?: string
}

export function Badge({ children, variant = 'default', size = 'md', dot = false, className }: BadgeProps) {
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 rounded-full font-medium',
        size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-xs',
        variant === 'default' && 'bg-[#3c3c3c] text-[#9d9d9d] border border-[#474747]',
        variant === 'success' && 'bg-[#1a3320] text-[#89d185] border border-[#2d6a2d]',
        variant === 'warning' && 'bg-[#332900] text-[#cca700] border border-[#665200]',
        variant === 'danger' && 'bg-[#3a1515] text-[#f44747] border border-[#7a2a2a]',
        variant === 'info' && 'bg-[#003f6e] text-[#9cdcfe] border border-[#0d419d]',
        variant === 'running' && 'bg-[#003f6e] text-[#4fc1ff] border border-[#007acc]',
        variant === 'muted' && 'bg-[#252526] text-[#6d6d6d] border border-[#3c3c3c]',
        className,
      )}
    >
      {dot && (
        <span
          className={clsx(
            'w-1.5 h-1.5 rounded-full',
            variant === 'running' && 'bg-[#4fc1ff] animate-pulse',
            variant === 'success' && 'bg-[#89d185]',
            variant === 'warning' && 'bg-[#cca700]',
            variant === 'danger' && 'bg-[#f44747]',
            variant === 'muted' && 'bg-[#6d6d6d]',
            variant === 'info' && 'bg-[#9cdcfe]',
          )}
        />
      )}
      {children}
    </span>
  )
}

export function statusVariant(status: RunStatus | StageState | string): BadgeProps['variant'] {
  switch (status) {
    case 'completed':
    case 'done':
      return 'success'
    case 'running':
      return 'running'
    case 'failed':
      return 'danger'
    case 'paused':
    case 'interrupted':
    case 'cancel_requested':
      return 'warning'
    case 'skipped':
      return 'muted'
    case 'pending':
    case 'queued':
      return 'info'
    case 'canceled':
    case 'restarting':
      return 'muted'
    default:
      return 'default'
  }
}

export function statusLabel(status: RunStatus | StageState | string): string {
  const labels: Record<string, string> = {
    not_started: 'Not Started',
    pending: 'Pending',
    queued: 'Queued',
    running: 'Running',
    paused: 'Paused',
    completed: 'Completed',
    done: 'Done',
    failed: 'Failed',
    canceled: 'Canceled',
    interrupted: 'Interrupted',
    skipped: 'Skipped',
    cancel_requested: 'Cancel Requested',
    restarting: 'Restarting',
  }
  return labels[status] ?? status
}

export function RunBadge({ status }: { status: RunStatus }) {
  return (
    <Badge variant={statusVariant(status)} dot>
      {statusLabel(status)}
    </Badge>
  )
}

export function StageBadge({ state }: { state: StageState }) {
  return (
    <Badge variant={statusVariant(state)} dot size="sm">
      {statusLabel(state)}
    </Badge>
  )
}
