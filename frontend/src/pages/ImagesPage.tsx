import { useEffect, useMemo, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useNavigate, Link } from 'react-router-dom'
import { clsx } from 'clsx'
import { ChevronLeft, ChevronRight, Database, Scan, FileText, Zap, Layers, Tag, Bird, Fingerprint, Compass, Dna, MessageSquare } from 'lucide-react'
import { galleryApi } from '@/api/gallery'
import { useUiStore } from '@/stores/uiStore'
import { Button } from '@/components/ui/button'
import { phaseStatusColor } from '@/constants/labelColors'
import { imageInspectorPath } from '@/utils/routes'
import type { Image, ImagePhaseStatusRow } from '@/types/api'

const PAGE_SIZES = [25, 50, 100] as const

const SORT_COLUMNS: { key: string; label: string; sortable?: boolean }[] = [
  { key: 'id', label: 'ID' },
  { key: 'file_name', label: 'File' },
  { key: 'file_path', label: 'Path' },
  { key: 'score_general', label: 'Quality' },
  { key: 'phases', label: 'Phases' },
  { key: 'embeddings', label: 'Embeddings' },
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
  icon: Icon 
}: { 
  code: string; 
  status?: string; 
  error?: string | null; 
  icon: any 
}) {
  const color = useMemo(() => phaseStatusColor(status), [status])

  const title = useMemo(() => {
    let t = `${code.charAt(0).toUpperCase() + code.slice(1)}: ${status || 'not_started'}`
    if (error) t += `\nError: ${error}`
    return t
  }, [code, status, error])

  return (
    <div 
      className="p-1 rounded-sm transition-colors hover:bg-[#3c3c3c]" 
      title={title}
      style={{ color }}
    >
      <Icon size={14} strokeWidth={2.5} />
    </div>
  )
}

