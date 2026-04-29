import { describe, expect, it } from 'vitest'
import { splitLogMessageWithImageLinks } from '@/utils/logMessageLinks'

describe('splitLogMessageWithImageLinks', () => {
  it('returns single text segment when no token', () => {
    expect(splitLogMessageWithImageLinks('hello')).toEqual([{ kind: 'text', text: 'hello' }])
    expect(splitLogMessageWithImageLinks('')).toEqual([{ kind: 'text', text: '' }])
  })

  it('splits one [[img:id]] suffix', () => {
    expect(splitLogMessageWithImageLinks('[scoring] Scored: x.jpg - 1.00 [[img:42]]')).toEqual([
      { kind: 'text', text: '[scoring] Scored: x.jpg - 1.00 ' },
      { kind: 'image', id: 42 },
    ])
  })

  it('handles multiple tokens', () => {
    expect(splitLogMessageWithImageLinks('a [[img:1]] b [[img:2]] c')).toEqual([
      { kind: 'text', text: 'a ' },
      { kind: 'image', id: 1 },
      { kind: 'text', text: ' b ' },
      { kind: 'image', id: 2 },
      { kind: 'text', text: ' c' },
    ])
  })

  it('treats only message as text when no [[img: prefix', () => {
    expect(splitLogMessageWithImageLinks('image_id=5')).toEqual([{ kind: 'text', text: 'image_id=5' }])
  })
})
