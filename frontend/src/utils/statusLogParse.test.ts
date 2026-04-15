import { describe, it, expect } from 'vitest'
import { parseWebuiLogLine, parseDebugLogLine } from './statusLogParse'

describe('parseWebuiLogLine', () => {
  it('parses standard Python logging', () => {
    const line =
      '2026-04-14 03:46:20,487 - image_scoring.performance - WARNING - [SLOW REQUEST] GET /api/status/logs'
    const p = parseWebuiLogLine(line)
    expect(p.level).toBe('WARNING')
    expect(p.message).toContain('[SLOW REQUEST]')
    expect(p.ts).toBeDefined()
  })

  it('parses uvicorn-style LEVEL: prefix', () => {
    const line = 'INFO:     127.0.0.1:7860 - "GET /api/health HTTP/1.1" 200 OK'
    const p = parseWebuiLogLine(line)
    expect(p.level).toBe('INFO')
    expect(p.message).toContain('127.0.0.1')
  })

  it('maps CRITICAL to ERROR', () => {
    const line = '2026-01-01 00:00:00,000 - root - CRITICAL - boom'
    expect(parseWebuiLogLine(line).level).toBe('ERROR')
  })

  it('defaults unknown lines to INFO', () => {
    const line = 'some plain text without level markers'
    const p = parseWebuiLogLine(line)
    expect(p.level).toBe('INFO')
    expect(p.message).toBe(line)
  })
})

describe('parseDebugLogLine', () => {
  it('parses JSON with level', () => {
    const line = JSON.stringify({ level: 'error', message: 'failed' })
    const p = parseDebugLogLine(line)
    expect(p.level).toBe('ERROR')
    expect(p.message).toBe('failed')
  })

  it('parses JSON without level as INFO', () => {
    const line = JSON.stringify({ foo: 1, bar: 'x' })
    const p = parseDebugLogLine(line)
    expect(p.level).toBe('INFO')
    expect(p.message).toContain('foo')
  })

  it('falls back for non-JSON', () => {
    const line = 'not json at all'
    const p = parseDebugLogLine(line)
    expect(p.level).toBe('INFO')
    expect(p.message).toBe('not json at all')
  })
})