function ImagePhases({ phases }: { phases?: Record<string, ImagePhaseStatusRow | string> | null }) {
  if (!phases) return <span className="text-[#6d6d6d]">—</span>

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

function EmbeddingIcon({
  code,
  present,
  icon: Icon,
  color,
  label,
}: {
  code: string
  present: boolean
  icon: any
  color: string
  label: string
}) {
  const title = `${label}: ${present ? 'Present' : 'Missing'}`
  return (
    <div
      data-code={code}
      className={clsx(
        'p-1 rounded-sm transition-colors hover:bg-[#3c3c3c]',
        present ? 'opacity-100' : 'opacity-30',
      )}
      title={title}
      style={{ color: present ? color : '#6d6d6d' }}
    >
      <Icon size={14} strokeWidth={2.5} />
    </div>
  )
}

function ImageEmbeddings({ embeddings }: { embeddings?: Record<string, boolean> | null }) {
  const present = embeddings || {}
  
  return (
    <div className="flex items-center gap-0.5 justify-start">
      <EmbeddingIcon 
        code="mobilenet_v2_imagenet_gap" 
        label="MobileNetV2 (1280d)" 
        icon={Fingerprint} 
        present={!!present['mobilenet_v2_imagenet_gap']} 
        color="#4fc1ff" 
      />
      <EmbeddingIcon 
        code="clip_vit_b32_image" 
        label="CLIP (512d)" 
        icon={Compass} 
        present={!!present['clip_vit_b32_image']} 
        color="#4ec9b0" 
      />
      <EmbeddingIcon 
        code="bioclip_2_image" 
        label="BioCLIP (512d)" 
        icon={Dna} 
        present={!!present['bioclip_2_image']} 
        color="#ce9178" 
      />
      <EmbeddingIcon 
        code="blip_vit_b16_image" 
        label="BLIP (768d)" 
        icon={MessageSquare} 
        present={!!present['blip_vit_b16_image']} 
        color="#c586c0" 
      />
    </div>
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

  useEffect(() => {
    setPage(1)
  }, [selectedScopePath, pageSize, sortBy, order])

  const { data, isLoading, isFetching, isPlaceholderData } = useQuery({
    queryKey: ['images', 'browse', selectedScopePath, page, pageSize, sortBy, order],
    queryFn: () =>
      galleryApi.list({
        folder_path: selectedScopePath ?? undefined,
        page,
        page_size: pageSize,
        sort_by: sortBy,
        order,
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
    <div className="flex flex-col h-full min-h-0 bg-[#1e1e1e]">
      <div className="shrink-0 border-b border-[#3c3c3c] px-4 py-3 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 text-[#cccccc]">
          <Database size={16} className="text-[#4fc1ff]" />
          <span className="text-sm font-semibold">Images</span>
        </div>
        <div className="text-xs text-[#6d6d6d] max-w-[min(100%,42rem)] truncate" title={scopeLabel}>
          Scope: <span className="text-[#9d9d9d]">{scopeLabel}</span>
        </div>
        <div className="ml-auto flex items-center gap-2 text-xs text-[#6d6d6d]">
          <span>
            {total.toLocaleString()} row{total !== 1 ? 's' : ''}
            {isFetching && !isLoading ? ' · …' : ''}
          </span>
          <label className="flex items-center gap-1">
            <span>Page size</span>
            <select
              value={pageSize}
              onChange={(e) => setPageSize(Number(e.target.value) as (typeof PAGE_SIZES)[number])}
              className="bg-[#252526] border border-[#474747] rounded px-1.5 py-0.5 text-[#cccccc] outline-none focus:border-[#4fc1ff]"
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
          <div className="p-4 text-sm text-[#6d6d6d]">Loading…</div>
        )}
        {!isLoading && images.length === 0 && (
          <div className="p-4 text-sm text-[#6d6d6d]">No images in this scope.</div>
        )}
        {images.length > 0 && (
          <table
            className={clsx(
              'w-full text-xs border-collapse',
              isPlaceholderData && 'opacity-70',
            )}
          >
            <thead className="sticky top-0 z-[1] bg-[#252526] border-b border-[#3c3c3c]">
              <tr>
                {SORT_COLUMNS.map((col) => (
                  <th key={col.key} className="text-left font-semibold text-[#9d9d9d] px-3 py-2">
                    {col.sortable !== false ? (
                      <button
                        type="button"
                        onClick={() => onHeaderClick(col.key)}
                        className={clsx(
                          'inline-flex items-center gap-1 hover:text-[#4fc1ff] transition-colors',
                          sortBy === col.key && 'text-[#4fc1ff]',
                        )}
                      >
                        {col.label}
                        {sortBy === col.key && (
                          <span className="text-[10px] font-mono">{order === 'asc' ? '↑' : '↓'}</span>
                        )}
                      </button>
                    ) : (
                      <span className="text-[#9d9d9d]">{col.label}</span>
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
                  className="border-b border-[#2d2d2d] hover:bg-[#2a2d2e] cursor-pointer"
                >
                  <td className="px-3 py-1.5 font-mono text-[#4fc1ff]">
                    <Link to={imageInspectorPath(row.id)} className="hover:underline">
                      {row.id}
                    </Link>
                  </td>
                  <td className="px-3 py-1.5 text-[#cccccc] max-w-[14rem] truncate" title={row.file_name}>
                    <Link to={imageInspectorPath(row.id)} className="hover:text-[#4fc1ff] hover:underline">
                      {row.file_name}
                    </Link>
                  </td>
                  <td
                    className="px-3 py-1.5 text-[#9d9d9d] max-w-[min(40vw,28rem)] truncate font-mono"
                    title={row.file_path}
                  >
                    {truncatePath(row.file_path, 72)}
                  </td>
                  <td className="px-3 py-1.5 text-[#cccccc]">
                    {row.score_general != null ? (row.score_general * 100).toFixed(1) : '—'}
                  </td>
                  <td className="px-3 py-1.5 text-center">
                    <ImagePhases phases={row.phase_statuses} />
                  </td>
                  <td className="px-3 py-1.5 text-center">
                    <ImageEmbeddings embeddings={row.embeddings_present} />
                  </td>
                  <td className="px-3 py-1.5 text-[#6d6d6d] font-mono">
                    {row.created_at ? String(row.created_at).slice(0, 19) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="shrink-0 border-t border-[#3c3c3c] px-4 py-2 flex items-center gap-2 bg-[#252526]">
        <Button
          variant="secondary"
          size="sm"
          disabled={!canPrev}
          onClick={() => setPage((p) => Math.max(1, p - 1))}
        >
          <ChevronLeft size={12} />
          Prev
        </Button>
        <span className="text-xs text-[#9d9d9d]">
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
