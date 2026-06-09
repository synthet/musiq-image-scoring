import { Link } from 'react-router-dom'
import { clsx } from 'clsx'
import { ExternalLink, Layers } from 'lucide-react'
import { previewSrc, type CullingStack } from '../api/culling'
import { stackPath } from '@/utils/routes'

interface StackCardProps {
  stack: CullingStack
  active: boolean
  onSelect: () => void
  onOpenLoupe: () => void
}

export function StackCard({ stack, active, onSelect, onOpenLoupe }: StackCardProps) {
  const src = stack.cover_path ? previewSrc(stack.cover_path) : null
  return (
    <button
      type="button"
      onClick={onSelect}
      onDoubleClick={onOpenLoupe}
      className={clsx(
        'group relative flex w-full flex-col overflow-hidden rounded border bg-bg-secondary text-left transition-colors',
        active
          ? 'border-accent ring-1 ring-accent/40'
          : 'border-border-muted hover:border-border',
      )}
      title={stack.name ?? `Stack ${stack.id}`}
    >
      <div className="relative aspect-square w-full bg-bg-primary">
        {src ? (
          <img
            src={src}
            alt={stack.name ?? `Stack ${stack.id}`}
            loading="lazy"
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-text-muted">
            <Layers size={28} />
          </div>
        )}
        {stack.image_count > 1 && (
          <span className="absolute right-1.5 top-1.5 inline-flex items-center gap-1 rounded bg-bg-primary/85 px-1.5 py-0.5 text-[10px] font-medium text-text-secondary backdrop-blur">
            <Layers size={10} />
            {stack.image_count}
          </span>
        )}
      </div>
      <div className="flex items-center justify-between gap-2 px-2 py-1.5 text-xs">
        <span className="truncate text-text-primary">{stack.name ?? `Stack ${stack.id}`}</span>
        <span className="flex items-center gap-1 shrink-0">
          {stack.sort_val != null && Number.isFinite(stack.sort_val) && (
            <span className="tabular-nums text-text-muted">{Math.round(stack.sort_val * 100)}%</span>
          )}
          <Link
            to={stackPath(stack.id)}
            onClick={(e) => e.stopPropagation()}
            onDoubleClick={(e) => e.stopPropagation()}
            className="text-text-muted hover:text-accent transition-colors"
            title={`Open stack #${stack.id}`}
          >
            <ExternalLink size={12} />
          </Link>
        </span>
      </div>
    </button>
  )
}
