import { describe, it, expect } from 'vitest'
import { adaptBackendMessage } from './adaptBackendMessage'

// ─── Helpers ────────────────────────────────────────────────────────────────

function msg(type: string, data?: Record<string, unknown>): Record<string, unknown> {
  return data !== undefined ? { type, data } : { type }
}

// ─── Pass-through: already-flat SPA-native events ───────────────────────────

describe('flat SPA-native events pass through unchanged', () => {
  it('run_progress with run_id', () => {
    const raw = {
      type: 'run_progress',
      run_id: 42,
      stage: 'scoring',
      items_done: 10,
      items_total: 100,
      throughput: 2.5,
      eta_seconds: 45,
    }
    const { events, bumpRuns } = adaptBackendMessage(raw)
    expect(bumpRuns).toBe(false)
    expect(events).toHaveLength(1)
    expect(events[0]).toEqual(raw)
  })

  it('log_line with top-level run_id passes through', () => {
    const raw = {
      type: 'log_line',
      run_id: 7,
      level: 'INFO',
      message: 'hello',
      ts: '2026-01-01T00:00:00Z',
    }
    const { events, bumpRuns } = adaptBackendMessage(raw)
    expect(bumpRuns).toBe(false)
    expect(events[0]).toEqual(raw)
  })

  it('stage_transition with top-level run_id passes through', () => {
    const raw = { type: 'stage_transition', run_id: 5, stage: 'scoring', from_state: 'queued', to_state: 'running' }
    const { events } = adaptBackendMessage(raw)
    expect(events[0]).toEqual(raw)
  })

  it('queue_update with top-level array passes through', () => {
    const raw = { type: 'queue_update', queue: [] }
    const { events } = adaptBackendMessage(raw)
    expect(events[0]).toEqual(raw)
  })

  it('work_item_done with top-level run_id passes through', () => {
    const raw = { type: 'work_item_done', run_id: 9, image_id: 1, stage: 'scoring', status: 'done' }
    const { events } = adaptBackendMessage(raw)
    expect(events[0]).toEqual(raw)
  })
})

// ─── Legacy { type, data } events ───────────────────────────────────────────

describe('job_progress → run_progress', () => {
  it('maps job_id/current/total to run_progress fields', () => {
    const raw = msg('job_progress', { job_id: 303, current: 30, total: 100, job_type: 'scoring' })
    const { events, bumpRuns } = adaptBackendMessage(raw)
    expect(bumpRuns).toBe(false)
    expect(events).toHaveLength(1)
    const e = events[0]
    expect(e.type).toBe('run_progress')
    if (e.type === 'run_progress') {
      expect(e.run_id).toBe(303)
      expect(e.items_done).toBe(30)
      expect(e.items_total).toBe(100)
      expect(e.stage).toBe('scoring')
    }
  })

  it('omits event when job_id is missing', () => {
    const { events } = adaptBackendMessage(msg('job_progress', {}))
    expect(events).toHaveLength(0)
  })
})

describe('nested log_line (type=log_line, data has run_id)', () => {
  it('unwraps data into flat log_line event', () => {
    const raw = msg('log_line', { run_id: 55, level: 'WARNING', message: 'uh oh', ts: '2026-01-01T00:00:00Z' })
    const { events, bumpRuns } = adaptBackendMessage(raw)
    expect(bumpRuns).toBe(false)
    expect(events).toHaveLength(1)
    const e = events[0]
    expect(e.type).toBe('log_line')
    if (e.type === 'log_line') {
      expect(e.run_id).toBe(55)
      expect(e.level).toBe('WARNING')
      expect(e.message).toBe('uh oh')
    }
  })

  it('normalises unknown level to INFO', () => {
    const raw = msg('log_line', { run_id: 1, level: 'VERBOSE', message: 'x', ts: 't' })
    const { events } = adaptBackendMessage(raw)
    if (events[0].type === 'log_line') {
      expect(events[0].level).toBe('INFO')
    }
  })

  it('omits event when data has no run_id', () => {
    const { events } = adaptBackendMessage(msg('log_line', { level: 'INFO', message: 'hi' }))
    expect(events).toHaveLength(0)
  })
})

describe('job_completed / job_failed → log_line + bumpRuns', () => {
  it('job_completed emits INFO log_line and bumps runs', () => {
    const raw = msg('job_completed', { job_id: 10, status: 'completed' })
    const { events, bumpRuns } = adaptBackendMessage(raw)
    expect(bumpRuns).toBe(true)
    expect(events).toHaveLength(1)
    const e = events[0]
    expect(e.type).toBe('log_line')
    if (e.type === 'log_line') {
      expect(e.run_id).toBe(10)
      expect(e.level).toBe('INFO')
      expect(e.message).toBe('completed')
    }
  })

  it('job_failed emits ERROR log_line and bumps runs', () => {
    const raw = msg('job_failed', { job_id: 11, status: 'failed', error: 'OOM' })
    const { events, bumpRuns } = adaptBackendMessage(raw)
    expect(bumpRuns).toBe(true)
    const e = events[0]
    if (e.type === 'log_line') {
      expect(e.level).toBe('ERROR')
      expect(e.message).toBe('failed: OOM')
    }
  })

  it('omits event when job_id is missing', () => {
    const { events } = adaptBackendMessage(msg('job_completed', {}))
    expect(events).toHaveLength(0)
  })
})

