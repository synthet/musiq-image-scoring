import { describe, it, expect } from 'vitest'
import { parseWebuiLogLine } from './statusLogParse'
import {
  matchLogViewportFilter,
  formatViewerLogTime,
} from './logViewportFilter'

describe('matchLogViewportFilter', () => {
  it('INFO hides DEBUG', () => {
    expect(matchLogViewportFilter('DEBUG', 'INFO')).toBe(false)
    expect(matchLogViewportFilter('INFO', 'INFO')).toBe(true)
  })

  it('WARNING includes ERROR', () => {
    expect(matchLogViewportFilter('ERROR', 'WARNING')).toBe(true)
    expect(matchLogViewportFilter('WARNING', 'WARNING')).toBe(true)
    expect(matchLogViewportFilter('INFO', 'WARNING')).toBe(false)
  })
})

describe('formatViewerLogTime', () => {
  it('parses Python logging-style timestamp', () => {
    const t = formatViewerLogTime('2026-04-14 03:46:20,487')
    expect(t).toMatch(/\d/)
  })
})

describe('viewport filter with parsed lines', () => {
  it('filters INFO preset on parsed webui lines', () => {
    const parsed = [
      parseWebuiLogLine('plain info line'),
      parseWebuiLogLine('2026-01-01 00:00:00,000 - m - WARNING - msg'),
      parseWebuiLogLine('2026-01-01 00:00:01,000 - m - DEBUG - x'),
    ]
    expect(parsed.filter((p) => matchLogViewportFilter(p.level, 'INFO')).length).toBe(2)
    expect(parsed.filter((p) => matchLogViewportFilter(p.level, 'ALL')).length).toBe(3)
  })
})
