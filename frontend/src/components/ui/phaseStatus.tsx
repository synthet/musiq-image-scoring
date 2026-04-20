import { CheckCircle2, Circle, Clock3, Loader2, XCircle } from 'lucide-react'

export function normalizePhaseStatus(status: string | null | undefined): string {
  if (!status) return 'unknown'
  return String(status).trim().toLowerCase()
}

export function PhaseStatusIcon({ status }: { status: string }) {
  const normalized = normalizePhaseStatus(status)

  if (normalized === 'completed' || normalized === 'done' || normalized === 'success') {
    return <CheckCircle2 size={12} className="text-[#89d185]" />
  }
  if (normalized === 'running' || normalized === 'in_progress' || normalized === 'processing') {
    return <Loader2 size={12} className="text-[#4fc1ff] animate-spin" />
  }
  if (normalized === 'pending' || normalized === 'queued') {
    return <Clock3 size={12} className="text-[#9d9d9d]" />
  }
  if (normalized === 'failed' || normalized === 'error') {
    return <XCircle size={12} className="text-[#f44747]" />
  }
  return <Circle size={12} className="text-[#9d9d9d]" />
}
