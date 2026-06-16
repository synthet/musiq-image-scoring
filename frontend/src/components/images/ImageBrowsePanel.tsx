import { useEffect, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useNavigate, Link } from 'react-router-dom'
import { clsx } from 'clsx'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { galleryApi, type ImageFilters } from '@/api/gallery'
import { useUiStore } from '@/stores/uiStore'
import { Button } from '@/components/ui/button'
import { ImageEmbeddingsRow } from '@/components/images/EmbeddingSpaceChip'
import { PHASES_HEADER_HINT, PipelinePhaseIconsRow } from '@/components/phases/PipelinePhaseIconsRow'
import { imageInspectorPath } from '@/utils/routes'
import type { Image } from '@/types/api'

const PAGE_SIZES = [25, 50, 100] as const

const EMBEDDINGS_HEADER_HINT =
  'MobileNetV2 · CLIP · BioCLIP · BLIP · OpenCLIP · OpenAI CLIP · DINOv2 · SigLIP2 (hover icons for present/missing)'

const SORT_COLUMNS: { key: string; label: string; sortable?: boolean; headerHint?: string }[] = [
  { key: 'id', label: 'ID' },
  { key: 'file_name', label: 'File' },
  { key: 'file_path', label: 'Path' },
  { key: 'score_general', label: 'Quality' },
  { key: 'phases', label: 'Phases', sortable: false, headerHint: PHASES_HEADER_HINT },
  { key: 'embeddings', label: 'Embeddings', sortable: false, headerHint: EMBEDDINGS_HEADER_HINT },
  { key: 'created_at', label: 'Created' },
]

function truncatePath(s: string, max = 64): string {
  if (s.length <= max) return s
  return `…${s.slice(-(max - 1))}`
}

function DataQualityBadge({ flags }: { flags?: Record<string, boolean> | null }) {
  if (!flags || !Object.values(flags).some(Boolean)) return null
  const labels: string[] = []
  if (flags.keywords_data_gap) labels.push('keywords')
  if (flags.scoring_data_gap) labels.push('scoring')
  return (
    <span
      className="ml-1 text-[10px] px-1 py-0.5 rounded bg-amber-500/20 text-amber-200"
      title={`Phase/data mismatch: ${labels.join(', ')}`}
    >
      gap
    </span>
  )
}

function QualityCell({ scoreGeneral }: { scoreGeneral?: number | null }) {
  if (scoreGeneral != null && scoreGeneral > 0) {
    return <span>{(scoreGeneral * 100).toFixed(1)}%</span>
  }
  return (
    <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-bg-elevated)] text-[var(--color-text-muted)]">
      unscored
    </span>
  )
}

export interface ImageBrowsePanelProps {
  filters: Pick<ImageFilters, 'folder_path' | 'stack_id' | 'keyword' | 'keyword_exact'>
  title: string
  subtitle?: string
  titleLeading?: React.ReactNode
  toolbarExtras?: React.ReactNode
  emptyMessage?: string
  queryKeyPrefix?: string
  onRowClick?: (imageId: number) => void
  /** When false, sort state is local to this panel instead of global uiStore. */
  useGlobalSort?: boolean
}

