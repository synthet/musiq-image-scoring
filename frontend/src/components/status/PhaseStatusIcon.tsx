import type { LucideIcon } from 'lucide-react'
import {
  AlertTriangle,
  CheckCircle2,
  Circle,
  Clock3,
  Loader2,
  MinusCircle,
  PauseCircle,
  XCircle,
} from 'lucide-react'
import { clsx } from 'clsx'

export type PhaseStatus =
  | 'pending'
  | 'queued'
  | 'running'
  | 'paused'
  | 'completed'
  | 'done'
  | 'failed'
  | 'skipped'
  | 'interrupted'
  | 'cancel_requested'
  | 'restarting'
  | 'canceled'
  | 'partial'
  | 'not_started'

export type NormalizedPhaseStatus = Exclude<PhaseStatus, 'done' | 'not_started'> | 'completed' | 'pending'

type PhaseStatusMeta = {
  icon: LucideIcon
  colorClass: string
}

/** Backend / API strings → stable snake_case before icon mapping (same as former ui/phaseStatus). */
const LEGACY_PHASE_ALIASES: Record<string, string> = {
  complete: 'done',
  completed: 'done',
  success: 'done',
  succeeded: 'done',
  in_progress: 'running',
  processing: 'running',
  error: 'failed',
  cancelled: 'canceled',
  cancel_requested: 'cancel_requested',
  notstarted: 'not_started',
}

/**
 * Stable vocabulary for `statusLabel()` and display text (e.g. inspector phase table).
 */
export function normalizeLegacyPhaseStatus(status: string | null | undefined): string {
  if (typeof status !== 'string') return 'unknown'
  const trimmed = status.trim()
  if (!trimmed) return 'unknown'
  const canonical = trimmed.toLowerCase().replace(/[\s-]+/g, '_')
  return LEGACY_PHASE_ALIASES[canonical] ?? canonical
}

const PHASE_STATUS_META: Record<NormalizedPhaseStatus, PhaseStatusMeta> = {
  pending: { icon: Circle, colorClass: 'text-[var(--color-text-muted)]' },
  queued: { icon: Clock3, colorClass: 'text-[var(--color-text-secondary)]' },
  running: { icon: Loader2, colorClass: 'text-[var(--color-accent-bright)]' },
  paused: { icon: PauseCircle, colorClass: 'text-[var(--color-warning)]' },
  completed: { icon: CheckCircle2, colorClass: 'text-[var(--color-success)]' },
  failed: { icon: XCircle, colorClass: 'text-[var(--color-danger)]' },
  skipped: { icon: MinusCircle, colorClass: 'text-[var(--color-text-muted)]' },
  interrupted: { icon: AlertTriangle, colorClass: 'text-[var(--color-warning)]' },
  cancel_requested: { icon: AlertTriangle, colorClass: 'text-[var(--color-warning)]' },
  restarting: { icon: Loader2, colorClass: 'text-[var(--color-text-secondary)]' },
  canceled: { icon: XCircle, colorClass: 'text-[var(--color-danger)]' },
  partial: { icon: AlertTriangle, colorClass: 'text-[var(--color-warning)]' },
}

function legacyToNormalized(legacy: string): NormalizedPhaseStatus {
  if (legacy === 'unknown') return 'pending'
  if (legacy === 'done') return 'completed'
  if (legacy === 'not_started') return 'pending'
  if (legacy in PHASE_STATUS_META) return legacy as NormalizedPhaseStatus
  return 'pending'
}

export function normalizePhaseStatus(status: string): NormalizedPhaseStatus {
  return legacyToNormalized(normalizeLegacyPhaseStatus(status))
}

export function getPhaseStatusMeta(status: string): PhaseStatusMeta & { normalizedStatus: NormalizedPhaseStatus } {
  const normalizedStatus = legacyToNormalized(normalizeLegacyPhaseStatus(status))
  return { ...PHASE_STATUS_META[normalizedStatus], normalizedStatus }
}

interface PhaseStatusIconProps {
  status: string
  size?: number
  animated?: boolean
  className?: string
}

export function PhaseStatusIcon({ status, size = 12, animated = false, className }: PhaseStatusIconProps) {
  const { icon: Icon, colorClass, normalizedStatus } = getPhaseStatusMeta(status)
  const shouldSpin = animated && (normalizedStatus === 'running' || normalizedStatus === 'restarting')

  return (
    <Icon
      size={size}
      className={clsx(colorClass, shouldSpin && 'animate-spin', 'shrink-0', className)}
    />
  )
}
