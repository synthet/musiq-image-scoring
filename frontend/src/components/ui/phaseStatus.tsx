import { AlertCircle, CheckCircle2, Loader2, MinusCircle } from 'lucide-react'

export function normalizePhaseStatus(status: string | null | undefined): string {
  if (!status) return 'unknown'

  const normalized = String(status).trim().toLowerCase()
  return PHASE_STATUS_ALIASES[normalized] ?? normalized
}

const PHASE_STATUS_ALIASES: Record<string, string> = {
  complete: 'done',
  completed: 'done',
  success: 'done',
  succeeded: 'done',
  in_progress: 'running',
  processing: 'running',
  error: 'failed',
  cancelled: 'canceled',
}

export function PhaseStatusIcon({ status }: { status: string | null | undefined }) {
  const normalized = normalizePhaseStatus(status)

  if (normalized === 'done') {
    return <CheckCircle2 className="text-[#89d185]" size={12} />
  }
  if (normalized === 'running') {
    return <Loader2 className="text-[#4fc1ff] animate-spin" size={12} />
  }
  if (normalized === 'failed' || normalized === 'canceled') {
    return <AlertCircle className="text-[#f44747]" size={12} />
  }

  return <MinusCircle className="text-[#9d9d9d]" size={12} />
}
