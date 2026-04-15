import { describe, it, expect } from 'vitest'
import { parseApiErrorDetail } from './client'

describe('parseApiErrorDetail', () => {
  it('returns plain text unchanged', () => {
    expect(parseApiErrorDetail('Something broke')).toBe('Something broke')
  })

  it('extracts string detail from JSON body', () => {
    expect(parseApiErrorDetail('{"detail":"Not found"}')).toBe('Not found')
  })

  it('joins array detail entries', () => {
    const body = JSON.stringify({ detail: ['first', { x: 1 }] })
    expect(parseApiErrorDetail(body)).toBe('first; {"x":1}')
  })

  it('falls back to full text when JSON has no usable detail', () => {
    expect(parseApiErrorDetail('{"foo":1}')).toBe('{"foo":1}')
  })

  it('returns raw text when not JSON', () => {
    expect(parseApiErrorDetail('not json {')).toBe('not json {')
  })

  it('returns Request failed for empty trimmed input', () => {
    expect(parseApiErrorDetail('   ')).toBe('Request failed')
  })
})
