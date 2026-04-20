import { AlertCircle, CheckCircle2, Loader2, MinusCircle } from 'lucide-react'

const PHASE_STATUS_ALIASES: Record<string, string> = {
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

/** Normalize backend phase statuses to a stable frontend vocabulary. */
export function normalizePhaseStatus(status: string | null | undefined): string {
  if (typeof status !== 'string') return 'unknown'
  const trimmed = status.trim()
  if (!trimmed) return 'unknown'
  const canonical = trimmed.toLowerCase().replace(/[\s-]+/g, '_')
  return PHASE_STATUS_ALIASES[canonical] ?? canonical
}

export function PhaseStatusIcon({ status }: { status: string }) {
  const normalized = normalizePhaseStatus(status)
  switch (normalized) {
    case 'done':
      return <CheckCircle2 size={12} className="text-[#89d185]" aria-hidden="true" />
    case 'failed':
      return <AlertCircle size={12} className="text-[#f44747]" aria-hidden="true" />
    case 'running':
    case 'queued':
    case 'pending':
    case 'partial':
      return <Loader2 size={12} className="text-[#cca700]" aria-hidden="true" />
    case 'skipped':
    case 'canceled':
    case 'cancel_requested':
      return <MinusCircle size={12} className="text-[#6d6d6d]" aria-hidden="true" />
    default:
      return <div className="w-3 h-3 rounded-full border border-[#474747]" aria-hidden="true" />
  }
}
