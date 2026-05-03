/**
 * Quality ranking utilities for the Culling workspace.
 *
 * Primary key: score_general (descending — higher is better).
 * When two images tie on the model score, photographers fall back on
 * camera-craft heuristics:
 *   1. Lower ISO wins              — less noise
 *   2. Larger pixel area wins      — more detail / less compression
 *   3. Shorter exposure wins       — less motion blur
 *   4. Stable tie-break by id      — keep ordering deterministic
 */

export interface QualitySortable {
  id: number
  score_general?: number | null
  exif_iso?: number | null
  exif_exposure_time?: string | null
  exif_image_width?: number | null
  exif_image_height?: number | null
}

const EPS = 1e-6

/** EXIF stores exposure time as a string ("1/250", "0.5", "30"). */
export function parseExposureSeconds(raw: string | null | undefined): number | null {
  if (raw == null) return null
  const s = String(raw).trim()
  if (!s) return null
  if (s.includes('/')) {
    const [num, denom] = s.split('/')
    const n = Number(num)
    const d = Number(denom)
    if (!Number.isFinite(n) || !Number.isFinite(d) || d === 0) return null
    return n / d
  }
  const v = Number(s)
  return Number.isFinite(v) ? v : null
}

function pixelArea(img: QualitySortable): number {
  const w = img.exif_image_width ?? 0
  const h = img.exif_image_height ?? 0
  return (w || 0) * (h || 0)
}

/**
 * Comparator for descending quality. Lower index = better keeper candidate.
 * Used by the Survey grid (cover selection) and Loupe filmstrip ordering.
 */
export function compareByQualityDesc(a: QualitySortable, b: QualitySortable): number {
  const sa = a.score_general ?? -Infinity
  const sb = b.score_general ?? -Infinity
  if (Math.abs(sa - sb) > EPS) return sb - sa

  // Tie 1: ISO — lower wins. Treat null as worst (Infinity).
  const iso_a = a.exif_iso ?? Infinity
  const iso_b = b.exif_iso ?? Infinity
  if (iso_a !== iso_b) return iso_a - iso_b

  // Tie 2: pixel area — larger wins.
  const area_a = pixelArea(a)
  const area_b = pixelArea(b)
  if (area_a !== area_b) return area_b - area_a

  // Tie 3: exposure — shorter wins. null treated as worst.
  const exp_a = parseExposureSeconds(a.exif_exposure_time) ?? Infinity
  const exp_b = parseExposureSeconds(b.exif_exposure_time) ?? Infinity
  if (exp_a !== exp_b) return exp_a - exp_b

  // Final stable tie-break by id.
  return a.id - b.id
}

export function sortByQualityDesc<T extends QualitySortable>(items: T[]): T[] {
  return [...items].sort(compareByQualityDesc)
}
