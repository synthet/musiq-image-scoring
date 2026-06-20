import { useState, useCallback, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { Star, Filter, X } from 'lucide-react'
import { VirtuosoGrid } from 'react-virtuoso'
import { galleryApi, type ImageFilters } from '@/api/gallery'
import { Button } from '@/components/ui/button'
import { LABEL_COLORS, LABEL_FALLBACK_COLOR } from '@/constants/labelColors'
import type { Image } from '@/types/api'

const LABELS = ['Red', 'Orange', 'Yellow', 'Green', 'Blue', 'Purple', 'Gray', 'Pick', 'Reject']
const PER_PAGE = 100

type BaseFilters = Omit<ImageFilters, 'page' | 'page_size'>

export function GalleryPage() {
  const navigate = useNavigate()
  const [baseFilters, setBaseFilters] = useState<BaseFilters>({})
  const [filterOpen, setFilterOpen] = useState(false)
  const [loadedImages, setLoadedImages] = useState<Image[]>([])
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const loadingRef = useRef(false)

  // Initial/filter-change load (page 1)
  const { data: initialData, isLoading } = useQuery({
    queryKey: ['gallery', baseFilters],
    queryFn: () => galleryApi.list({ ...baseFilters, page: 1, page_size: PER_PAGE }),
  })

  useEffect(() => {
    if (initialData) {
      setLoadedImages(initialData.images)
      setTotal(initialData.total)
      setPage(2)
    }
  }, [initialData])

  const loadMore = useCallback(async () => {
    if (loadingRef.current || loadedImages.length >= total) return
    loadingRef.current = true
    try {
      const res = await galleryApi.list({ ...baseFilters, page, page_size: PER_PAGE })
      setLoadedImages((prev) => [...prev, ...res.images])
      setTotal(res.total)
      setPage((p) => p + 1)
    } finally {
      loadingRef.current = false
    }
  }, [baseFilters, page, loadedImages.length, total])

  function updateFilter(patch: Partial<BaseFilters>) {
    setBaseFilters((prev) => ({ ...prev, ...patch }))
  }

  return (
    <div className="flex h-full min-h-0">
      {/* Filters sidebar */}
      {filterOpen && (
        <aside className="w-56 shrink-0 border-r border-[#3c3c3c] bg-[#252526] p-4 overflow-y-auto">
          <div className="flex items-center justify-between mb-4">
            <span className="text-xs font-semibold text-[#9d9d9d] uppercase tracking-wider">Filters</span>
            <button onClick={() => setFilterOpen(false)} className="text-[#6d6d6d] hover:text-[#cccccc]">
              <X size={13} />
            </button>
          </div>

          <FilterSection label="Min Rating">
            <div className="flex gap-1">
              {[0, 1, 2, 3, 4, 5].map((r) => (
                <button
                  key={r}
                  onClick={() => {
                    const rating = r === 0 ? undefined : Array.from({ length: 6 - r }, (_, i) => r + i).join(',')
                    updateFilter({ rating })
                  }}
                  className={clsx(
                    'w-7 h-7 flex items-center justify-center rounded text-xs border transition-colors',
                    baseFilters.rating?.startsWith(String(r))
                      ? 'bg-[var(--color-accent-dim)] border-[var(--color-accent)] text-[var(--color-accent-bright)]'
                      : 'border-[var(--color-border)] text-[var(--color-text-secondary)] hover:border-[var(--color-accent-bright)]',
                  )}
                >
                  {r === 0 ? 'Any' : <Star size={10} />}
                </button>
              ))}
            </div>
          </FilterSection>

          <FilterSection label="Label">
            <div className="space-y-1">
              {LABELS.map((l) => (
                <button
                  key={l}
                  onClick={() => updateFilter({ label: l === baseFilters.label ? undefined : l })}
                  className={clsx(
                    'w-full text-left text-xs px-2 py-1 rounded border transition-colors',
                    baseFilters.label === l
                      ? 'bg-[var(--color-accent-dim)] border-[var(--color-accent)] text-[var(--color-accent-bright)]'
                      : 'border-transparent text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-elevated)]',
                  )}
                >
                  {l}
                </button>
              ))}
            </div>
          </FilterSection>

          <FilterSection label="Min Score (General)">
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={baseFilters.min_score_general ?? 0}
              onChange={(e) => updateFilter({ min_score_general: parseFloat(e.target.value) || undefined })}
              className="w-full"
            />
            <div className="text-xs text-[#6d6d6d] text-right">
              {((baseFilters.min_score_general ?? 0) * 100).toFixed(0)}%
            </div>
          </FilterSection>

          <FilterSection label="Min CLIP Quality">
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={baseFilters.min_clip_quality_v0 ?? 0}
              onChange={(e) =>
                updateFilter({ min_clip_quality_v0: parseFloat(e.target.value) || undefined })
              }
              className="w-full"
            />
            <div className="text-xs text-[#6d6d6d] text-right">
              {((baseFilters.min_clip_quality_v0 ?? 0) * 100).toFixed(0)}%
            </div>
          </FilterSection>

          <FilterSection label="Keyword">
            <input
              value={baseFilters.keyword ?? ''}
              onChange={(e) => updateFilter({ keyword: e.target.value || undefined })}
              placeholder="landscape, portrait…"
              className="w-full bg-[#1e1e1e] border border-[#474747] rounded px-2 py-1 text-xs text-[#cccccc] outline-none focus:border-[#4fc1ff] placeholder:text-[#6d6d6d]"
            />
            <div className="mt-2 flex flex-wrap gap-1">
              {(
                [
                  { label: 'Birds', value: 'birds' },
                  { label: 'No species match', value: 'birds:species-exhausted' },
                  { label: 'Has species', value: 'species:' },
                ] as const
              ).map((preset) => (
                <button
                  key={preset.label}
                  type="button"
                  onClick={() => updateFilter({ keyword: preset.value })}
                  className={clsx(
                    'rounded border px-1.5 py-0.5 text-[10px] transition-colors',
                    baseFilters.keyword === preset.value
                      ? 'border-[var(--color-accent)] bg-[var(--color-accent-dim)] text-[var(--color-accent-bright)]'
                      : 'border-[#474747] text-[#9d9d9d] hover:bg-[#2a2a2a]',
                  )}
                >
                  {preset.label}
                </button>
              ))}
            </div>
          </FilterSection>

          <Button
            size="xs"
            variant="ghost"
            onClick={() => setBaseFilters({})}
            className="mt-3"
          >
            Clear all filters
          </Button>
        </aside>
      )}

      {/* Main gallery */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Toolbar */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-[#3c3c3c] shrink-0">
          <Button
            variant={filterOpen ? 'outline' : 'secondary'}
            size="sm"
            onClick={() => setFilterOpen((v) => !v)}
          >
            <Filter size={12} />
            Filters
          </Button>
          <span className="text-xs text-[#6d6d6d]">
            {total.toLocaleString()} image{total !== 1 ? 's' : ''}
          </span>
        </div>

        {/* Virtualized Grid */}
        <div className="flex-1 min-h-0 relative">
          {isLoading && loadedImages.length === 0 && (
            <div className="p-4 text-sm text-[#6d6d6d]">Loading gallery…</div>
          )}
          {!isLoading && loadedImages.length === 0 && (
            <div className="p-4 text-sm text-[#6d6d6d]">No images found.</div>
          )}
          {loadedImages.length > 0 && (
            <VirtuosoGrid
              style={{ height: '100%' }}
              totalCount={loadedImages.length}
              overscan={200}
              endReached={loadMore}
              listClassName="grid gap-1 p-4"
              itemClassName=""
              computeItemKey={(index) => loadedImages[index]?.id ?? index}
              itemContent={(index) => {
                const img = loadedImages[index]
                if (!img) return null
                return (
                  <ImageTile
                    image={img}
                    onClick={() => navigate(`/gallery/${img.id}`)}
                  />
                )
              }}
            />
          )}
        </div>
      </div>
    </div>
  )
}

function FilterSection({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-[#6d6d6d] mb-2">{label}</div>
      {children}
    </div>
  )
}

function ImageTile({
  image,
  onClick,
}: {
  image: Image
  onClick: () => void
}) {
  const src = image.thumbnail_path
    ? `/source-image?path=${encodeURIComponent(image.thumbnail_path)}&thumb=1`
    : null

  const displayScore = image.score_general ?? image.score ?? image.composite_score

  return (
    <div
      onClick={onClick}
      className={clsx(
        'relative aspect-square rounded overflow-hidden cursor-pointer border-2 transition-all',
        'border-transparent hover:border-[#474747]',
      )}
    >
      {src ? (
        <img
          src={src}
          alt={image.file_name}
          className="w-full h-full object-cover"
          loading="lazy"
        />
      ) : (
        <div className="w-full h-full bg-[#3c3c3c] flex items-center justify-center text-[#6d6d6d] text-xs">
          No preview
        </div>
      )}
      {image.label && (
        <div 
          className="absolute top-1 left-1 w-2.5 h-2.5 rounded-full border border-black/50 shadow-sm"
          style={{ backgroundColor: LABEL_COLORS[image.label.toLowerCase()] || LABEL_FALLBACK_COLOR }}
          title={image.label}
        />
      )}
      {image.rating != null && image.rating > 0 && (
        <div className="absolute bottom-1 left-1 flex">
          {Array.from({ length: image.rating }).map((_, i) => (
            <Star key={i} size={8} className="text-[#cca700]" fill="currentColor" />
          ))}
        </div>
      )}
      {displayScore != null && (
        <div className="absolute top-1 right-1 bg-black/70 text-white text-[9px] px-1 rounded">
          {(displayScore * 100).toFixed(0)}
        </div>
      )}
    </div>
  )
}

