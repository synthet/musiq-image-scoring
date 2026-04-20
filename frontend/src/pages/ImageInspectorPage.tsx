import { useState, useEffect } from 'react'
import { Link, useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import { galleryApi } from '@/api/gallery'
import { imageInspectorPath } from '@/utils/routes'
import { useUiStore } from '@/stores/uiStore'
import { CollapsibleInspectorSection, KeyValueTable, formatInspectorValue } from '@/components/images/InspectorPrimitives'
import { statusLabel } from '@/components/ui/badge'
import { PhaseStatusIcon, normalizePhaseStatus } from '@/components/ui/phaseStatus'
import type { ImageDetail, ImagePhaseStatusRow } from '@/types/api'

function detailPreviewSrc(image: ImageDetail): string | null {
  const full = image.resolved_path || image.file_path
  if (full) return `/source-image?path=${encodeURIComponent(full)}`
  if (image.thumbnail_path) {
    return `/source-image?path=${encodeURIComponent(image.thumbnail_path)}&thumb=1`
  }
  return null
}

function isScoreKey(k: string): boolean {
  return (
    k === 'score' ||
    k.startsWith('score_') ||
    k === 'musiq_score' ||
    k === 'topiq_score' ||
    k === 'qalign_score' ||
    k === 'composite_score'
  )
}

function partitionScalars(data: ImageDetail): {
  identity: [string, unknown][]
  paths: [string, unknown][]
  scores: [string, unknown][]
  user: [string, unknown][]
  dates: [string, unknown][]
  other: [string, unknown][]
} {
  const skip = new Set(['file_paths', 'resolved_path', 'phase_statuses'])
  const identityKeys = new Set([
    'id',
    'image_uuid',
    'image_hash',
    'hash_version',
    'burst_uuid',
    'stack_id',
    'folder_id',
    'file_name',
    'file_type',
    'file_size',
    'model_version',
  ])
  const pathKeys = new Set(['file_path', 'thumbnail_path', 'win_path'])
  const userKeys = new Set(['rating', 'label', 'title', 'description', 'keywords', 'caption'])
  const dateKeys = new Set(['created_at', 'updated_at'])

  const identity: [string, unknown][] = []
  const paths: [string, unknown][] = []
  const scores: [string, unknown][] = []
  const user: [string, unknown][] = []
  const dates: [string, unknown][] = []
  const other: [string, unknown][] = []

  const raw = data as unknown as Record<string, unknown>
  for (const k of Object.keys(raw)) {
    if (skip.has(k)) continue
    const v = raw[k]
    if (isScoreKey(k)) {
      scores.push([k, v])
      continue
    }
    if (identityKeys.has(k)) {
      identity.push([k, v])
      continue
    }
    if (pathKeys.has(k)) {
      paths.push([k, v])
      continue
    }
    if (userKeys.has(k)) {
      user.push([k, v])
      continue
    }
    if (dateKeys.has(k)) {
      dates.push([k, v])
      continue
    }
    other.push([k, v])
  }

  return { identity, paths, scores, user, dates, other }
}

function PhaseStatusTable({ phases }: { phases: NonNullable<ImageDetail['phase_statuses']> }) {
  const rows = Object.entries(phases)
  if (rows.length === 0) {
    return <div className="text-xs text-[#6d6d6d]">No phase rows.</div>
  }
  return (
    <div className="border border-[#3c3c3c] rounded overflow-auto max-h-64">
      <table className="w-full text-[11px] border-collapse min-w-[36rem]">
        <thead className="bg-[#1e1e1e] sticky top-0">
          <tr className="text-left text-[#9d9d9d] border-b border-[#3c3c3c]">
            <th className="px-2 py-1 font-semibold">Phase</th>
            <th className="px-2 py-1 font-semibold">Status</th>
            <th className="px-2 py-1 font-semibold">Updated</th>
            <th className="px-2 py-1 font-semibold">Attempts</th>
            <th className="px-2 py-1 font-semibold">Error</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([code, row]) => {
            const isString = typeof row === 'string'
            const r = isString ? null : (row as ImagePhaseStatusRow)
            const rawStatus = isString ? row : r?.status
            const normalizedStatus = normalizePhaseStatus(rawStatus)
            const statusText = isString
              ? row
              : rawStatus
                ? statusLabel(normalizedStatus)
                : '—'
            return (
              <tr key={code} className="border-b border-[#2d2d2d] hover:bg-[#2a2a2a]">
                <td className="px-2 py-1 font-mono text-[#4fc1ff]">{code}</td>
                <td className="px-2 py-1">
                  <div className="flex items-center gap-1.5">
                    <PhaseStatusIcon status={normalizedStatus} />
                    <span>{statusText}</span>
                  </div>
                </td>
                <td className="px-2 py-1 text-[#6d6d6d] font-mono">
                  {isString ? '—' : r?.updated_at ? String(r.updated_at).slice(0, 19) : '—'}
                </td>
                <td className="px-2 py-1">{isString ? '—' : (r?.attempt_count ?? '—')}</td>
                <td className="px-2 py-1 text-[#f44747] max-w-xs truncate" title={isString ? '' : r?.last_error ?? ''}>
                  {isString ? '—' : r?.last_error || '—'}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function LazyMetadataSection({
  imageId,
  kind,
  title,
}: {
  imageId: number
  kind: 'exif' | 'xmp'
  title: string
}) {
  const [loaded, setLoaded] = useState(false)
  const q = useQuery({
    queryKey: ['image', imageId, kind],
    queryFn: () => (kind === 'exif' ? galleryApi.getExif(imageId) : galleryApi.getXmp(imageId)),
    enabled: loaded,
  })

  return (
    <CollapsibleInspectorSection
      title={title}
      defaultOpen={false}
      badge={loaded && q.data ? `${Object.keys(q.data).length} fields` : undefined}
    >
      {!loaded && (
        <ButtonLoad onClick={() => setLoaded(true)} label={`Load ${kind.toUpperCase()}…`} />
      )}
      {loaded && q.isLoading && <div className="text-xs text-[#6d6d6d]">Loading…</div>}
      {loaded && q.isError && (
        <div className="text-xs text-[#f44747]">{(q.error as Error)?.message ?? 'Request failed'}</div>
      )}
      {loaded && q.data && Object.keys(q.data).length === 0 && (
        <div className="text-xs text-[#6d6d6d]">No cached row in the database.</div>
      )}
      {loaded && q.data && Object.keys(q.data).length > 0 && (
        <KeyValueTable entries={Object.entries(q.data)} dense />
      )}
    </CollapsibleInspectorSection>
  )
}

function ButtonLoad({ onClick, label }: { onClick: () => void; label: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="text-xs px-2 py-1 rounded border border-[#474747] text-[#4fc1ff] hover:bg-[#3c3c3c] transition-colors"
    >
      {label}
    </button>
  )
}

export function ImageInspectorPage() {
  const { imageId: rawId } = useParams<{ imageId: string }>()
  const id = rawId ? parseInt(rawId, 10) : NaN
  const navigate = useNavigate()

  const sortBy = useUiStore((s) => s.sortBy)
  const order = useUiStore((s) => s.sortOrder)
  const selectedScopePath = useUiStore((s) => s.selectedScopePath)

  const { data: neighbors } = useQuery({
    queryKey: ['image', 'neighbors', id, sortBy, order, selectedScopePath],
    queryFn: () =>
      galleryApi.getNeighbors(id, {
        sort_by: sortBy,
        order: order,
        folder_path: selectedScopePath ?? undefined,
      }),
    enabled: Number.isFinite(id) && id > 0,
  })

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const target = e.target as HTMLElement
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) {
        return
      }

      if (e.key === 'ArrowLeft') {
        if (neighbors?.prev_id) {
          navigate(imageInspectorPath(neighbors.prev_id))
        }
      } else if (e.key === 'ArrowRight') {
        if (neighbors?.next_id) {
          navigate(imageInspectorPath(neighbors.next_id))
        }
      } else if (e.key === 'Escape') {
        navigate('/images')
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [neighbors, navigate])

  const { data, isLoading, error } = useQuery({
    queryKey: ['image', 'inspector', id],
    queryFn: () => galleryApi.get(id),
    enabled: Number.isFinite(id) && id > 0,
  })

  if (!Number.isFinite(id) || id <= 0) {
    return <div className="p-4 text-sm text-[#6d6d6d]">Invalid image id.</div>
  }

  if (isLoading) {
    return <div className="p-4 text-sm text-[#6d6d6d]">Loading image…</div>
  }

  if (error || !data) {
    return (
      <div className="p-4 space-y-2">
        <div className="text-sm text-[#f44747]">Could not load image.</div>
        <Link to="/images" className="text-xs text-[#4fc1ff] hover:underline inline-flex items-center gap-1">
          <ArrowLeft size={12} /> Back to Images
        </Link>
      </div>
    )
  }

  const src = detailPreviewSrc(data)
  const parts = partitionScalars(data)
  const filePaths = data.file_paths
  const resolved = data.resolved_path

  return (
    <div className="flex flex-col h-full min-h-0 bg-[#1e1e1e] overflow-hidden">
      <div className="shrink-0 flex items-center gap-3 px-4 py-2 border-b border-[#3c3c3c] bg-[#252526]">
        <Link
          to="/images"
          className="text-xs text-[#4fc1ff] hover:underline inline-flex items-center gap-1 shrink-0"
        >
          <ArrowLeft size={12} /> Images
        </Link>
        <span className="text-sm font-medium text-[#cccccc] truncate">{data.file_name}</span>
        <span className="text-[10px] text-[#6d6d6d] font-mono ml-auto shrink-0">
          id{' '}
          <Link
            to={imageInspectorPath(data.id)}
            className="text-[#4fc1ff] hover:underline cursor-pointer"
          >
            {data.id}
          </Link>
        </span>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto">
        <div className="flex flex-col lg:flex-row gap-4 p-4 max-w-[120rem] mx-auto">
          <div className="w-full lg:w-[min(42%,520px)] shrink-0 lg:sticky lg:top-0 lg:self-start">
            <div className="rounded border border-[#3c3c3c] bg-[#141414] min-h-[200px] max-h-[50vh] lg:max-h-[calc(100vh-8rem)] flex items-center justify-center p-2">
              {src ? (
                <img
                  src={src}
                  alt={data.file_name}
                  className="max-w-full max-h-[min(50vh,480px)] object-contain"
                />
              ) : (
                <span className="text-sm text-[#6d6d6d]">No preview path</span>
              )}
            </div>
          </div>

          <div className="flex-1 min-w-0 space-y-3">
            <CollapsibleInspectorSection title="Identity & storage" defaultOpen>
              <KeyValueTable
                entries={parts.identity}
                dense
                renderValue={(k, v) => {
                  if (k === 'id' && typeof v === 'number') {
                    return (
                      <Link
                        to={imageInspectorPath(v)}
                        className="text-[#4fc1ff] hover:underline cursor-pointer"
                      >
                        {v}
                      </Link>
                    )
                  }
                  return formatInspectorValue(v)
                }}
              />
            </CollapsibleInspectorSection>

            <CollapsibleInspectorSection title="Paths" subtitle={resolved ? 'resolved_path' : undefined} defaultOpen>
              <div className="space-y-2">
                {parts.paths.length > 0 && <KeyValueTable entries={parts.paths} dense />}
                {resolved && (
                  <div className="text-[11px]">
                    <div className="text-[#6d6d6d] mb-0.5">resolved_path</div>
                    <div className="font-mono text-[#cccccc] break-all">{resolved}</div>
                  </div>
                )}
                {filePaths && filePaths.length > 0 && (
                  <div className="text-[11px]">
                    <div className="text-[#6d6d6d] mb-0.5">file_paths ({filePaths.length})</div>
                    <ul className="list-none space-y-1 font-mono text-[#9d9d9d] break-all">
                      {filePaths.map((p, i) => (
                        <li key={i}>{p}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </CollapsibleInspectorSection>

            <CollapsibleInspectorSection title="Scores" badge={`${parts.scores.length}`} defaultOpen>
              {parts.scores.length === 0 ? (
                <div className="text-xs text-[#6d6d6d]">No score columns.</div>
              ) : (
                <KeyValueTable entries={parts.scores} dense />
              )}
            </CollapsibleInspectorSection>

            <CollapsibleInspectorSection title="User metadata" defaultOpen>
              {parts.user.length === 0 ? (
                <div className="text-xs text-[#6d6d6d]">—</div>
              ) : (
                <KeyValueTable entries={parts.user} dense />
              )}
            </CollapsibleInspectorSection>

            <CollapsibleInspectorSection title="Dates" defaultOpen={false}>
              <KeyValueTable entries={parts.dates} dense />
            </CollapsibleInspectorSection>

            <CollapsibleInspectorSection
              title="Pipeline phases"
              badge={data.phase_statuses ? `${Object.keys(data.phase_statuses).length}` : '0'}
              defaultOpen
            >
              {data.phase_statuses && Object.keys(data.phase_statuses).length > 0 ? (
                <PhaseStatusTable phases={data.phase_statuses} />
              ) : (
                <div className="text-xs text-[#6d6d6d]">No phase status rows.</div>
              )}
            </CollapsibleInspectorSection>

            <LazyMetadataSection imageId={id} kind="exif" title="EXIF (cached)" />
            <LazyMetadataSection imageId={id} kind="xmp" title="XMP (cached)" />

            {parts.other.length > 0 && (
              <CollapsibleInspectorSection title="Other columns" badge={`${parts.other.length}`} defaultOpen={false}>
                <KeyValueTable entries={parts.other} dense />
              </CollapsibleInspectorSection>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
