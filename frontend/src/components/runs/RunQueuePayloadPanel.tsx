/**
 * Shows queue_payload / run flags from the jobs row (what the dispatcher and runners use).
 */

import type { RunQueueReason } from '../../types/api'

function stageQueueLengths(
  repairPlan: Record<string, unknown> | undefined,
): { code: string; count: number }[] {
  if (!repairPlan || typeof repairPlan !== 'object') return []
  const queues = repairPlan.stage_queues
  if (!queues || typeof queues !== 'object') return []
  const seen = new Set<string>()
  const rows: { code: string; count: number }[] = []
  for (const [code, ids] of Object.entries(queues as Record<string, unknown>)) {
    if (code === 'clustering') continue
    if (seen.has(code)) continue
    seen.add(code)
    if (!Array.isArray(ids)) continue
    rows.push({ code, count: ids.length })
  }
  const order = [
    'indexing',
    'metadata',
    'scoring',
    'culling',
    'keywords',
    'bird_species',
  ]
  rows.sort((a, b) => {
    const ia = order.indexOf(a.code)
    const ib = order.indexOf(b.code)
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib)
  })
  return rows
}

function parseQueueReason(queuePayload: Record<string, unknown>): RunQueueReason | null {
  const raw = queuePayload.reason
  if (!raw || typeof raw !== 'object') return null
  const reason = raw as RunQueueReason
  if (typeof reason.summary !== 'string' || !reason.summary.trim()) return null
  return reason
}

function topPlannerBadges(criteria: Record<string, unknown> | undefined): string[] {
  if (!criteria || typeof criteria !== 'object') return []
  const badges: string[] = []
  const bucket = criteria.auto_drive_bucket
  if (typeof bucket === 'string' && bucket.trim()) {
    badges.push(bucket.replace(/_/g, ' '))
  }
  const counts = criteria.planner_reason_counts
  if (counts && typeof counts === 'object') {
    const entries = Object.entries(counts as Record<string, unknown>)
      .map(([k, v]) => [k, typeof v === 'number' ? v : Number(v)] as const)
      .filter(([, v]) => Number.isFinite(v) && v > 0)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
    for (const [k, v] of entries) {
      badges.push(`${k.replace(/_/g, ' ')}=${v}`)
    }
  }
  return badges
}

export function RunQueuePayloadPanel({
  jobType,
  queuePayload,
}: {
  jobType: string
  queuePayload?: Record<string, unknown> | null
}) {
  const hasPayload = queuePayload && typeof queuePayload === 'object' && Object.keys(queuePayload).length > 0
  const enqueueReason = hasPayload ? parseQueueReason(queuePayload) : null
  const reasonBadges = topPlannerBadges(enqueueReason?.criteria)
  const repairPlan =
    hasPayload && typeof queuePayload.repair_plan_summary === 'object'
      ? (queuePayload.repair_plan_summary as Record<string, unknown>)
      : undefined
  const queueRows = stageQueueLengths(repairPlan)
  const reasons =
    repairPlan && typeof repairPlan.issue_counts_by_reason === 'object'
      ? (repairPlan.issue_counts_by_reason as Record<string, number>)
      : null

  return (
    <div className="rounded-md border border-[#474747] bg-[#252526] flex flex-col">
      <div className="px-4 py-2 border-b border-[#3c3c3c] shrink-0">
        <span className="text-xs font-semibold text-[#cccccc]">Run options</span>
        <span className="text-[10px] text-[#6d6d6d] ml-2 font-mono">job_type: {jobType || '—'}</span>
      </div>
      {enqueueReason && (
        <div className="px-4 py-3 border-b border-[#3c3c3c] space-y-2">
          <p className="text-[10px] text-[#9d9d9d] uppercase tracking-wide">Why this run was queued</p>
          <p className="text-sm text-[#cccccc] leading-snug">{enqueueReason.summary}</p>
          <div className="flex flex-wrap gap-1.5">
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#1e1e1e] text-[#4fc1ff] border border-[#3c3c3c]">
              {enqueueReason.source.replace(/_/g, ' ')}
            </span>
            {reasonBadges.map((badge) => (
              <span
                key={badge}
                className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#1e1e1e] text-[#9d9d9d] border border-[#3c3c3c]"
              >
                {badge}
              </span>
            ))}
          </div>
        </div>
      )}
      {queueRows.length > 0 && (
        <div className="px-4 py-2 border-b border-[#3c3c3c] space-y-1">
          <p className="text-[10px] text-[#9d9d9d] uppercase tracking-wide">Planner queues at enqueue</p>
          <ul className="text-xs font-mono text-[#cccccc] space-y-0.5">
            {queueRows.map(({ code, count }) => (
              <li key={code}>
                <span className="text-[#4fc1ff]">{code}</span>
                <span className="text-[#6d6d6d]"> — </span>
                {count} image{count === 1 ? '' : 's'}
              </li>
            ))}
          </ul>
          {reasons && Object.keys(reasons).length > 0 && (
            <p className="text-[10px] text-[#6d6d6d] pt-1">
              Reasons:{' '}
              {Object.entries(reasons)
                .map(([k, v]) => `${k}=${v}`)
                .join(', ')}
            </p>
          )}
          <p className="text-[10px] text-[#6d6d6d]">
            Pending stages may auto-skip at dispatch when JIT finds no stale/missing work.
          </p>
        </div>
      )}
      <div className="px-4 py-3 max-h-64 overflow-auto">
        {!hasPayload ? (
          <p className="text-xs text-[#6d6d6d]">No queue_payload for this run (older jobs may omit it).</p>
        ) : (
          <pre className="text-[10px] font-mono text-[#9d9d9d] whitespace-pre-wrap break-words leading-relaxed">
            {JSON.stringify(queuePayload, null, 2)}
          </pre>
        )}
      </div>
      <p className="px-4 pb-2 text-[10px] text-[#6d6d6d] border-t border-[#3c3c3c] pt-2">
        Flags such as <span className="text-[#cccccc]">run_mode</span> (always{' '}
        <span className="text-[#cccccc]">process_stale_or_missing</span>),{' '}
        <span className="text-[#cccccc]">resolved_image_ids</span>,{' '}
        <span className="text-[#cccccc]">force_rescan</span>, and clustering{' '}
        <span className="text-[#cccccc]">threshold</span> (visual cosine distance) /{' '}
        <span className="text-[#cccccc]">time_gap</span> (capture-time gap in seconds between consecutive shots) come
        from this payload when the run was queued.
      </p>
    </div>
  )
}
