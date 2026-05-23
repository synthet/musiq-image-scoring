import { describe, expect, it } from 'vitest'
import { DB_PAGE_SIZES, DEFAULT_API_DB_MAX_ROWS } from './db'

describe('dbApi constants', () => {
  it('exposes page sizes for pagination UI', () => {
    expect(DB_PAGE_SIZES).toEqual([25, 50, 100, 250])
  })

  it('default max rows matches backend default', () => {
    expect(DEFAULT_API_DB_MAX_ROWS).toBe(5000)
  })
})
