import { describe, expect, it } from 'vitest'
import { dbExplorerImagePath, dbExplorerImageSql, dbExplorerPath } from './routes'

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

describe('dbExplorerImagePath', () => {
  it('deep-links to images table with id query param', () => {
    expect(dbExplorerImagePath(23970)).toBe('/db/images?id=23970')
    expect(dbExplorerImagePath('42')).toBe('/db/images?id=42')
  })

  it('falls back to images table path for invalid ids', () => {
    expect(dbExplorerImagePath(0)).toBe('/db/images')
    expect(dbExplorerImagePath(-1)).toBe('/db/images')
    expect(dbExplorerImagePath('abc')).toBe('/db/images')
  })
})

describe('dbExplorerImageSql', () => {
  it('builds a filtered images query', () => {
    expect(dbExplorerImageSql(23970)).toBe('SELECT * FROM "images" WHERE id = 23970')
  })

  it('returns null for invalid ids', () => {
    expect(dbExplorerImageSql(0)).toBeNull()
    expect(dbExplorerImageSql('x')).toBeNull()
  })
})
