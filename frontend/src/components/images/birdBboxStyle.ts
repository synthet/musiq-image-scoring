import { LABEL_COLORS } from '@/constants/labelColors'

type Rgb = [number, number, number]

function parseHex(hex: string): Rgb {
  const h = hex.replace('#', '')
  return [
    Number.parseInt(h.slice(0, 2), 16),
    Number.parseInt(h.slice(2, 4), 16),
    Number.parseInt(h.slice(4, 6), 16),
  ]
}

function lerpChannel(a: number, b: number, t: number): number {
  return Math.round(a + (b - a) * t)
}

function lerpRgb(a: Rgb, b: Rgb, t: number): Rgb {
  return [lerpChannel(a[0], b[0], t), lerpChannel(a[1], b[1], t), lerpChannel(a[2], b[2], t)]
}

/** Color Label endpoints; orange / yellow-green come from mid-segment lerps. */
const RED = parseHex(LABEL_COLORS.red)
const YELLOW = parseHex(LABEL_COLORS.yellow)
const GREEN = parseHex(LABEL_COLORS.green)

const STOPS: { t: number; rgb: Rgb }[] = [
  { t: 0, rgb: RED },
  { t: 0.25, rgb: lerpRgb(RED, YELLOW, 0.5) },
  { t: 0.5, rgb: YELLOW },
  { t: 0.75, rgb: lerpRgb(YELLOW, GREEN, 0.5) },
  { t: 1, rgb: GREEN },
]

/**
 * Continuous red→orange→yellow→yellow-green→green border color from Color Label hexes,
 * with opacity rising with confidence.
 */
export function birdBboxBorderCss(conf: number): string {
  const t = Number.isFinite(conf) ? Math.min(1, Math.max(0, conf)) : 0
  let rgb = STOPS[0].rgb
  for (let i = 0; i < STOPS.length - 1; i++) {
    const a = STOPS[i]
    const b = STOPS[i + 1]
    if (t <= b.t || i === STOPS.length - 2) {
      const span = b.t - a.t
      const local = span > 0 ? (t - a.t) / span : 0
      rgb = lerpRgb(a.rgb, b.rgb, Math.min(1, Math.max(0, local)))
      break
    }
  }
  const alpha = Math.round((0.35 + 0.65 * t) * 1000) / 1000
  return `rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, ${alpha})`
}
