import { useState, useEffect } from 'react'
import { Link, useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { ArrowLeft, Play } from 'lucide-react'
import { galleryApi } from '@/api/gallery'
import { runsApi } from '@/api/runs'
import { dbExplorerImagePath, folderPath, imageInspectorPath, stackPath } from '@/utils/routes'
import { useUiStore } from '@/stores/uiStore'
import { useConfig } from '@/hooks/useConfig'
import { Button } from '@/components/ui/button'
import {
  CollapsibleInspectorSection,
  KeyValueTable,
  formatInspectorValue,
  formatScoreValue,
} from '@/components/images/InspectorPrimitives'
import { partitionScalars } from '@/components/images/imageInspectorPartition'
import {
  CullingInspectorSection,
  ProvenanceInspectorSection,
  IndexingInspectorSection,
  EmbeddingsInspectorSection,
  TechnicalFailureInspectorSection,
  PathsInspectorSection,
} from '@/components/images/inspectorSections'
import { statusLabel } from '@/components/ui/badge'
import { PhaseStatusIcon, normalizeLegacyPhaseStatus } from '@/components/status/PhaseStatusIcon'
import type { ImageDetail, ImagePhaseStatusRow, ModelScoreEntry } from '@/types/api'

function detailPreviewSrc(image: ImageDetail): string | null {
  const full = image.resolved_path || image.file_path
  if (full) return `/source-image?path=${encodeURIComponent(full)}`
  if (image.thumbnail_path) {
    return `/source-image?path=${encodeURIComponent(image.thumbnail_path)}&thumb=1`
  }
  return null
}

import {
  resolveModelValue,
  resolveVisibleModels,
  scoreLabel,
} from '@/constants/scoreModels'

const INSPECTOR_NAV: { id: string; label: string }[] = [
  { id: 'identity', label: 'Identity' },
  { id: 'paths', label: 'Paths' },
  { id: 'scores', label: 'Scores' },
  { id: 'user', label: 'Metadata' },
  { id: 'culling', label: 'Culling' },
  { id: 'dates', label: 'Dates' },
  { id: 'phases', label: 'Phases' },
  { id: 'audit', label: 'Audit' },
  { id: 'provenance', label: 'Provenance' },
  { id: 'indexing', label: 'Indexing' },
  { id: 'embeddings', label: 'Embeddings' },
  { id: 'exif', label: 'EXIF' },
  { id: 'xmp', label: 'XMP' },
]

function InspectorSectionNav({
  extra,
  onCollapseAll,
}: {
  extra?: { id: string; label: string }[]
  onCollapseAll: () => void
}) {
  const items = [...INSPECTOR_NAV, ...(extra ?? [])]
  return (
    <nav
      className="flex flex-wrap items-center gap-1 mb-2 pb-2 border-b border-[var(--color-border-muted)] sticky top-0 z-[2] bg-[var(--color-bg-primary)]"
      aria-label="Inspector sections"
    >
      {items.map((s) => (
        <button
          key={s.id}
          type="button"
          onClick={() =>
            document.getElementById(`inspector-section-${s.id}`)?.scrollIntoView({
              behavior: 'smooth',
              block: 'start',
            })
          }
          className="text-[10px] px-2 py-0.5 rounded border border-[var(--color-border-muted)] text-[var(--color-text-secondary)] hover:text-[var(--color-accent-bright)] hover:border-[var(--color-accent)] transition-colors"
        >
          {s.label}
        </button>
      ))}
      <button
        type="button"
        onClick={onCollapseAll}
        className="ml-auto text-[10px] px-2 py-0.5 rounded text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-bg-elevated)] transition-colors"
      >
        Collapse all
      </button>
    </nav>
  )
}

function ModelScoresTable({
  data,
  modelScores,
  visibleModels,
}: {
  data: ImageDetail
  modelScores: Record<string, ModelScoreEntry>
  visibleModels: string[]
}) {
  const raw = data as unknown as Record<string, unknown>
  return (
    <div className="border border-[var(--color-border-muted)] rounded overflow-hidden mt-2 text-[11px]">
      <table className="w-full border-collapse">
        <tbody>
          {visibleModels.map((name) => {
            const entry = modelScores[name]
            const value = resolveModelValue(raw, modelScores, name)
            const isShadow = !!entry?.is_shadow
            return (
              <tr
                key={name}
                className="border-b border-[var(--color-border-muted)] last:border-b-0 hover:bg-[var(--color-bg-tertiary)]"
              >
                <td className="align-top text-[var(--color-text-secondary)] px-2 py-1 w-[38%] border-r border-[var(--color-border-muted)] font-mono shrink-0">
                  <span className="inline-flex items-center gap-1 flex-wrap">
                    <span>{scoreLabel(name)}</span>
                    {isShadow && (
                      <span className="text-[9px] px-1 rounded bg-[var(--color-bg-elevated)] text-[var(--color-text-secondary)]">
                        shadow
                      </span>
                    )}
                  </span>
                </td>
                <td className="align-top text-[var(--color-text-primary)] px-2 py-1 font-mono whitespace-pre-wrap break-all">
                  {value != null ? formatScoreValue(value) : '—'}
                  {entry?.status && entry.status !== 'success' && (
                    <span className="ml-1 text-[var(--color-danger)]">({entry.status})</span>
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

function ImageAuditlogSection({
  imageId,
  collapseAllToken,
}: {
  imageId: number
  collapseAllToken: number
}) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['images', imageId, 'auditlog'],
    queryFn: () => galleryApi.getAuditlog(imageId, 40),
    staleTime: 30_000,
  })
  const items = data?.items ?? []
  return (
    <CollapsibleInspectorSection
      title="Phase audit log"
      badge={items.length ? String(items.length) : undefined}
      defaultOpen={false}
      sectionId="audit"
      collapseAllToken={collapseAllToken}
    >
      {isLoading && <div className="text-xs text-[var(--color-text-muted)]">Loading audit trail…</div>}
      {isError && <div className="text-xs text-red-400/90">Could not load auditlog.</div>}
      {!isLoading && !isError && items.length === 0 && (
        <div className="text-xs text-[var(--color-text-muted)]">No audit entries.</div>
      )}
      {!isLoading && items.length > 0 && (
        <ul className="text-[11px] font-mono space-y-1 max-h-48 overflow-auto">
          {items.map((entry, idx) => {
            const patch = entry.patch as { op?: string; path?: string; value?: string; oldValue?: string }[] | undefined
            const change = Array.isArray(patch) ? patch[0] : null
            const runLink =
              entry.run_id != null ? (
                <Link to={`/runs/${entry.run_id}`} className="text-[var(--color-accent-bright)] hover:underline">
                  #{entry.run_id}
                </Link>
              ) : (
                '—'
              )
            return (
              <li key={`${entry.created_at}-${idx}`} className="text-[var(--color-text-secondary)]">
                <span className="text-[var(--color-text-muted)]">{String(entry.created_at ?? '').slice(0, 19)}</span>
                {' '}
                {entry.phase_code ?? '—'} {change?.oldValue ?? '?'}→{change?.value ?? '?'}
                {' '}
                run {runLink}
              </li>
            )
          })}
        </ul>
      )}
    </CollapsibleInspectorSection>
  )
}

function PhaseStatusTable({ phases }: { phases: NonNullable<ImageDetail['phase_statuses']> }) {
  const rows = Object.entries(phases)
  if (rows.length === 0) {
    return <div className="text-xs text-[var(--color-text-muted)]">No phase rows.</div>
  }
  return (
    <div className="border border-[var(--color-border-muted)] rounded overflow-auto max-h-64">
      <table className="w-full text-[11px] border-collapse min-w-[36rem]">
        <thead className="bg-[var(--color-bg-primary)] sticky top-0">
          <tr className="text-left text-[var(--color-text-secondary)] border-b border-[var(--color-border-muted)]">
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
  collapseAllToken,
}: {
  imageId: number
  kind: 'exif' | 'xmp'
  title: string
  collapseAllToken?: number
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
      sectionId={kind}
      collapseAllToken={collapseAllToken}
      badge={loaded && q.data ? `${Object.keys(q.data).length} fields` : undefined}
    >
      {!loaded && (
        <ButtonLoad onClick={() => setLoaded(true)} label={`Load ${kind.toUpperCase()}…`} />
      )}
      {loaded && q.isLoading && <div className="text-xs text-[var(--color-text-muted)]">Loading…</div>}
      {loaded && q.isError && (
        <div className="text-xs text-[var(--color-danger)]">{(q.error as Error)?.message ?? 'Request failed'}</div>
      )}
      {loaded && q.data && Object.keys(q.data).length === 0 && (
        <div className="text-xs text-[var(--color-text-muted)]">No cached row in the database.</div>
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
      className="text-xs px-2 py-1 rounded border border-[var(--color-border)] text-[var(--color-accent-bright)] hover:bg-[var(--color-bg-elevated)] transition-colors"
    >
      {label}
    </button>
  )
}

export function ImageInspectorPage() {
  const { imageId: rawId } = useParams<{ imageId: string }>()
  const id = rawId ? parseInt(rawId, 10) : NaN
  const navigate = useNavigate()
  const [collapseAllToken, setCollapseAllToken] = useState(0)

  const sortBy = useUiStore((s) => s.sortBy)
  const order = useUiStore((s) => s.sortOrder)
  const selectedScopePath = useUiStore((s) => s.selectedScopePath)
  const { config, isDbExplorerEnabled } = useConfig()

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
    return <div className="p-4 text-sm text-[var(--color-text-muted)]">Invalid image id.</div>
  }

  if (isLoading) {
    return <div className="p-4 text-sm text-[var(--color-text-muted)]">Loading image…</div>
  }

  if (error || !data) {
    return (
      <div className="p-4 space-y-2">
        <div className="text-sm text-[var(--color-danger)]">Could not load image.</div>
        <Link to="/images" className="text-xs text-[var(--color-accent-bright)] hover:underline inline-flex items-center gap-1">
          <ArrowLeft size={12} /> Back to Images
        </Link>
      </div>
    )
  }

  const src = detailPreviewSrc(data)
  const parts = partitionScalars(data)
  const scoringModels = config?.scoring_models ?? {}
  const visibleModels = resolveVisibleModels(scoringModels)
  const visibleModelSet = new Set(visibleModels)
  // Per-model keys are rendered by the roster; keep only aggregates here.
  const aggregateScores = parts.scores.filter(
    ([k]) => !visibleModelSet.has(k.replace(/^score_/, '').replace(/_score$/, '')),
  )

  const extraNav = [
    ...(data.technical_failure_detection ? [{ id: 'technical', label: 'Technical' }] : []),
    ...(parts.unmapped.length > 0 ? [{ id: 'unmapped', label: 'Unmapped' }] : []),
  ]

  return (
    <div className="flex flex-col h-full min-h-0 bg-[var(--color-bg-primary)] overflow-hidden">
      <div className="shrink-0 flex items-center gap-3 px-4 py-2 border-b border-[var(--color-border-muted)] bg-[var(--color-bg-secondary)]">
        <Link
          to="/images"
          className="text-xs text-[var(--color-accent-bright)] hover:underline inline-flex items-center gap-1 shrink-0"
        >
          <ArrowLeft size={12} /> Images
        </Link>
        <span className="text-sm font-medium text-[var(--color-text-primary)] truncate">{data.file_name}</span>
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
          <div className="flex items-center gap-2 border-l border-[var(--color-border-muted)] pl-3 text-xs">
            {isDbExplorerEnabled ? (
              <Link
                to={dbExplorerImagePath(data.id)}
                className="text-[var(--color-text-secondary)] hover:text-[var(--color-accent-bright)] transition-colors"
                title="Open this row in DB Explorer"
              >
                DB
              </Link>
            ) : null}
            <span className="text-[var(--color-text-muted)] font-mono">
              id{' '}
              <Link
                to={imageInspectorPath(data.id)}
                className="text-[var(--color-accent-bright)] hover:underline cursor-pointer"
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
            <div className="rounded border border-[var(--color-border-muted)] bg-[var(--color-bg-preview)] min-h-[200px] max-h-[50vh] lg:max-h-[calc(100vh-8rem)] flex items-center justify-center p-2">
              {src ? (
                <img
                  src={src}
                  alt={data.file_name}
                  className="max-w-full max-h-[min(50vh,480px)] object-contain"
                />
              ) : (
                <span className="text-sm text-[var(--color-text-muted)]">No preview path</span>
              )}
            </div>
          </div>

          <div className="flex-1 min-w-0 space-y-3">
            <InspectorSectionNav
              extra={extraNav}
              onCollapseAll={() => setCollapseAllToken((t) => t + 1)}
            />

            <CollapsibleInspectorSection
              title="Identity & storage"
              defaultOpen
              sectionId="identity"
              collapseAllToken={collapseAllToken}
            >
              <KeyValueTable
                entries={parts.identity}
                dense
                renderValue={(k, v) => {
                  if (k === 'id' && typeof v === 'number') {
                    return (
                      <Link
                        to={imageInspectorPath(v)}
                        className="text-[var(--color-accent-bright)] hover:underline cursor-pointer"
                      >
                        {v}
                      </Link>
                    )
                  }
                  if (k === 'folder_id' && typeof v === 'number' && v > 0) {
                    return (
                      <Link
                        to={folderPath(v)}
                        className="text-[var(--color-accent-bright)] hover:underline cursor-pointer"
                      >
                        {v}
                      </Link>
                    )
                  }
                  if (k === 'stack_id' && typeof v === 'number' && v > 0) {
                    return (
                      <Link
                        to={stackPath(v)}
                        className="text-[var(--color-accent-bright)] hover:underline cursor-pointer"
                      >
                        {v}
                      </Link>
                    )
                  }
                  return formatInspectorValue(v)
                }}
              />
            </CollapsibleInspectorSection>

            <PathsInspectorSection
              data={data}
              pathEntries={parts.paths}
              collapseAllToken={collapseAllToken}
            />

            <CollapsibleInspectorSection
              title="Scores"
              badge={`${visibleModels.length}`}
              defaultOpen
              sectionId="scores"
              collapseAllToken={collapseAllToken}
            >
              {aggregateScores.length > 0 && (
                <KeyValueTable
                  entries={aggregateScores}
                  dense
                  labelFor={scoreLabel}
                  renderValue={(_, v) => formatScoreValue(v)}
                />
              )}
              <ModelScoresTable
                data={data}
                modelScores={data.model_scores ?? {}}
                visibleModels={visibleModels}
              />
            </CollapsibleInspectorSection>

            <CollapsibleInspectorSection
              title="User metadata"
              defaultOpen
              sectionId="user"
              collapseAllToken={collapseAllToken}
            >
              {parts.user.length === 0 ? (
                <div className="text-xs text-[var(--color-text-muted)]">—</div>
              ) : (
                <KeyValueTable entries={parts.user} dense />
              )}
            </CollapsibleInspectorSection>

            <CullingInspectorSection
              data={data}
              entries={parts.culling}
              collapseAllToken={collapseAllToken}
            />

            <CollapsibleInspectorSection
              title="Dates"
              defaultOpen={false}
              sectionId="dates"
              collapseAllToken={collapseAllToken}
            >
              <KeyValueTable entries={parts.dates} dense />
            </CollapsibleInspectorSection>

            <CollapsibleInspectorSection
              title="Pipeline phases"
              badge={data.phase_statuses ? `${Object.keys(data.phase_statuses).length}` : '0'}
              defaultOpen
              sectionId="phases"
              collapseAllToken={collapseAllToken}
            >
              {data.phase_statuses && Object.keys(data.phase_statuses).length > 0 ? (
                <PhaseStatusTable phases={data.phase_statuses} />
              ) : (
                <div className="text-xs text-[var(--color-text-muted)]">No phase status rows.</div>
              )}
            </CollapsibleInspectorSection>

            {data.data_quality_flags && Object.values(data.data_quality_flags).some(Boolean) && (
              <CollapsibleInspectorSection
                title="Data quality"
                badge="gap"
                defaultOpen
                sectionId="data-quality"
                collapseAllToken={collapseAllToken}
              >
                <ul className="text-xs text-amber-200/90 list-disc pl-4 space-y-1">
                  {data.data_quality_flags.keywords_data_gap && (
                    <li>Keywords phase is terminal but keywords/captions are incomplete in the database.</li>
                  )}
                  {data.data_quality_flags.scoring_data_gap && (
                    <li>Scoring phase is done but score_general is missing or zero.</li>
                  )}
                </ul>
              </CollapsibleInspectorSection>
            )}

            <ImageAuditlogSection imageId={id} collapseAllToken={collapseAllToken} />

            <ProvenanceInspectorSection entries={parts.provenance} collapseAllToken={collapseAllToken} />
            <IndexingInspectorSection data={data} collapseAllToken={collapseAllToken} />
            <EmbeddingsInspectorSection
              embeddings={data.embeddings_present}
              collapseAllToken={collapseAllToken}
            />
            {data.technical_failure_detection && (
              <TechnicalFailureInspectorSection
                detection={data.technical_failure_detection}
                collapseAllToken={collapseAllToken}
              />
            )}

            <LazyMetadataSection imageId={id} kind="exif" title="EXIF (cached)" collapseAllToken={collapseAllToken} />
            <LazyMetadataSection imageId={id} kind="xmp" title="XMP (cached)" collapseAllToken={collapseAllToken} />

            {parts.unmapped.length > 0 && (
              <CollapsibleInspectorSection
                title="Unmapped fields"
                badge={`${parts.unmapped.length}`}
                defaultOpen={false}
                sectionId="unmapped"
                collapseAllToken={collapseAllToken}
              >
                <KeyValueTable entries={parts.unmapped} dense />
              </CollapsibleInspectorSection>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
