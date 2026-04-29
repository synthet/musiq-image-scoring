import { useState, useCallback, useRef, useEffect, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { clsx } from 'clsx'
import { Search, Sparkles, Image as ImageIcon, SlidersHorizontal, X, Loader2, ExternalLink } from 'lucide-react'
import { searchApi, type TextSearchResult } from '@/api/search'
import { useUiStore } from '@/stores/uiStore'
import { imageInspectorPath } from '@/utils/routes'

const RESULT_LIMITS = [12, 24, 48, 96] as const
const MIN_SIM_OPTIONS = [
  { label: 'None', value: undefined },
  { label: '≥ 0.15', value: 0.15 },
  { label: '≥ 0.20', value: 0.20 },
  { label: '≥ 0.25', value: 0.25 },
  { label: '≥ 0.30', value: 0.30 },
] as const

const EXAMPLE_QUERIES = [
  'sunset over mountains',
  'portrait with dramatic lighting',
  'birds in flight',
  'forest path in autumn',
  'ocean waves crashing',
  'city skyline at night',
  'close-up of flower petals',
  'snow-covered landscape',
]

const EXAMPLE_ROTATE_MS = 10_000

/** Pick up to six random suggestions from `pool`. */
function pickExampleSubset(pool: string[], count = 6): string[] {
  if (!pool.length) return []
  if (pool.length <= count) {
    return [...pool].sort(() => Math.random() - 0.5)
  }
  const shuffled = [...pool].sort(() => Math.random() - 0.5)
  return shuffled.slice(0, count)
}

function thumbnailSrc(filePath: string): string {
  return `/source-image?path=${encodeURIComponent(filePath)}&thumb=1`
}

function ResultCard({
  result,
  rank,
  onClick,
}: {
  result: TextSearchResult
  rank: number
  onClick: () => void
}) {
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState(false)
  const fileName = result.file_path.split(/[/\\]/).pop() ?? result.file_path

  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        'group relative rounded-lg overflow-hidden border border-[#3c3c3c] bg-[#252526]',
        'hover:border-[#007acc] hover:shadow-[0_0_0_1px_#007acc,0_4px_24px_rgba(0,122,204,0.15)]',
        'transition-all duration-200 cursor-pointer text-left',
        'focus:outline-none focus:border-[#007acc] focus:ring-1 focus:ring-[#007acc]',
      )}
      title={`${fileName}\nSimilarity: ${(result.similarity * 100).toFixed(1)}%`}
    >
      {/* Image area */}
      <div className="aspect-square bg-[#141414] flex items-center justify-center overflow-hidden">
        {!error ? (
          <img
            src={thumbnailSrc(result.file_path)}
            alt={fileName}
            loading="lazy"
            onLoad={() => setLoaded(true)}
            onError={() => setError(true)}
            className={clsx(
              'w-full h-full object-cover transition-all duration-300',
              loaded ? 'opacity-100 scale-100' : 'opacity-0 scale-105',
              'group-hover:scale-105',
            )}
          />
        ) : (
          <div className="flex flex-col items-center gap-1 text-[#6d6d6d]">
            <ImageIcon size={24} />
            <span className="text-[10px]">Preview unavailable</span>
          </div>
        )}
        {!loaded && !error && (
          <div className="absolute inset-0 flex items-center justify-center bg-[#141414]">
            <div className="w-5 h-5 border-2 border-[#3c3c3c] border-t-[#4fc1ff] rounded-full animate-spin" />
          </div>
        )}
      </div>

      {/* Info bar */}
      <div className="px-2.5 py-2 space-y-1">
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] font-mono text-[#4fc1ff] bg-[#003f6e] px-1.5 py-0.5 rounded-sm shrink-0">
            #{rank}
          </span>
          <span className="text-xs text-[#cccccc] truncate flex-1" title={fileName}>
            {fileName}
          </span>
        </div>
        <div className="flex items-center justify-between gap-2">
          <SimilarityBar similarity={result.similarity} />
          <span className="text-[10px] text-[#9d9d9d] shrink-0 font-mono">
            {(result.similarity * 100).toFixed(1)}%
          </span>
        </div>
      </div>

      {/* Hover overlay */}
      <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none">
        <div className="absolute bottom-10 right-2">
          <ExternalLink size={14} className="text-white/70" />
        </div>
      </div>
    </button>
  )
}

