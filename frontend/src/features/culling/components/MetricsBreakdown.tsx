import { memo } from 'react'
import { clsx } from 'clsx'
import { PRODUCTION_MODEL_DISPLAY_ORDER, SCORE_LABELS } from '@/constants/scoreModels'
import type { CullingStackImage } from '../api/culling'

interface MetricsBreakdownProps {
  image: CullingStackImage
}

interface ScoreRow {
  key: string
  label: string
  value: number | null | undefined
}

function pct(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—'
  return `${Math.round(v * 100)}%`
}

function fillTone(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return 'bg-text-muted/40'
  if (v >= 0.8) return 'bg-score-gold'
  if (v >= 0.5) return 'bg-accent'
  return 'bg-text-muted'
}

interface ScoreBarProps {
  label: string
  value: number | null | undefined
  /** Visually distinguish composite vs. model rows. */
  size?: 'lg' | 'sm'
}

function ScoreBar({ label, value, size = 'lg' }: ScoreBarProps) {
  const has = value != null && Number.isFinite(value)
  const widthPct = has ? Math.max(0, Math.min(1, value as number)) * 100 : 0
  return (
    <div className="grid grid-cols-[5rem_1fr_2.5rem] items-center gap-2">
      <span
        className={clsx(
          'truncate text-text-muted',
          size === 'lg' ? 'text-xs' : 'text-[10px]',
        )}
      >
        {label}
      </span>
      <div
        className={clsx(
          'overflow-hidden rounded bg-bg-elevated',
          size === 'lg' ? 'h-1.5' : 'h-1',
        )}
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={has ? Math.round(widthPct) : 0}
        aria-label={label}
      >
        <div
          className={clsx('h-full rounded transition-all duration-200', fillTone(value))}
          style={{ width: `${widthPct}%` }}
        />
      </div>
      <span
        className={clsx(
          'text-right tabular-nums text-text-secondary',
          size === 'lg' ? 'text-xs' : 'text-[10px]',
        )}
      >
        {pct(value)}
      </span>
    </div>
  )
}

function MetricsBreakdownInner({ image }: MetricsBreakdownProps) {
  const composites: ScoreRow[] = [
    { key: 'general', label: 'General', value: image.score_general ?? null },
    { key: 'technical', label: 'Technical', value: image.score_technical ?? null },
    { key: 'aesthetic', label: 'Aesthetic', value: image.score_aesthetic ?? null },
  ]

  // CullingStackImage has no index signature; route the dynamic score lookups
  // through `unknown` to satisfy TS2352.
  const scores = image as unknown as Record<string, number | null | undefined>
  const models: ScoreRow[] = [
    ...PRODUCTION_MODEL_DISPLAY_ORDER.map((key) => ({
      key,
      label: SCORE_LABELS[key] ?? key,
      value: scores[`score_${key}`] ?? null,
    })),
    {
      key: 'clip_quality_v0',
      label: SCORE_LABELS.clip_quality_v0,
      value: scores.clip_quality_v0_score ?? scores.clip_quality_v0 ?? null,
    },
  ]

  return (
    <div className="rounded border border-border-muted bg-bg-secondary p-3">
      <div className="mb-2 text-[11px] font-medium uppercase tracking-wide text-text-muted">
        Quality
      </div>
      <div className="space-y-1.5">
        {composites.map((row) => (
          <ScoreBar key={row.key} label={row.label} value={row.value} />
        ))}
      </div>
      <details className="group mt-3 rounded bg-bg-tertiary p-2 text-xs">
        <summary className="cursor-pointer select-none text-text-secondary outline-none transition-colors hover:text-text-primary">
          Model breakdown
        </summary>
        <div className="mt-2 space-y-1">
          {models.map((row) => (
            <ScoreBar key={row.key} label={row.label} value={row.value} size="sm" />
          ))}
        </div>
      </details>
    </div>
  )
}

export const MetricsBreakdown = memo(MetricsBreakdownInner, (prev, next) => prev.image.id === next.image.id)
