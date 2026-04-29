/**
 * Photo color labels (Lightroom-style) and phase status colors.
 *
 * Source of truth for both is `docs/design/DESIGN_SYSTEM.md`. Photo labels
 * mirror the gallery `--label-*` tokens defined in
 * `image-scoring-gallery/src/styles/tokens.css`.
 */

/**
 * Lightroom-style photo color labels stored on `image.label`.
 * These are user-facing photo metadata, not UI status colors.
 */
export const LABEL_COLORS: Record<string, string> = {
  red: '#e53935',
  yellow: '#fdd835',
  green: '#43a047',
  blue: '#1e88e5',
  purple: '#8e24aa',
}

/**
 * Fallback color used when an image has no label or the label is unknown.
 * Matches `--color-text-muted` in `frontend/src/index.css`.
 */
export const LABEL_FALLBACK_COLOR = '#6d6d6d'

/**
 * Canonical phase / pipeline status colors. Mirrors the `--color-*` tokens in
 * `frontend/src/index.css` and the table in `docs/design/DESIGN_SYSTEM.md`.
 */
export const PHASE_STATUS_COLORS = {
  pending: '#6d6d6d',
  queued: '#9d9d9d',
  running: '#007acc',
  done: '#89d185',
  skipped: '#6d6d6d',
  failed: '#f44747',
  canceled: '#f44747',
  paused: '#cca700',
  partial: '#cca700',
  notStarted: '#6d6d6d',
} as const

export type PhaseStatusColorKey = keyof typeof PHASE_STATUS_COLORS

/**
 * Map an arbitrary phase / image-phase status string to a canonical color.
 * Unknown values fall back to the muted ("not started") tone.
 */
export function phaseStatusColor(status: string | null | undefined): string {
  if (!status) return PHASE_STATUS_COLORS.notStarted
  const s = status.toLowerCase()
  if (s === 'not_started') return PHASE_STATUS_COLORS.notStarted
  if (s === 'done' || s === 'completed') return PHASE_STATUS_COLORS.done
  if (s === 'running') return PHASE_STATUS_COLORS.running
  if (s === 'failed') return PHASE_STATUS_COLORS.failed
  if (s === 'canceled' || s === 'cancelled') return PHASE_STATUS_COLORS.canceled
  if (s === 'paused') return PHASE_STATUS_COLORS.paused
  if (s === 'pending' || s === 'queued') return PHASE_STATUS_COLORS.queued
  if (s === 'skipped') return PHASE_STATUS_COLORS.skipped
  if (s === 'partial' || s === 'interrupted' || s === 'cancel_requested') {
    return PHASE_STATUS_COLORS.partial
  }
  return PHASE_STATUS_COLORS.notStarted
}
