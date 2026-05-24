/**
 * Shows queue_payload / run flags from the jobs row (what the dispatcher and runners use).
 */
export function RunQueuePayloadPanel({
  jobType,
  queuePayload,
}: {
  jobType: string
  queuePayload?: Record<string, unknown> | null
}) {
  const hasPayload = queuePayload && typeof queuePayload === 'object' && Object.keys(queuePayload).length > 0

  return (
    <div className="rounded-md border border-[#474747] bg-[#252526] flex flex-col">
      <div className="px-4 py-2 border-b border-[#3c3c3c] shrink-0">
        <span className="text-xs font-semibold text-[#cccccc]">Run options</span>
        <span className="text-[10px] text-[#6d6d6d] ml-2 font-mono">job_type: {jobType || '—'}</span>
      </div>
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