function SimilarityBar({ similarity }: { similarity: number }) {
  const pct = Math.min(100, similarity * 100)
  const hue = Math.round(pct * 1.2) // 0=red, 120=green

  return (
    <div className="flex-1 h-1.5 bg-[#3c3c3c] rounded-full overflow-hidden min-w-0">
      <div
        className="h-full rounded-full transition-all duration-500"
        style={{
          width: `${pct}%`,
          background: `hsl(${hue}, 70%, 50%)`,
        }}
      />
    </div>
  )
}

function EmptyState({
  exampleQueries,
  onExampleClick,
}: {
  exampleQueries: string[]
  onExampleClick: (q: string) => void
}) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-6 px-4 py-12">
      <div className="relative">
        <div className="absolute -inset-4 bg-[#007acc]/5 rounded-full blur-2xl" />
        <div className="relative w-16 h-16 rounded-2xl bg-gradient-to-br from-[#007acc] to-[#4fc1ff] flex items-center justify-center shadow-lg shadow-[#007acc]/20">
          <Sparkles size={28} className="text-white" />
        </div>
      </div>
      <div className="text-center space-y-2 max-w-md">
        <h2 className="text-lg font-semibold text-[#cccccc]">Semantic Image Search</h2>
        <p className="text-sm text-[#9d9d9d] leading-relaxed">
          Search your image library with natural language. Powered by CLIP embeddings
          and vector similarity.
        </p>
      </div>
      <div className="flex flex-col items-center gap-2 max-w-lg">
        <span className="text-[10px] uppercase tracking-wider text-[#6d6d6d] font-semibold">
          Try a query
        </span>
        <div className="flex flex-wrap gap-2 justify-center">
          {exampleQueries.map((q, i) => (
            <button
              key={`${q}-${i}`}
              type="button"
              onClick={() => onExampleClick(q)}
              className={clsx(
                'px-3 py-1.5 rounded-full text-xs border border-[#3c3c3c] text-[#9d9d9d]',
                'hover:border-[#4fc1ff] hover:text-[#4fc1ff] hover:bg-[#003f6e]/30',
                'transition-all duration-200 cursor-pointer',
              )}
            >
              {q}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

export function SearchPage() {
  const navigate = useNavigate()
  const selectedScopePath = useUiStore((s) => s.selectedScopePath)

  const [queryText, setQueryText] = useState('')
  const [submittedQuery, setSubmittedQuery] = useState('')
  const [limit, setLimit] = useState<(typeof RESULT_LIMITS)[number]>(24)
  const [minSim, setMinSim] = useState<number | undefined>(undefined)
  const [showFilters, setShowFilters] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const { data: exampleData } = useQuery({
    queryKey: ['search-example-queries', selectedScopePath ?? null],
    queryFn: () =>
      searchApi.exampleQueries({
        limit: 48,
        folder_path: selectedScopePath ?? undefined,
      }),
    staleTime: 600_000,
    retry: 1,
  })

  const examplePool = useMemo(() => {
    const qs = exampleData?.queries
    return qs?.length ? qs : EXAMPLE_QUERIES
  }, [exampleData])

  const examplePoolRef = useRef(examplePool)
  examplePoolRef.current = examplePool

  const [rotatingChips, setRotatingChips] = useState(() => pickExampleSubset(EXAMPLE_QUERIES))
  const [placeholderIdx, setPlaceholderIdx] = useState(0)

  useEffect(() => {
    setRotatingChips(pickExampleSubset(examplePool))
    setPlaceholderIdx(0)
  }, [examplePool])

  useEffect(() => {
    const rotate = () => {
      if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return
      const pool = examplePoolRef.current
      if (!pool.length) return
      setRotatingChips(pickExampleSubset(pool))
      setPlaceholderIdx((i) => (i + 1) % pool.length)
    }
    const id = window.setInterval(rotate, EXAMPLE_ROTATE_MS)
    const onVisibility = () => {
      if (document.visibilityState === 'visible') {
        rotate()
      }
    }
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      window.clearInterval(id)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [])

  const searchPlaceholder =
    examplePool.length > 0
      ? `Describe what you're looking for… (e.g. ${examplePool[placeholderIdx % examplePool.length]})`
      : "Describe what you're looking for…"

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  const handleSubmit = useCallback(
    (q?: string) => {
      const text = (q ?? queryText).trim()
      if (!text) return
      setSubmittedQuery(text)
      if (q) setQueryText(q)
    },
    [queryText],
  )

  const handleClear = useCallback(() => {
    setQueryText('')
    setSubmittedQuery('')
    inputRef.current?.focus()
  }, [])

  const { data, isLoading, isFetching, error } = useQuery({
    queryKey: ['text-search', submittedQuery, limit, minSim, selectedScopePath],
    queryFn: () =>
      searchApi.textSearch({
        query: submittedQuery,
        limit,
        folder_path: selectedScopePath ?? undefined,
        min_similarity: minSim,
      }),
    enabled: submittedQuery.length > 0,
    staleTime: 30_000,
    retry: 1,
  })

  const results: TextSearchResult[] = data?.results ?? []
  const hasSearched = submittedQuery.length > 0

  return (
    <div className="flex flex-col h-full min-h-0 bg-[#1e1e1e]">
      {/* Search header */}
      <div className="shrink-0 border-b border-[#3c3c3c] bg-[#252526] px-4 py-3">
        <div className="max-w-3xl mx-auto space-y-3">
          {/* Search bar */}
          <form
            onSubmit={(e) => {
              e.preventDefault()
              handleSubmit()
            }}
            className="relative"
          >
            <div
              className={clsx(
                'flex items-center gap-2 rounded-lg border bg-[#1e1e1e] px-3 py-2',
                'transition-all duration-200',
                'focus-within:border-[#007acc] focus-within:shadow-[0_0_0_1px_#007acc]',
                !isFetching && 'border-[#474747]',
                isFetching && 'border-[#4fc1ff] shadow-[0_0_0_1px_#4fc1ff]',
              )}
            >
              {isFetching ? (
                <Loader2 size={16} className="text-[#4fc1ff] animate-spin shrink-0" />
              ) : (
                <Search size={16} className="text-[#6d6d6d] shrink-0" />
              )}
              <input
                ref={inputRef}
                type="text"
                value={queryText}
                onChange={(e) => setQueryText(e.target.value)}
                placeholder={searchPlaceholder}
                className={clsx(
                  'flex-1 bg-transparent text-sm text-[#cccccc] placeholder-[#6d6d6d]',
                  'outline-none min-w-0',
                )}
                id="search-query-input"
              />
              {queryText && (
                <button
                  type="button"
                  onClick={handleClear}
                  className="p-0.5 rounded text-[#6d6d6d] hover:text-[#cccccc] transition-colors"
                >
                  <X size={14} />
                </button>
              )}
              <button
                type="button"
                onClick={() => setShowFilters(!showFilters)}
                className={clsx(
                  'p-1 rounded transition-colors',
                  showFilters ? 'text-[#4fc1ff] bg-[#003f6e]' : 'text-[#6d6d6d] hover:text-[#9d9d9d]',
                )}
                title="Search filters"
              >
                <SlidersHorizontal size={14} />
              </button>
              <button
                type="submit"
                disabled={!queryText.trim() || isFetching}
                className={clsx(
                  'px-3 py-1 rounded-md text-xs font-medium transition-all duration-200',
                  'disabled:opacity-40 disabled:cursor-not-allowed',
                  queryText.trim()
                    ? 'bg-[#007acc] text-white hover:bg-[#1e8ad6] cursor-pointer'
                    : 'bg-[#3c3c3c] text-[#6d6d6d]',
                )}
                id="search-submit-btn"
              >
                Search
              </button>
            </div>
          </form>

          {/* Filters panel (collapsible) */}
          {showFilters && (
            <div className="flex flex-wrap items-center gap-4 text-xs text-[#9d9d9d] bg-[#1e1e1e] rounded-lg border border-[#3c3c3c] px-4 py-3">
              <label className="flex items-center gap-2">
                <span className="text-[#6d6d6d]">Results</span>
                <select
                  value={limit}
                  onChange={(e) => {
                    setLimit(Number(e.target.value) as (typeof RESULT_LIMITS)[number])
                    if (submittedQuery) handleSubmit()
                  }}
                  className="bg-[#252526] border border-[#474747] rounded px-2 py-1 text-[#cccccc] outline-none focus:border-[#4fc1ff]"
                >
                  {RESULT_LIMITS.map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex items-center gap-2">
                <span className="text-[#6d6d6d]">Min similarity</span>
                <select
                  value={minSim ?? ''}
                  onChange={(e) => {
                    setMinSim(e.target.value ? Number(e.target.value) : undefined)
                    if (submittedQuery) handleSubmit()
                  }}
                  className="bg-[#252526] border border-[#474747] rounded px-2 py-1 text-[#cccccc] outline-none focus:border-[#4fc1ff]"
                >
                  {MIN_SIM_OPTIONS.map((opt) => (
                    <option key={opt.label} value={opt.value ?? ''}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </label>
              {selectedScopePath && (
                <div className="flex items-center gap-1">
                  <span className="text-[#6d6d6d]">Scope:</span>
                  <span className="text-[#4fc1ff] truncate max-w-[20rem]" title={selectedScopePath}>
                    {selectedScopePath.split(/[/\\]/).pop()}
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Results area */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {!hasSearched && (
          <EmptyState exampleQueries={rotatingChips} onExampleClick={handleSubmit} />
        )}

        {hasSearched && isLoading && (
          <div className="flex flex-col items-center justify-center gap-3 py-20">
            <div className="w-8 h-8 border-2 border-[#3c3c3c] border-t-[#4fc1ff] rounded-full animate-spin" />
            <p className="text-sm text-[#6d6d6d]">
              Searching for "<span className="text-[#9d9d9d]">{submittedQuery}</span>"…
            </p>
            <p className="text-xs text-[#6d6d6d]">(First search may take a moment while the model loads)</p>
          </div>
        )}

        {hasSearched && error && (
          <div className="flex flex-col items-center gap-2 py-20 px-4">
            <div className="text-sm text-[#f44747]">Search failed</div>
            <div className="text-xs text-[#9d9d9d] text-center max-w-md">
              {(error as Error)?.message ?? 'Unknown error'}
            </div>
          </div>
        )}

        {hasSearched && !isLoading && !error && results.length === 0 && (
          <div className="flex flex-col items-center gap-3 py-20 px-4">
            <ImageIcon size={36} className="text-[#3c3c3c]" />
            <div className="text-center space-y-1">
              <p className="text-sm text-[#9d9d9d]">No matches found</p>
              <p className="text-xs text-[#6d6d6d]">
                Try a different query, lower the similarity threshold, or ensure images have CLIP embeddings (run tagging).
              </p>
            </div>
          </div>
        )}

        {results.length > 0 && (
          <div className="p-4 space-y-3">
            {/* Results meta bar */}
            <div className="flex items-center justify-between gap-4 text-xs">
              <div className="text-[#9d9d9d]">
                <span className="text-[#4fc1ff] font-medium">{results.length}</span>
                {' result'}{results.length !== 1 ? 's' : ''} for "
                <span className="text-[#cccccc]">{data?.query}</span>"
                {isFetching && !isLoading && (
                  <Loader2 size={10} className="inline ml-1 animate-spin text-[#4fc1ff]" />
                )}
              </div>
              <div className="text-[#6d6d6d]">
                space: <span className="font-mono text-[#9d9d9d]">{data?.embedding_space}</span>
              </div>
            </div>

            {/* Results grid */}
            <div className="grid gap-3 grid-cols-[repeat(auto-fill,minmax(180px,1fr))]">
              {results.map((result, i) => (
                <ResultCard
                  key={result.image_id}
                  result={result}
                  rank={i + 1}
                  onClick={() => navigate(imageInspectorPath(result.image_id))}
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
