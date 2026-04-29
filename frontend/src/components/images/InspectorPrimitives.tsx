import { useState, type ReactNode } from 'react'
import { clsx } from 'clsx'
import { ChevronDown, ChevronRight } from 'lucide-react'
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
  renderValue,
}: {
  entries: [string, unknown][]
  dense?: boolean
  renderValue?: (key: string, value: unknown) => ReactNode
}) {
  const sorted = [...entries].sort(([a], [b]) => a.localeCompare(b))
  return (
    <div
      className={clsx(
        'border border-[#3c3c3c] rounded overflow-hidden',
        dense ? 'text-[11px]' : 'text-xs',
      )}
    >
      <table className="w-full border-collapse">
        <tbody>
          {sorted.map(([k, v]) => (
            <tr key={k} className="border-b border-[#3c3c3c] last:border-b-0 hover:bg-[#2a2a2a]">
              <td className="align-top text-[#9d9d9d] px-2 py-1 w-[38%] border-r border-[#3c3c3c] font-mono shrink-0">
                {k}
              </td>
              <td className="align-top text-[#cccccc] px-2 py-1 font-mono whitespace-pre-wrap break-all">
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
  children,
}: {
  title: string
  subtitle?: string
  defaultOpen?: boolean
  badge?: string
  children: ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen ?? true)
  return (
    <div className="border border-[#3c3c3c] rounded bg-[#252526] overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-[#2d2d30] transition-colors"
      >
        <span className="text-[#6d6d6d]">{open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}</span>
        <span className="text-sm font-semibold text-[#cccccc]">{title}</span>
        {badge && (
          <span className="text-[10px] px-1.5 py-0 rounded bg-[#3c3c3c] text-[#9d9d9d] font-mono">{badge}</span>
        )}
        {subtitle && <span className="text-[10px] text-[#6d6d6d] ml-auto truncate">{subtitle}</span>}
      </button>
      {open && <div className="px-3 pb-3 border-t border-[#3c3c3c] pt-2">{children}</div>}
    </div>
  )
}

