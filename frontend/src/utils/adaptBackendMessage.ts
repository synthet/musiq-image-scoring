import type { WsEvent, WsLogLine } from '@/types/api'

export interface AdaptResult {
  events: WsEvent[]
  bumpRuns: boolean
  bumpDrive?: boolean
}

const BUMP_STATUSES = new Set([
  'job_queued',
  'job_running',
  'job_pending',
  'job_completed',
  'job_failed',
  'job_canceled',
  'job_cancelled',
  'job_paused',
  'job_interrupted',
  'job_cancel_requested',
  'job_restarting',
])

/** Last job_type per run from job_started when job_progress omits job_type. */
const runJobTypeHint = new Map<number, string>()

/**
 * Map jobs.job_type from WS payloads to job_phases.phase_code used in the Runs UI.
 * @see modules/api.py _phase_code_map for backend alignment
 */
function jobTypeToUiStage(jobType: string): string {
  const t = jobType.toLowerCase()
  if (t === 'tagging') return 'keywords'
  if (t === 'clustering' || t === 'cluster') return 'culling'
  if (t === 'selection') return 'culling'
  if (t === 'fix_db') return 'scoring'
  return t
}

function resolveUiStage(data: Record<string, unknown>, run_id: number): string {
  if (typeof data.phase_code === 'string' && data.phase_code.trim()) {
    return data.phase_code.trim()
  }
  const jt =
    data.job_type != null
      ? String(data.job_type)
      : runJobTypeHint.get(run_id)
  if (data.job_type != null) {
    runJobTypeHint.set(run_id, String(data.job_type))
  }
  return jobTypeToUiStage(jt ?? 'scoring')
}

/**
 * Normalise a raw WebSocket message from the Python backend into one or more
 * typed SPA `WsEvent` objects.
 *
 * The backend sends `{ type, data }` for legacy events and flat objects for
 * the newer SPA-native event types. Both shapes are handled here so the
 * calling hook can treat every message uniformly.
 */
export function adaptBackendMessage(raw: Record<string, unknown>): AdaptResult {
  const type = String(raw.type ?? '')
  const data =
    raw.data !== undefined && typeof raw.data === 'object' && raw.data !== null
      ? (raw.data as Record<string, unknown>)
      : {}

  // Already-flat SPA-native events — pass through unchanged.
  if (type === 'run_progress' && typeof raw.run_id === 'number') {
    return { events: [raw as unknown as WsEvent], bumpRuns: false }
  }
  if (type === 'log_line' && typeof raw.run_id === 'number') {
    return { events: [raw as unknown as WsEvent], bumpRuns: false }
  }
  if (type === 'stage_transition' && typeof raw.run_id === 'number') {
    return { events: [raw as unknown as WsEvent], bumpRuns: false }
  }
  if (type === 'queue_update' && Array.isArray(raw.queue)) {
    return { events: [raw as unknown as WsEvent], bumpRuns: false }
  }
  if (type === 'work_item_done' && typeof raw.run_id === 'number') {
    return { events: [raw as unknown as WsEvent], bumpRuns: false }
  }

  if (type === 'drive_started' || type === 'drive_progress' || type === 'drive_stopped') {
    return { events: [], bumpRuns: true, bumpDrive: true }
  }

  const bumpRuns = BUMP_STATUSES.has(type)
  const events: WsEvent[] = []

  if (type === 'job_progress' || type === 'job_started') {
    const run_id = Number(data.job_id ?? data.run_id)
    if (Number.isFinite(run_id)) {
      if (type === 'job_started' && data.job_type != null) {
        runJobTypeHint.set(run_id, String(data.job_type))
      }
      if (type === 'job_started') {
        events.push({
          type: 'log_line',
          run_id,
          level: 'INFO',
          message: `Run ${run_id} started: ${data.job_type ?? 'job'}`,
          ts: new Date().toISOString(),
        })
      }
      events.push({
        type: 'run_progress',
        run_id,
        stage: resolveUiStage(data, run_id),
        items_done: Number(data.current ?? 0),
        items_total: Number(data.total ?? 0),
        throughput: 0,
        eta_seconds: 0,
      })
    }
    return { events, bumpRuns: type === 'job_started' ? true : false }
  }

  // Nested log_line (backend wraps it in { type, data })
  if (type === 'log_line') {
    const run_id = Number(data.run_id ?? data.job_id)
    if (Number.isFinite(run_id)) {
      const lv = String(data.level ?? 'INFO').toUpperCase()
      const level = (['DEBUG', 'INFO', 'WARNING', 'ERROR'].includes(lv) ? lv : 'INFO') as WsLogLine['level']
      events.push({
        type: 'log_line',
        run_id,
        level,
        message: String(data.message ?? ''),
        ts: String(data.ts ?? new Date().toISOString()),
      })
    }
    return { events, bumpRuns: false }
  }

  if (type === 'job_completed' || type === 'job_failed') {
    const run_id = Number(data.job_id ?? data.run_id)
    if (Number.isFinite(run_id)) {
      runJobTypeHint.delete(run_id)
      const status = String(data.status ?? (type === 'job_failed' ? 'failed' : 'completed'))
      const err = data.error != null ? String(data.error) : ''
      events.push({
        type: 'log_line',
        run_id,
        level: type === 'job_failed' ? 'ERROR' : 'INFO',
        message: err ? `${status}: ${err}` : status,
        ts: new Date().toISOString(),
      })
    }
    return { events, bumpRuns }
  }

  return { events, bumpRuns }
}
