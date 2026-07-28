/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { LABEL_COLORS } from '@/constants/labelColors'
import { BirdBoxPreview } from './BirdBoxPreview'
import { birdBboxBorderCss } from './birdBboxStyle'
import type { BirdBoundingBox } from '@/types/api'

/** Real values from image 202242 (DSC_2095.NEF). */
const bbox: BirdBoundingBox = {
  x1: 884,
  y1: 377,
  x2: 2123,
  y2: 1672,
  conf: 0.9138,
  img_w: 3936,
  img_h: 2624,
}

function checkbox(): HTMLInputElement {
  return screen.getByRole('checkbox') as HTMLInputElement
}

function parseRgba(css: string): { r: number; g: number; b: number; a: number } {
  const m = css.match(/^rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)$/)
  if (!m) throw new Error(`expected rgba(...), got ${css}`)
  return { r: +m[1], g: +m[2], b: +m[3], a: +m[4] }
}

function hexRgb(hex: string): { r: number; g: number; b: number } {
  const h = hex.replace('#', '')
  return {
    r: Number.parseInt(h.slice(0, 2), 16),
    g: Number.parseInt(h.slice(2, 4), 16),
    b: Number.parseInt(h.slice(4, 6), 16),
  }
}

describe('birdBboxBorderCss', () => {
  it('maps conf 0 to label red with alpha 0.35', () => {
    const { r, g, b, a } = parseRgba(birdBboxBorderCss(0))
    expect({ r, g, b }).toEqual(hexRgb(LABEL_COLORS.red))
    expect(a).toBeCloseTo(0.35, 5)
  })

  it('maps conf 0.5 to label yellow with mid alpha', () => {
    const { r, g, b, a } = parseRgba(birdBboxBorderCss(0.5))
    expect({ r, g, b }).toEqual(hexRgb(LABEL_COLORS.yellow))
    expect(a).toBeCloseTo(0.675, 5)
  })

  it('maps conf 1 to label green with alpha 1', () => {
    const { r, g, b, a } = parseRgba(birdBboxBorderCss(1))
    expect({ r, g, b }).toEqual(hexRgb(LABEL_COLORS.green))
    expect(a).toBeCloseTo(1, 5)
  })

  it('maps conf 0.25 to orange between red and yellow', () => {
    const { g } = parseRgba(birdBboxBorderCss(0.25))
    const red = hexRgb(LABEL_COLORS.red)
    const yellow = hexRgb(LABEL_COLORS.yellow)
    expect(g).toBeGreaterThan(red.g)
    expect(g).toBeLessThan(yellow.g)
  })

  it('maps conf 0.75 to yellow-green between yellow and green', () => {
    const { r } = parseRgba(birdBboxBorderCss(0.75))
    const yellow = hexRgb(LABEL_COLORS.yellow)
    const green = hexRgb(LABEL_COLORS.green)
    expect(r).toBeLessThan(yellow.r)
    expect(r).toBeGreaterThan(green.r)
  })
})

describe('BirdBoxPreview', () => {
  afterEach(() => {
    cleanup()
  })

  it('hides the overlay until the checkbox is ticked', () => {
    render(<BirdBoxPreview src="/source-image?path=a.NEF" alt="a.NEF" bbox={bbox} />)

    expect(screen.queryByTestId('bird-bbox-overlay')).toBeNull()
    fireEvent.click(checkbox())
    expect(screen.getByTestId('bird-bbox-overlay')).not.toBeNull()
  })

  it('positions the box as a fraction of the detector image size', () => {
    render(<BirdBoxPreview src="/source-image?path=a.NEF" alt="a.NEF" bbox={bbox} />)
    fireEvent.click(checkbox())

    const overlay = screen.getByTestId('bird-bbox-overlay')
    expect(overlay.style.left).toBe(`${(884 / 3936) * 100}%`)
    expect(overlay.style.top).toBe(`${(377 / 2624) * 100}%`)
    expect(overlay.style.width).toBe(`${((2123 - 884) / 3936) * 100}%`)
    expect(overlay.style.height).toBe(`${((1672 - 377) / 2624) * 100}%`)
  })

  it('applies an rgba confidence border when shown', () => {
    render(<BirdBoxPreview src="/source-image?path=a.NEF" alt="a.NEF" bbox={bbox} />)
    fireEvent.click(checkbox())

    const overlay = screen.getByTestId('bird-bbox-overlay')
    expect(overlay.style.border).toBe(`2px solid ${birdBboxBorderCss(bbox.conf)}`)
    expect(overlay.style.border).toContain('rgba(')
  })

  it('disables the checkbox when the image has no detection', () => {
    render(<BirdBoxPreview src="/source-image?path=a.NEF" alt="a.NEF" bbox={null} />)

    expect(checkbox().disabled).toBe(true)
    expect(screen.getByText('(no detection)')).not.toBeNull()
    expect(screen.queryByTestId('bird-bbox-overlay')).toBeNull()
  })

  it('treats the not-detected sentinel as undrawable', () => {
    render(
      <BirdBoxPreview src="/source-image?path=a.NEF" alt="a.NEF" bbox={{ detected: false }} />,
    )

    expect(checkbox().disabled).toBe(true)
    expect(screen.getByText('(no detection)')).not.toBeNull()
    expect(screen.queryByTestId('bird-bbox-overlay')).toBeNull()
  })

  it('treats a box with zero reference dimensions as undrawable', () => {
    render(
      <BirdBoxPreview src="/source-image?path=a.NEF" alt="a.NEF" bbox={{ ...bbox, img_w: 0, img_h: 0 }} />,
    )

    expect(checkbox().disabled).toBe(true)
    expect(screen.queryByTestId('bird-bbox-overlay')).toBeNull()
  })
})
