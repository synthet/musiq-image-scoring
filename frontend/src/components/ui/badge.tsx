import { type ReactNode } from 'react'
import { clsx } from 'clsx'
import type { RunStatus, StageState } from '@/types/api'

export interface BadgeProps {
  children: ReactNode
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'info' | 'muted' | 'running'
  size?: 'sm' | 'md'
  dot?: boolean
  className?: string
}

const VARIANT_CLASSES: Record<NonNullable<BadgeProps['variant']>, string> = {
  default:
    'bg-[var(--color-bg-elevated)] text-[var(--color-text-secondary)] border border-[var(--color-border)]',
  success:
    'bg-[var(--color-success-bg)] text-[var(--color-success)] border border-[var(--color-success-border)]',
  warning:
    'bg-[var(--color-warning-bg)] text-[var(--color-warning)] border border-[var(--color-warning-border)]',
  danger:
    'bg-[var(--color-danger-bg)] text-[var(--color-danger)] border border-[var(--color-danger-border)]',
  info: 'bg-[var(--color-info-bg)] text-[var(--color-info)] border border-[var(--color-accent-border)]',
  running:
    'bg-[var(--color-accent-dim)] text-[var(--color-accent-bright)] border border-[var(--color-accent)]',
  muted:
    'bg-[var(--color-bg-secondary)] text-[var(--color-text-muted)] border border-[var(--color-border-muted)]',
}

const DOT_CLASSES: Record<NonNullable<BadgeProps['variant']>, string> = {
  default: 'bg-[var(--color-text-muted)]',
  success: 'bg-[var(--color-success)]',
  warning: 'bg-[var(--color-warning)]',
  danger: 'bg-[var(--color-danger)]',
  info: 'bg-[var(--color-info)]',
  running: 'bg-[var(--color-accent-bright)] animate-pulse',
  muted: 'bg-[var(--color-text-muted)]',
}

export function Badge({ children, variant = 'default', size = 'md', dot = false, className }: BadgeProps) {
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 rounded-full font-medium',
        size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-xs',
        VARIANT_CLASSES[variant],
        className,
      )}
    >
      {dot && <span className={clsx('w-1.5 h-1.5 rounded-full', DOT_CLASSES[variant])} />}
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
    case 'partial':
      return 'warning'
    case 'skipped':
    case 'pending':
    case 'queued':
    case 'canceled':
    case 'restarting':
    case 'not_started':
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
