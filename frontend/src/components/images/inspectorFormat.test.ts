import { describe, expect, it } from 'vitest'
import { formatInspectorValue, formatScoreValue } from './InspectorPrimitives'

describe('formatScoreValue', () => {
  it('formats 0–1 scores as percent including integer 1', () => {
    expect(formatScoreValue(1)).toBe('100.00%')
    expect(formatScoreValue(0.9999)).toBe('99.99%')
    expect(formatScoreValue(0)).toBe('0.00%')
  })

  it('leaves out-of-range numbers as plain strings', () => {
    expect(formatScoreValue(1.5)).toBe('1.5')
    expect(formatScoreValue(-0.1)).toBe('-0.1')
  })
})

describe('formatInspectorValue', () => {
  it('does not percent-format integer 1 (non-score fields)', () => {
    expect(formatInspectorValue(1)).toBe('1')
  })

  it('formats fractional values in (0,1) as percent', () => {
    expect(formatInspectorValue(0.76)).toBe('76.00%')
  })
})
