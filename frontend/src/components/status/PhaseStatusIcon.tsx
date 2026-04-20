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

const PHASE_STATUS_META: Record<NormalizedPhaseStatus, PhaseStatusMeta> = {
  pending: { icon: Circle, colorClass: 'text-[#6d6d6d]' },
  queued: { icon: Clock3, colorClass: 'text-[#9d9d9d]' },
  running: { icon: Loader2, colorClass: 'text-[#4fc1ff]' },
  paused: { icon: PauseCircle, colorClass: 'text-[#cca700]' },
  completed: { icon: CheckCircle2, colorClass: 'text-[#89d185]' },
  failed: { icon: XCircle, colorClass: 'text-[#f44747]' },
  skipped: { icon: MinusCircle, colorClass: 'text-[#6d6d6d]' },
  interrupted: { icon: AlertTriangle, colorClass: 'text-[#cca700]' },
  cancel_requested: { icon: AlertTriangle, colorClass: 'text-[#cca700]' },
  restarting: { icon: Loader2, colorClass: 'text-[#9d9d9d]' },
  canceled: { icon: XCircle, colorClass: 'text-[#f44747]' },
  partial: { icon: AlertTriangle, colorClass: 'text-[#cca700]' },
}

export function normalizePhaseStatus(status: string): NormalizedPhaseStatus {
  if (status === 'done') return 'completed'
  if (status === 'not_started') return 'pending'
  if (status in PHASE_STATUS_META) return status as NormalizedPhaseStatus
  return 'pending'
}

export function getPhaseStatusMeta(status: string): PhaseStatusMeta & { normalizedStatus: NormalizedPhaseStatus } {
  const normalizedStatus = normalizePhaseStatus(status)
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
