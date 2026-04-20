import { CheckCircle2, Circle, Clock3, Loader2, XCircle } from 'lucide-react'

export function normalizePhaseStatus(status: string | null | undefined): string {
  if (!status) return 'unknown'
  return String(status).trim().toLowerCase()
}

export function PhaseStatusIcon({ status }: { status: string }) {
  switch (status) {
    case 'completed':
    case 'success':
    case 'done':
      return <CheckCircle2 className="text-[#89d185]" size={12} />
    case 'running':
    case 'processing':
    case 'in_progress':
      return <Loader2 className="text-[#4fc1ff] animate-spin" size={12} />
    case 'pending':
    case 'queued':
      return <Clock3 className="text-[#9d9d9d]" size={12} />
    case 'failed':
    case 'error':
      return <XCircle className="text-[#f44747]" size={12} />
    default:
      return <Circle className="text-[#9d9d9d]" size={12} />
  }
}
