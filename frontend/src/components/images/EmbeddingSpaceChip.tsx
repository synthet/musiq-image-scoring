import { clsx } from 'clsx'
import { Check, X } from 'lucide-react'
import {
  ALL_EMBEDDING_SPACE_CODES,
  EmbeddingSpaceIcon,
  EMBEDDING_SPACE_COLORS,
  EMBEDDING_SPACE_LABELS,
  PRIMARY_EMBEDDING_SPACE_CODES,
} from '@synthet/image-scoring-design'

function embeddingLabel(code: string): string {
  return EMBEDDING_SPACE_LABELS[code] ?? code
}

function embeddingColor(code: string): string {
  return EMBEDDING_SPACE_COLORS[code] ?? 'var(--color-text-muted)'
}

export function EmbeddingSpaceChip({
  variant,
  code,
  present,
}: {
  variant: 'table' | 'inspector'
  code: string
  present: boolean
}) {
  const label = embeddingLabel(code)
  const color = embeddingColor(code)

  if (variant === 'table') {
    return (
      <div
        data-code={code}
        className={clsx(
          'p-1 rounded-sm transition-colors hover:bg-[var(--color-bg-elevated)]',
          present ? 'opacity-100' : 'opacity-30',
        )}
        title={`${label}: ${present ? 'Present' : 'Missing'}`}
      >
        <EmbeddingSpaceIcon
          code={code}
          size={14}
          muted={!present}
          color={present ? color : undefined}
        />
      </div>
    )
  }

  return (
    <div
      className={clsx(
        'flex items-center gap-1.5 px-2 py-1 rounded border text-[11px]',
        present
          ? 'border-[var(--color-border)] bg-[var(--color-bg-secondary)]'
          : 'border-[var(--color-border-muted)] opacity-50',
      )}
      title={`${label} (${code})`}
    >
      <EmbeddingSpaceIcon
        code={code}
        size={14}
        muted={!present}
        color={present ? color : undefined}
      />
      <span className="text-[var(--color-text-primary)]">{label}</span>
      {present ? (
        <Check size={12} className="text-[var(--color-success)]" />
      ) : (
        <X size={12} className="text-[var(--color-text-muted)]" />
      )}
    </div>
  )
}

export function ImageEmbeddingsRow({
  embeddings,
}: {
  embeddings?: Record<string, boolean> | null
}) {
  const present = embeddings ?? {}

  return (
    <div className="flex items-center gap-0.5 flex-wrap justify-start">
      {ALL_EMBEDDING_SPACE_CODES.map((code) => (
        <EmbeddingSpaceChip
          key={code}
          variant="table"
          code={code}
          present={!!present[code]}
        />
      ))}
    </div>
  )
}

export function EmbeddingsInspectorChips({
  embeddings,
}: {
  embeddings?: Record<string, boolean> | null
}) {
  const present = embeddings ?? {}

  return (
    <div className="flex flex-wrap gap-2">
      {ALL_EMBEDDING_SPACE_CODES.map((code) => (
        <EmbeddingSpaceChip
          key={code}
          variant="inspector"
          code={code}
          present={!!present[code]}
        />
      ))}
    </div>
  )
}

export { ALL_EMBEDDING_SPACE_CODES, PRIMARY_EMBEDDING_SPACE_CODES }