describe('job_started', () => {
  it('emits log_line plus run_progress and bumps runs', () => {
    const raw = msg('job_started', { job_id: 88001, job_type: 'scoring', current: 0, total: 50 })
    const { events, bumpRuns } = adaptBackendMessage(raw)
    expect(bumpRuns).toBe(true)
    expect(events).toHaveLength(2)
    expect(events[0].type).toBe('log_line')
    if (events[0].type === 'log_line') {
      expect(events[0].run_id).toBe(88001)
      expect(events[0].message).toContain('88001')
      expect(events[0].message).toContain('scoring')
    }
    const rp = events[1]
    expect(rp.type).toBe('run_progress')
    if (rp.type === 'run_progress') {
      expect(rp.run_id).toBe(88001)
      expect(rp.stage).toBe('scoring')
      expect(rp.items_done).toBe(0)
      expect(rp.items_total).toBe(50)
    }
  })

  it('defaults stage to scoring when job_type is missing', () => {
    const raw = msg('job_started', { job_id: 88002, current: 0, total: 1 })
    const { events } = adaptBackendMessage(raw)
    const rp = events.find((e) => e.type === 'run_progress')
    expect(rp && rp.type === 'run_progress' && rp.stage).toBe('scoring')
  })
})

describe('job_progress stage from phase_code and job_type mapping', () => {
  it('prefers phase_code over job_type for stage', () => {
    const raw = msg('job_progress', {
      job_id: 88200,
      current: 1,
      total: 2,
      phase_code: 'metadata',
      job_type: 'scoring',
    })
    const { events } = adaptBackendMessage(raw)
    const rp = events[0]
    expect(rp.type).toBe('run_progress')
    if (rp.type === 'run_progress') expect(rp.stage).toBe('metadata')
  })

  it.each([
    { jobId: 88401, jobType: 'tagging', uiStage: 'keywords' },
    { jobId: 88402, jobType: 'clustering', uiStage: 'culling' },
    { jobId: 88403, jobType: 'cluster', uiStage: 'culling' },
    { jobId: 88404, jobType: 'selection', uiStage: 'culling' },
    { jobId: 88405, jobType: 'fix_db', uiStage: 'scoring' },
  ])('maps job_type $jobType to UI stage $uiStage', ({ jobId, jobType, uiStage }) => {
    const raw = msg('job_progress', { job_id: jobId, current: 0, total: 1, job_type: jobType })
    const { events } = adaptBackendMessage(raw)
    const rp = events[0]
    expect(rp.type).toBe('run_progress')
    if (rp.type === 'run_progress') expect(rp.stage).toBe(uiStage)
  })
})

describe('job_progress uses job_type hint from prior job_started', () => {
  it('uses stored job_type when job_progress omits job_type', () => {
    const rid = 987654
    adaptBackendMessage(msg('job_started', { job_id: rid, job_type: 'tagging', current: 0, total: 1 }))
    const { events } = adaptBackendMessage(
      msg('job_progress', { job_id: rid, current: 2, total: 10 }),
    )
    expect(events).toHaveLength(1)
    const rp = events[0]
    expect(rp.type).toBe('run_progress')
    if (rp.type === 'run_progress') expect(rp.stage).toBe('keywords')
  })
})

describe('bumpRuns for job status change events', () => {
  const statusEvents = [
    'job_queued', 'job_running', 'job_pending', 'job_canceled',
    'job_cancelled', 'job_paused', 'job_interrupted', 'job_cancel_requested', 'job_restarting',
  ]
  for (const type of statusEvents) {
    it(`${type} bumps runs`, () => {
      const { bumpRuns } = adaptBackendMessage({ type })
      expect(bumpRuns).toBe(true)
    })
  }
})

describe('auto-drive WebSocket events', () => {
  it.each(['drive_started', 'drive_progress', 'drive_stopped'])('%s bumps runs and drive', (type) => {
    const { events, bumpRuns, bumpDrive } = adaptBackendMessage(msg(type, { drive: { enabled: true } }))
    expect(events).toHaveLength(0)
    expect(bumpRuns).toBe(true)
    expect(bumpDrive).toBe(true)
  })
})

describe('unknown types', () => {
  it('returns empty events and no bumpRuns for unrecognised type', () => {
    const { events, bumpRuns } = adaptBackendMessage({ type: 'some_unknown_event', data: {} })
    expect(events).toHaveLength(0)
    expect(bumpRuns).toBe(false)
  })
})
