import { describe, expect, it } from 'vitest'
import { dbExplorerPath } from './routes'

describe('dbExplorerPath', () => {
  it('returns base path when table is omitted', () => {
    expect(dbExplorerPath()).toBe('/db')
    expect(dbExplorerPath(null)).toBe('/db')
  })

  it('encodes table names for deep links', () => {
    expect(dbExplorerPath('images')).toBe('/db/images')
    expect(dbExplorerPath('my table')).toBe('/db/my%20table')
  })
})
