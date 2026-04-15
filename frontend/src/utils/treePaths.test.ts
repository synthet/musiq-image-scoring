import { describe, it, expect } from 'vitest'
import { normalizeTreePath, pathTargetsRevealFolder } from './treePaths'

describe('normalizeTreePath', () => {
  it('trims and lowercases', () => {
    expect(normalizeTreePath('  /Foo/BAR  ')).toBe('/foo/bar')
  })

  it('normalises backslashes to slashes', () => {
    expect(normalizeTreePath('D:\\Photos\\2024')).toBe('d:/photos/2024')
  })

  it('strips trailing slashes', () => {
    expect(normalizeTreePath('/a/b/c///')).toBe('/a/b/c')
  })
})

describe('pathTargetsRevealFolder', () => {
  it('returns false for empty or missing targets', () => {
    expect(pathTargetsRevealFolder('/any', [])).toBe(false)
    expect(pathTargetsRevealFolder('/any', undefined)).toBe(false)
    expect(pathTargetsRevealFolder('/any', null)).toBe(false)
  })

  it('matches exact folder (case-insensitive)', () => {
    expect(pathTargetsRevealFolder('/Photos/Vacation', ['/photos/vacation'])).toBe(true)
  })

  it('matches when target is a descendant', () => {
    expect(pathTargetsRevealFolder('/Photos', ['/Photos/Vacation/June'])).toBe(true)
  })

  it('does not match sibling path that only shares a prefix without segment boundary', () => {
    expect(pathTargetsRevealFolder('/a', ['/ab'])).toBe(false)
  })

  it('does not match when target is an ancestor only', () => {
    expect(pathTargetsRevealFolder('/Photos/Vacation', ['/Photos'])).toBe(false)
  })
})
