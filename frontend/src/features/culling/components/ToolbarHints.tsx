import { Keyboard, X } from 'lucide-react'

interface ToolbarHintsProps {
  open: boolean
  onClose: () => void
}

const ROWS: ReadonlyArray<{ keys: string; action: string }> = [
  { keys: 'P', action: 'Pick' },
  { keys: 'X', action: 'Reject' },
  { keys: 'U', action: 'Unflag' },
  { keys: '←  →', action: 'Previous / next stack' },
  { keys: '[  ] or , .', action: 'Cycle images in stack' },
  { keys: 'E / Enter', action: 'Toggle Survey ↔ Loupe' },
  { keys: 'Z / Space', action: 'Toggle 100% zoom' },
  { keys: '?', action: 'Toggle this cheat sheet' },
]

export function ToolbarHints({ open, onClose }: ToolbarHintsProps) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-bg-primary/70 backdrop-blur-sm">
      <div className="w-full max-w-md rounded border border-border-muted bg-bg-secondary shadow-2xl">
        <header className="flex items-center justify-between border-b border-border-muted px-4 py-2">
          <div className="flex items-center gap-2 text-sm text-text-primary">
            <Keyboard size={14} className="text-accent-bright" />
            Keyboard shortcuts
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-text-muted transition-colors hover:bg-bg-elevated hover:text-text-primary"
            aria-label="Close shortcuts"
          >
            <X size={14} />
          </button>
        </header>
        <dl className="grid grid-cols-[8rem_1fr] gap-y-1 px-4 py-3 text-xs">
          {ROWS.map((r) => (
            <RowEntry key={r.keys} keys={r.keys} action={r.action} />
          ))}
        </dl>
      </div>
    </div>
  )
}

function RowEntry({ keys, action }: { keys: string; action: string }) {
  return (
    <>
      <dt>
        <kbd className="rounded border border-border-muted bg-bg-tertiary px-1.5 py-0.5 font-mono text-[10px] text-text-secondary">
          {keys}
        </kbd>
      </dt>
      <dd className="text-text-secondary">{action}</dd>
    </>
  )
}
