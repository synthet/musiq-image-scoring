import { describe, it, expect, vi, afterEach } from 'vitest'
import { parsePersistedRunLog } from './runLog'

describe('parsePersistedRunLog', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('returns empty array when there are no non-empty lines', () => {
    expect(parsePersistedRunLog('', 1, null)).toEqual([])
    expect(parsePersistedRunLog('\n\n', 1, null)).toEqual([])
  })

  it('splits on newlines and trims end of each line', () => {
    const lines = parsePersistedRunLog(' first \n second  \n', 42, '2026-01-01T00:00:00.000Z')
    expect(lines).toHaveLength(2)
    expect(lines[0].message).toBe(' first')
    expect(lines[1].message).toBe(' second')
    expect(lines[0].run_id).toBe(42)
    expect(lines[0].type).toBe('log_line')
    expect(lines[0].level).toBe('INFO')
  })

  it('uses startedAt as base time for synthetic timestamps', () => {
    const lines = parsePersistedRunLog('a\nb', 1, '2026-06-15T12:00:00.000Z')
    const t0 = new Date(lines[0].ts).getTime()
    const t1 = new Date(lines[1].ts).getTime()
    expect(t1 - t0).toBe(1)
  })

  it('uses Date.now when startedAt is null', () => {
    vi.spyOn(Date, 'now').mockReturnValue(1_700_000_000_000)
    const lines = parsePersistedRunLog('only', 7, null)
    expect(lines).toHaveLength(1)
    expect(new Date(lines[0].ts).getTime()).toBe(1_700_000_000_000)
  })
})
