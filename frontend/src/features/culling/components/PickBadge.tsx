import { CheckCircle2, XCircle, Circle } from 'lucide-react'
import { clsx } from 'clsx'
import type { PickStatus } from '../utils/pickStatus'

interface PickBadgeProps {
  status: PickStatus
  size?: number
  className?: string
}

export function PickBadge({ status, size = 16, className }: PickBadgeProps) {
  if (status === 1) {
    return <CheckCircle2 size={size} className={clsx('text-success', className)} aria-label="Picked" />
  }
  if (status === -1) {
    return <XCircle size={size} className={clsx('text-danger', className)} aria-label="Rejected" />
  }
  return <Circle size={size} className={clsx('text-text-muted', className)} aria-label="Unflagged" />
}
