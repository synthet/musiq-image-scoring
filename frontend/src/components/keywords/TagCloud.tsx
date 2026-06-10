import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { keywordsApi, type KeywordCloudEntry, type KeywordCloudKind } from '@/api/keywords'

const MIN_FONT = 12
const MAX_FONT = 38

export interface TagCloudProps {
  kind: KeywordCloudKind
  limit?: number
  /** Destination route for a clicked tag (e.g. speciesImagesPath / keywordImagesPath). */
  hrefFor: (entry: KeywordCloudEntry) => string
  /** Display label for a tag; defaults to keyword_display or keyword_norm. */
  displayFor?: (entry: KeywordCloudEntry) => string
  emptyMessage?: string
}

function defaultDisplay(entry: KeywordCloudEntry): string {
  return (entry.keyword_display?.trim() || entry.keyword_norm || '').trim()
}

/** Log-scale a count into a font size between MIN_FONT and MAX_FONT. */
function fontSizeFor(count: number, minCount: number, maxCount: number): number {
  if (maxCount <= minCount) return (MIN_FONT + MAX_FONT) / 2
  const lo = Math.log(minCount + 1)
  const hi = Math.log(maxCount + 1)
  const t = (Math.log(count + 1) - lo) / (hi - lo)
  return Math.round(MIN_FONT + t * (MAX_FONT - MIN_FONT))
}

export function TagCloud({
  kind,
  limit = 200,
  hrefFor,
  displayFor = defaultDisplay,
  emptyMessage = 'No keywords yet.',
}: TagCloudProps) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['keyword-cloud', kind, limit],
    queryFn: () => keywordsApi.cloud(kind, { limit }),
  })

  const entries = data?.keywords ?? []

  const { minCount, maxCount } = useMemo(() => {
    if (entries.length === 0) return { minCount: 0, maxCount: 0 }
    let min = Infinity
    let max = 0
    for (const e of entries) {
      const c = e.count ?? 0
      if (c < min) min = c
      if (c > max) max = c
    }
    return { minCount: min === Infinity ? 0 : min, maxCount: max }
  }, [entries])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 size={20} className="text-[var(--color-accent-bright)] animate-spin" />
      </div>
    )
  }

  if (isError) {
    return <p className="p-6 text-sm text-[var(--color-danger)]">Failed to load keywords.</p>
  }

  if (entries.length === 0) {
    return <p className="p-6 text-sm text-[var(--color-text-muted)]">{emptyMessage}</p>
  }

  return (
    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-2 p-6">
      {entries.map((entry) => {
        const label = displayFor(entry)
        const size = fontSizeFor(entry.count ?? 0, minCount, maxCount)
        return (
          <Link
            key={entry.keyword_norm}
            to={hrefFor(entry)}
            title={`${label} · ${entry.count?.toLocaleString() ?? 0} image${entry.count === 1 ? '' : 's'}`}
            className="text-[var(--color-text-secondary)] hover:text-[var(--color-accent-bright)] hover:underline leading-none transition-colors"
            style={{ fontSize: `${size}px` }}
          >
            {label}
          </Link>
        )
      })}
    </div>
  )
}
