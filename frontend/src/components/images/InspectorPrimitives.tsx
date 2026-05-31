import { useEffect, useState, type ReactNode } from 'react'
import { clsx } from 'clsx'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { formatScoreValue as formatScoreValueBase } from '@synthet/image-scoring-design'
import { LABEL_COLORS } from '@/constants/labelColors'

export function LabelBadge({ label, className }: { label: string | null | undefined; className?: string }) {
  if (!label) return <span className="text-[var(--color-text-muted)]">None</span>
  const key = label.toLowerCase()
  const color = LABEL_COLORS[key]

  if (!color) {
    return (
      <span className={clsx('px-1.5 py-0.5 rounded text-[10px] bg-[var(--color-bg-elevated)] text-[var(--color-text-primary)]', className)}>
        {label}
      </span>
    )
  }

  return (
    <span
      className={clsx('inline-flex items-center gap-1.5 px-1.5 py-0.5 rounded text-[10px] font-medium transition-all hover:brightness-110', className)}
      style={{
        backgroundColor: `${color}15`,
        color: color,
        border: `1px solid ${color}33`,
      }}
    >
      <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: color }} />
      {label}
    </span>
  )
}

/** Normalized 0–1 quality scores (including integer 1 → 100%). */
export function formatScoreValue(value: unknown): ReactNode {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'number' && Number.isFinite(value)) {
    return formatScoreValueBase(value)
  }
  return formatInspectorValue(value)
}

export function formatInspectorValue(value: unknown): ReactNode {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'number' && Number.isFinite(value)) {
    if (Math.abs(value) <= 1 && value !== 0 && !Number.isInteger(value)) {
      return `${(value * 100).toFixed(2)}%`
    }
    return String(value)
  }
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value, null, 2)
    } catch {
      return String(value)
    }
  }
  return String(value)
}

export function KeyValueTable({
  entries,
  dense,
  preserveOrder,
  renderValue,
  labelFor,
}: {
  entries: [string, unknown][]
  dense?: boolean
  /** When true, keep caller row order (e.g. logical path ordering). */
  preserveOrder?: boolean
  renderValue?: (key: string, value: unknown) => ReactNode
  labelFor?: (key: string) => string
}) {
  const sorted = preserveOrder ? entries : [...entries].sort(([a], [b]) => a.localeCompare(b))
  return (
    <div
      className={clsx(
        'border border-[var(--color-border-muted)] rounded overflow-hidden',
        dense ? 'text-[11px]' : 'text-xs',
      )}
    >
      <table className="w-full border-collapse">
        <tbody>
          {sorted.map(([k, v]) => (
            <tr
              key={k}
              className="border-b border-[var(--color-border-muted)] last:border-b-0 hover:bg-[var(--color-bg-tertiary)]"
            >
              <td className="align-top text-[var(--color-text-secondary)] px-2 py-1 w-[38%] border-r border-[var(--color-border-muted)] font-mono shrink-0">
                {labelFor ? labelFor(k) : k}
              </td>
              <td className="align-top text-[var(--color-text-primary)] px-2 py-1 font-mono whitespace-pre-wrap break-all">
                {renderValue ? renderValue(k, v) : k === 'label' ? <LabelBadge label={v as string} /> : formatInspectorValue(v)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function CollapsibleInspectorSection({
  title,
  subtitle,
  defaultOpen,
  badge,
  sectionId,
  collapseAllToken,
  children,
}: {
  title: string
  subtitle?: string
  defaultOpen?: boolean
  badge?: string
  /** Anchor id for in-page section navigation (`inspector-section-*`). */
  sectionId?: string
  /** When incremented, section collapses (Collapse all). */
  collapseAllToken?: number
  children: ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen ?? true)

  useEffect(() => {
    if (collapseAllToken != null && collapseAllToken > 0) {
      setOpen(false)
    }
  }, [collapseAllToken])

  const domId = sectionId ? `inspector-section-${sectionId}` : undefined

  return (
    <div
      id={domId}
      className="border border-[var(--color-border-muted)] rounded bg-[var(--color-bg-secondary)] overflow-hidden scroll-mt-4"
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-[var(--color-bg-tertiary)] transition-colors"
      >
        <span className="text-[var(--color-text-muted)]">
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>
        <span className="text-sm font-semibold text-[var(--color-text-primary)]">{title}</span>
        {badge && (
          <span className="text-[10px] px-1.5 py-0 rounded bg-[var(--color-bg-elevated)] text-[var(--color-text-secondary)] font-mono">
            {badge}
          </span>
        )}
        {subtitle && (
          <span className="text-[10px] text-[var(--color-text-muted)] ml-auto truncate">{subtitle}</span>
        )}
      </button>
      {open && (
        <div className="px-3 pb-3 border-t border-[var(--color-border-muted)] pt-2">{children}</div>
      )}
    </div>
  )
}

