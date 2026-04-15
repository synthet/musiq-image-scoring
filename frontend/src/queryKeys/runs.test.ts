import { describe, expect, it } from 'vitest'
import {
  RUNS_ACTIVE_QUERY_KEY,
  RUNS_QUERY_ROOT,
  runDetailQueryKey,
  runStagesQueryKey,
} from './runs'

describe('runs query keys', () => {
  it('run detail key is stable two-tuple (id only, no live version)', () => {
    expect(runDetailQueryKey(42)).toEqual(['run', 42])
    expect(runDetailQueryKey(42).length).toBe(2)
  })

  it('run stages key is stable two-tuple (id only, no live version)', () => {
    expect(runStagesQueryKey(99)).toEqual(['run-stages', 99])
    expect(runStagesQueryKey(99).length).toBe(2)
  })

  it('list invalidation root is a single-segment prefix for all runs* list queries', () => {
    expect(RUNS_QUERY_ROOT).toEqual(['runs'])
  })

  it('header active-runs query key is stable (no version segment)', () => {
    expect(RUNS_ACTIVE_QUERY_KEY).toEqual(['runs-active'])
    expect(RUNS_ACTIVE_QUERY_KEY.length).toBe(1)
  })
})
