import { useEffect, useMemo, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useNavigate, Link } from 'react-router-dom'
import { clsx } from 'clsx'
import { ChevronLeft, ChevronRight, Database, Scan, FileText, Zap, Layers, Tag, Bird } from 'lucide-react'
import { galleryApi } from '@/api/gallery'
import { useUiStore } from '@/stores/uiStore'
import { Button } from '@/components/ui/button'
import { phaseStatusColor } from '@/constants/labelColors'
import { ImageEmbeddingsRow } from '@/components/images/EmbeddingSpaceChip'
import { imageInspectorPath } from '@/utils/routes'
import type { Image, ImagePhaseStatusRow } from '@/types/api'

const PAGE_SIZES = [25, 50, 100] as const

const PHASES_HEADER_HINT =
  'Indexing · Metadata · Scoring · Culling · Keywords · Bird species (hover icons for status)'
const EMBEDDINGS_HEADER_HINT =
  'MobileNetV2 · CLIP · BioCLIP · BLIP (hover icons for present/missing)'

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

function PhaseIcon({
  code,
  status,
  error,
  icon: Icon,
}: {
  code: string
  status?: string
  error?: string | null
  icon: React.ComponentType<{ size?: number; strokeWidth?: number }>
}) {
  const color = useMemo(() => phaseStatusColor(status), [status])

  const title = useMemo(() => {
    let t = `${code.charAt(0).toUpperCase() + code.slice(1)}: ${status || 'not_started'}`
    if (error) t += `\nError: ${error}`
    return t
  }, [code, status, error])

  return (
    <div
      className="p-1 rounded-sm transition-colors hover:bg-[var(--color-bg-elevated)]"
      title={title}
      style={{ color }}
    >
      <Icon size={14} strokeWidth={2.5} />
    </div>
  )
}

function ImagePhases({ phases }: { phases?: Record<string, ImagePhaseStatusRow | string> | null }) {
  if (!phases) return <span className="text-[var(--color-text-muted)]">—</span>

  const getStatus = (code: string) => {
    const p = phases[code]
    if (typeof p === 'string') return { status: p }
    return p as ImagePhaseStatusRow | undefined
  }

  return (
    <div className="flex items-center gap-0.5">
      <PhaseIcon code="indexing" icon={Scan} status={getStatus('indexing')?.status} error={getStatus('indexing')?.last_error} />
      <PhaseIcon code="metadata" icon={FileText} status={getStatus('metadata')?.status} error={getStatus('metadata')?.last_error} />
      <PhaseIcon code="scoring" icon={Zap} status={getStatus('scoring')?.status} error={getStatus('scoring')?.last_error} />
      <PhaseIcon code="culling" icon={Layers} status={getStatus('culling')?.status} error={getStatus('culling')?.last_error} />
      <PhaseIcon code="keywords" icon={Tag} status={getStatus('keywords')?.status} error={getStatus('keywords')?.last_error} />
      <PhaseIcon code="birds" icon={Bird} status={getStatus('bird_species')?.status} error={getStatus('bird_species')?.last_error} />
    </div>
  )
}

function ImageEmbeddings({ embeddings }: { embeddings?: Record<string, boolean> | null }) {
  return <ImageEmbeddingsRow embeddings={embeddings} />
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

export function ImagesPage() {
  const navigate = useNavigate()
  const selectedScopePath = useUiStore((s) => s.selectedScopePath)
  const sortBy = useUiStore((s) => s.sortBy)
  const setSortBy = useUiStore((s) => s.setSortBy)
  const order = useUiStore((s) => s.sortOrder)
  const setOrder = useUiStore((s) => s.setSortOrder)

  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState<(typeof PAGE_SIZES)[number]>(50)
  const [phaseStatusFilter, setPhaseStatusFilter] = useState('')
  const [unscoredOnly, setUnscoredOnly] = useState(false)
  const [dataGapFilter, setDataGapFilter] = useState('')

  useEffect(() => {
    setPage(1)
  }, [selectedScopePath, pageSize, sortBy, order, phaseStatusFilter, unscoredOnly, dataGapFilter])

  const { data, isLoading, isFetching, isPlaceholderData } = useQuery({
    queryKey: [
      'images',
      'browse',
      selectedScopePath,
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
        folder_path: selectedScopePath ?? undefined,
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

  const scopeLabel = useMemo(() => {
    if (!selectedScopePath) return 'All indexed images'
    return selectedScopePath
  }, [selectedScopePath])

  return (
    <div className="flex flex-col h-full min-h-0 bg-[var(--color-bg-primary)]">
      <div className="shrink-0 border-b border-[var(--color-border-muted)] px-4 py-3 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 text-[var(--color-text-primary)]">
          <Database size={16} className="text-[var(--color-accent-bright)]" />
          <span className="text-sm font-semibold">Images</span>
        </div>
        <div className="text-xs text-[var(--color-text-muted)] max-w-[min(100%,42rem)] truncate" title={scopeLabel}>
          Scope: <span className="text-[var(--color-text-secondary)]">{scopeLabel}</span>
        </div>
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
          <div className="p-4 text-sm text-[var(--color-text-muted)]">No images in this scope.</div>
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
                  onClick={() => navigate(imageInspectorPath(row.id))}
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
                    <ImagePhases phases={row.phase_statuses} />
                  </td>
                  <td className="px-3 py-1.5 text-center">
                    <ImageEmbeddings embeddings={row.embeddings_present} />
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
