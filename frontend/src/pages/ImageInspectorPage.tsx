import { useState, useEffect } from 'react'
import { Link, useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { ArrowLeft, Play } from 'lucide-react'
import { clsx } from 'clsx'
import { galleryApi } from '@/api/gallery'
import { runsApi } from '@/api/runs'
import { imageInspectorPath, embeddingsPathFor } from '@/utils/routes'
import { useUiStore } from '@/stores/uiStore'
import { useConfig } from '@/hooks/useConfig'
import { Button } from '@/components/ui/button'
import { CollapsibleInspectorSection, KeyValueTable, formatInspectorValue } from '@/components/images/InspectorPrimitives'
import { statusLabel } from '@/components/ui/badge'
import { PhaseStatusIcon, normalizeLegacyPhaseStatus } from '@/components/status/PhaseStatusIcon'
import type { ImageDetail, ImagePhaseStatusRow, ModelScoreEntry } from '@/types/api'
import type { ModelMembership } from '@/api/config'

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

// Friendly display names for score keys / model names. Keyed by the bare model
// name (after stripping `score_` / `_score`).
const SCORE_LABELS: Record<string, string> = {
  topiq: 'TOPIQ-NR',
  musiq: 'MUSIQ',
  qalign: 'Q-Align',
  cursor: 'Cursor (LLM)',
  claude: 'Claude (LLM)',
  liqe: 'LIQE',
  spaq: 'SPAQ',
  ava: 'AVA',
  paq2piq: 'PAQ2PIQ',
  koniq: 'KonIQ',
  composite: 'Composite',
  general: 'General',
  technical: 'Technical',
  aesthetic: 'Aesthetic',
}

function scoreLabel(key: string): string {
  if (key === 'score') return 'Score'
  const base = key.replace(/^score_/, '').replace(/_score$/, '')
  return SCORE_LABELS[base] ?? key
}

// Canonical IQA models shown in the inspector roster. A model renders normally
// when it is active (enabled/shadow in scoring.models config, or it has a stored
// value); otherwise it is grayed out as "off". Values resolve from
// image_model_scores, then a legacy `score_{name}` column, then a flat
// `{name}_score` field.
const KNOWN_MODELS = ['spaq', 'ava', 'liqe', 'paq2piq', 'koniq', 'musiq', 'topiq', 'qalign', 'cursor', 'claude']

function resolveModelValue(
  raw: Record<string, unknown>,
  entry: ModelScoreEntry | undefined,
  name: string,
): number | null {
  const fromBlock = entry ? entry.normalized ?? entry.raw_score : null
  if (typeof fromBlock === 'number') return fromBlock
  const legacy = raw[`score_${name}`]
  if (typeof legacy === 'number') return legacy
  const flat = raw[`${name}_score`]
  if (typeof flat === 'number') return flat
  return null
}

function ModelScoresTable({
  data,
  modelScores,
  scoringModels,
}: {
  data: ImageDetail
  modelScores: Record<string, ModelScoreEntry>
  scoringModels: Record<string, ModelMembership>
}) {
  const raw = data as unknown as Record<string, unknown>
  return (
    <div className="border border-[#3c3c3c] rounded overflow-hidden mt-2 text-[11px]">
      <table className="w-full border-collapse">
        <tbody>
          {KNOWN_MODELS.map((name) => {
            const entry = modelScores[name]
            const value = resolveModelValue(raw, entry, name)
            const membership = scoringModels[name]
            const configActive = !!(membership && (membership.enabled || membership.shadow))
            const isActive = value != null || configActive
            const isShadow = !!(entry?.is_shadow || membership?.shadow)
            return (
              <tr
                key={name}
                className={clsx(
                  'border-b border-[#3c3c3c] last:border-b-0 hover:bg-[#2a2a2a]',
                  !isActive && 'opacity-45',
                )}
              >
                <td className="align-top text-[#9d9d9d] px-2 py-1 w-[38%] border-r border-[#3c3c3c] font-mono shrink-0">
                  {scoreLabel(name)}
                  {isShadow && (
                    <span className="ml-1 text-[9px] px-1 rounded bg-[#3c3c3c] text-[#9d9d9d]">shadow</span>
                  )}
                  {!isActive && (
                    <span className="ml-1 text-[9px] px-1 rounded bg-[#2a2a2a] text-[#6d6d6d]">off</span>
                  )}
                </td>
                <td className="align-top text-[#cccccc] px-2 py-1 font-mono whitespace-pre-wrap break-all">
                  {value != null ? formatInspectorValue(value) : '—'}
                  {entry?.status && entry.status !== 'success' && (
                    <span className="ml-1 text-[#f44747]">({entry.status})</span>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
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
  const skip = new Set(['file_paths', 'resolved_path', 'phase_statuses', 'model_scores'])
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
            <th className="px-2 py-1 font-semibold">Data Status</th>
            <th className="px-2 py-1 font-semibold">Last Run Activity</th>
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
            const legacyKey = normalizeLegacyPhaseStatus(
              typeof rawStatus === 'string' ? rawStatus : '',
            )
            const dataStatusText = isString
              ? row
              : rawStatus
                ? statusLabel(legacyKey)
                : '—'
            
            const lastRunAction = isString ? null : r?.last_run_action;
            const actionText = lastRunAction?.action ? lastRunAction.action : '—';
            const actionReason = lastRunAction?.reason ? `(${lastRunAction.reason})` : '';
            const actionDisplay = lastRunAction ? `${actionText} ${actionReason}`.trim() : '—';
            
            return (
              <tr key={code} className="border-b border-[var(--color-border-muted)] hover:bg-[var(--color-bg-tertiary)]">
                <td className="px-2 py-1 font-mono text-[var(--color-accent-bright)]">{code}</td>
                <td className="px-2 py-1">
                  <div className="flex items-center gap-1.5">
                    <PhaseStatusIcon status={typeof rawStatus === 'string' ? rawStatus : ''} />
                    <span>{dataStatusText}</span>
                  </div>
                </td>
                <td className="px-2 py-1">
                  <span className={`px-1.5 py-0.5 rounded ${
                    lastRunAction?.action === 'failed' ? 'bg-[var(--color-danger-muted)] text-[var(--color-danger)]' :
                    lastRunAction?.action === 'processed' ? 'bg-[var(--color-success-muted)] text-[var(--color-success)]' :
                    lastRunAction?.action === 'skipped' ? 'bg-[var(--color-warning-muted)] text-[var(--color-warning)]' :
                    lastRunAction?.action === 'unchanged' ? 'text-[var(--color-text-muted)]' :
                    'text-[var(--color-text-muted)]'
                  }`}>
                    {actionDisplay}
                  </span>
                </td>
                <td className="px-2 py-1 text-[var(--color-text-muted)] font-mono">
                  {isString ? '—' : r?.updated_at ? String(r.updated_at).slice(0, 19) : '—'}
                </td>
                <td className="px-2 py-1">{isString ? '—' : (r?.attempt_count ?? '—')}</td>
                <td className="px-2 py-1 text-[var(--color-danger)] max-w-xs truncate" title={isString ? '' : r?.last_error ?? ''}>
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
  const { config } = useConfig()

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

  const runJobMut = useMutation({
    mutationFn: () => {
      const path = data?.resolved_path || data?.file_path
      if (!path) throw new Error('No path available to run job')
      return runsApi.submit({
        scope_type: 'file',
        scope_paths: [path],
      })
    },
    onSuccess: (res) => {
      if (res?.run_id) {
        navigate(`/runs/${res.run_id}`)
      }
    },
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
  const scoringModels = config?.scoring_models ?? {}
  const knownModelSet = new Set(KNOWN_MODELS)
  // Per-model keys are rendered by the roster; keep only aggregates here.
  const aggregateScores = parts.scores.filter(
    ([k]) => !knownModelSet.has(k.replace(/^score_/, '').replace(/_score$/, '')),
  )

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
        <div className="ml-auto shrink-0 flex items-center gap-3">
          <Button
            size="xs"
            variant="secondary"
            onClick={() => runJobMut.mutate()}
            loading={runJobMut.isPending}
            title="Run pipeline for this image"
          >
            <Play size={12} />
            Run Job
          </Button>
          <div className="flex items-center gap-2 border-l border-[#3c3c3c] pl-3">
            <Link
              to={embeddingsPathFor(data.id)}
              className="text-[10px] text-[#9d9d9d] hover:text-[#4fc1ff] transition-colors"
              title="Open this image in Vector DB"
            >
              Vector DB
            </Link>
          <span className="text-[10px] text-[#6d6d6d] font-mono">
            id{' '}
            <Link
              to={imageInspectorPath(data.id)}
              className="text-[#4fc1ff] hover:underline cursor-pointer"
            >
              {data.id}
            </Link>
          </span>
          </div>
        </div>
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

            <CollapsibleInspectorSection title="Scores" badge={`${KNOWN_MODELS.length}`} defaultOpen>
              {aggregateScores.length > 0 && (
                <KeyValueTable entries={aggregateScores} dense labelFor={scoreLabel} />
              )}
              <ModelScoresTable
                data={data}
                modelScores={data.model_scores ?? {}}
                scoringModels={scoringModels}
              />
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