export function ImageBrowsePanel({
  filters,
  title,
  subtitle,
  titleLeading,
  toolbarExtras,
  emptyMessage = 'No images in this scope.',
  queryKeyPrefix = 'images',
  onRowClick,
  useGlobalSort = true,
}: ImageBrowsePanelProps) {
  const navigate = useNavigate()
  const globalSortBy = useUiStore((s) => s.sortBy)
  const globalSetSortBy = useUiStore((s) => s.setSortBy)
  const globalOrder = useUiStore((s) => s.sortOrder)
  const globalSetOrder = useUiStore((s) => s.setSortOrder)

  const [localSortBy, setLocalSortBy] = useState('score_general')
  const [localOrder, setLocalOrder] = useState<'asc' | 'desc'>('desc')

  const sortBy = useGlobalSort ? globalSortBy : localSortBy
  const setSortBy = useGlobalSort ? globalSetSortBy : setLocalSortBy
  const order = useGlobalSort ? globalOrder : localOrder
  const setOrder = useGlobalSort ? globalSetOrder : setLocalOrder

  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState<(typeof PAGE_SIZES)[number]>(50)
  const [phaseStatusFilter, setPhaseStatusFilter] = useState('')
  const [unscoredOnly, setUnscoredOnly] = useState(false)
  const [dataGapFilter, setDataGapFilter] = useState('')

  const folderPath = filters.folder_path ?? null
  const stackId = filters.stack_id ?? null
  const keyword = filters.keyword ?? null
  const keywordExact = filters.keyword_exact ?? false

  useEffect(() => {
    setPage(1)
  }, [folderPath, stackId, keyword, keywordExact, pageSize, sortBy, order, phaseStatusFilter, unscoredOnly, dataGapFilter])

  const { data, isLoading, isFetching, isPlaceholderData } = useQuery({
    queryKey: [
      queryKeyPrefix,
      'browse',
      folderPath,
      stackId,
      keyword,
      keywordExact,
      page,
      pageSize,
      sortBy,
      order,
      phaseStatusFilter,
      unscoredOnly,
      dataGapFilter,
    ],
    queryFn: () =>
      galleryApi.list({
        folder_path: folderPath ?? undefined,
        stack_id: stackId ?? undefined,
        keyword: keyword ?? undefined,
        keyword_exact: keyword ? keywordExact || undefined : undefined,
        page,
        page_size: pageSize,
        sort_by: sortBy,
        order,
        phase_status: phaseStatusFilter || undefined,
        unscored_only: unscoredOnly || undefined,
        data_gap: dataGapFilter || undefined,
      }),
    placeholderData: keepPreviousData,
  })

  const totalPages = data?.total_pages ?? 0
  const total = data?.total ?? 0
  const images: Image[] = data?.images ?? []

  const canPrev = page > 1
  const canNext = totalPages > 0 && page < totalPages

  function onHeaderClick(key: string) {
    if (sortBy === key) {
      setOrder(order === 'asc' ? 'desc' : 'asc')
    } else {
      setSortBy(key)
      setOrder(key === 'file_name' || key === 'file_path' ? 'asc' : 'desc')
    }
  }

  function handleRowClick(imageId: number) {
    if (onRowClick) {
      onRowClick(imageId)
    } else {
      navigate(imageInspectorPath(imageId))
    }
  }

  return (
    <div className="flex flex-col h-full min-h-0 bg-[var(--color-bg-primary)]">
      <div className="shrink-0 border-b border-[var(--color-border-muted)] px-4 py-3 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 text-[var(--color-text-primary)]">
          {titleLeading}
          <span className="text-sm font-semibold">{title}</span>
        </div>
        {subtitle ? (
          <div
            className="text-xs text-[var(--color-text-muted)] max-w-[min(100%,42rem)] truncate"
            title={subtitle}
          >
            {subtitle}
          </div>
        ) : null}
        <div className="flex flex-wrap items-center gap-2 text-xs text-[var(--color-text-muted)]">
          <label className="flex items-center gap-1">
            <span>Phase</span>
            <select
              value={phaseStatusFilter}
              onChange={(e) => setPhaseStatusFilter(e.target.value)}
              className="bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded px-1.5 py-0.5 text-[var(--color-text-primary)]"
            >
              <option value="">Any</option>
              <option value="keywords:not_started">Keywords not started</option>
              <option value="scoring:not_started">Scoring not started</option>
              <option value="indexing:not_started">Indexing not started</option>
              <option value="keywords:failed">Keywords failed</option>
            </select>
          </label>
          <label className="flex items-center gap-1">
            <input
              type="checkbox"
              checked={unscoredOnly}
              onChange={(e) => setUnscoredOnly(e.target.checked)}
            />
            <span>Unscored</span>
          </label>
          <label className="flex items-center gap-1">
            <span>Data gap</span>
            <select
              value={dataGapFilter}
              onChange={(e) => setDataGapFilter(e.target.value)}
              className="bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded px-1.5 py-0.5 text-[var(--color-text-primary)]"
            >
              <option value="">Off</option>
              <option value="keywords">Keywords</option>
            </select>
          </label>
        </div>
        {toolbarExtras}
        <div className="ml-auto flex items-center gap-2 text-xs text-[var(--color-text-muted)]">
          <span>
            {total.toLocaleString()} row{total !== 1 ? 's' : ''}
            {isFetching && !isLoading ? ' · …' : ''}
          </span>
          <label className="flex items-center gap-1">
            <span>Page size</span>
            <select
              value={pageSize}
              onChange={(e) => setPageSize(Number(e.target.value) as (typeof PAGE_SIZES)[number])}
              className="bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded px-1.5 py-0.5 text-[var(--color-text-primary)] outline-none focus:border-[var(--color-accent)]"
            >
              {PAGE_SIZES.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-auto">
        {isLoading && !isPlaceholderData && (
          <div className="p-4 text-sm text-[var(--color-text-muted)]">Loading…</div>
        )}
        {!isLoading && images.length === 0 && (
          <div className="p-4 text-sm text-[var(--color-text-muted)]">{emptyMessage}</div>
        )}
        {images.length > 0 && (
          <table
            className={clsx(
              'w-full text-xs border-collapse',
              isPlaceholderData && 'opacity-70',
            )}
          >
            <thead className="sticky top-0 z-[1] bg-[var(--color-bg-secondary)] border-b border-[var(--color-border-muted)]">
              <tr>
                {SORT_COLUMNS.map((col) => (
                  <th
                    key={col.key}
                    className="text-left font-semibold text-[var(--color-text-secondary)] px-3 py-2"
                    title={col.headerHint}
                  >
                    {col.sortable !== false ? (
                      <button
                        type="button"
                        onClick={() => onHeaderClick(col.key)}
                        className={clsx(
                          'inline-flex items-center gap-1 hover:text-[var(--color-accent-bright)] transition-colors',
                          sortBy === col.key && 'text-[var(--color-accent-bright)]',
                        )}
                        title={col.headerHint}
                      >
                        {col.label}
                        {sortBy === col.key && (
                          <span className="text-[10px] font-mono">{order === 'asc' ? '↑' : '↓'}</span>
                        )}
                      </button>
                    ) : (
                      <span className="text-[var(--color-text-secondary)] cursor-help" title={col.headerHint}>
                        {col.label}
                      </span>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {images.map((row) => (
                <tr
                  key={row.id}
                  onClick={() => handleRowClick(row.id)}
                  className="border-b border-[var(--color-border-muted)] hover:bg-[var(--color-bg-tertiary)] cursor-pointer"
                >
                  <td className="px-3 py-1.5 font-mono text-[var(--color-accent-bright)]">
                    <Link to={imageInspectorPath(row.id)} className="hover:underline" onClick={(e) => e.stopPropagation()}>
                      {row.id}
                    </Link>
                    <DataQualityBadge flags={row.data_quality_flags} />
                  </td>
                  <td className="px-3 py-1.5 text-[var(--color-text-primary)] max-w-[14rem] truncate" title={row.file_name}>
                    <Link
                      to={imageInspectorPath(row.id)}
                      className="hover:text-[var(--color-accent-bright)] hover:underline"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {row.file_name}
                    </Link>
                  </td>
                  <td
                    className="px-3 py-1.5 text-[var(--color-text-secondary)] max-w-[min(32vw,22rem)] truncate font-mono"
                    title={row.file_path}
                  >
                    {truncatePath(row.file_path, 56)}
                  </td>
                  <td className="px-3 py-1.5 text-[var(--color-text-primary)]">
                    <QualityCell scoreGeneral={row.score_general} />
                  </td>
                  <td className="px-3 py-1.5 text-center">
                    <PipelinePhaseIconsRow phases={row.phase_statuses} />
                  </td>
                  <td className="px-3 py-1.5 text-center">
                    <ImageEmbeddingsRow embeddings={row.embeddings_present} />
                  </td>
                  <td className="px-3 py-1.5 text-[var(--color-text-muted)] font-mono">
                    {row.created_at ? String(row.created_at).slice(0, 19) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="shrink-0 border-t border-[var(--color-border-muted)] px-4 py-2 flex items-center gap-2 bg-[var(--color-bg-secondary)]">
        <Button
          variant="secondary"
          size="sm"
          disabled={!canPrev}
          onClick={() => setPage((p) => Math.max(1, p - 1))}
        >
          <ChevronLeft size={12} />
          Prev
        </Button>
        <span className="text-xs text-[var(--color-text-secondary)]">
          Page {page}
          {totalPages > 0 ? ` / ${totalPages}` : ''}
        </span>
        <Button
          variant="secondary"
          size="sm"
          disabled={!canNext}
          onClick={() => setPage((p) => p + 1)}
        >
          Next
          <ChevronRight size={12} />
        </Button>
      </div>
    </div>
  )
}
