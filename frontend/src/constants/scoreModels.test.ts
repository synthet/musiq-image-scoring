import { describe, expect, it } from 'vitest'
import { resolveVisibleModels } from './scoreModels'

describe('resolveVisibleModels', () => {
  it('includes production models and clip_quality_v0, hides deprecated models', () => {
    const models = resolveVisibleModels({
      spaq: { enabled: true, shadow: false },
      ava: { enabled: true, shadow: false },
      liqe: { enabled: true, shadow: false },
      topiq: { enabled: true, shadow: false },
      arniqa: { enabled: true, shadow: false },
      cursor: { enabled: false, shadow: false },
      claude: { enabled: false, shadow: true },
    })

    expect(models).toEqual([
      'spaq',
      'ava',
      'liqe',
      'topiq',
      'arniqa',
      'clip_quality_v0',
    ])
    expect(models).not.toContain('cursor')
    expect(models).not.toContain('claude')
    expect(models).not.toContain('koniq')
    expect(models).not.toContain('paq2piq')
  })
})
