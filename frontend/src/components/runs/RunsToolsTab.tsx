import { useMemo, useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Wrench, RefreshCcw, ExternalLink, Play, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { toolsApi } from '@/api/tools'
import {
  FULL_PIPELINE,
  MAINTENANCE_QUEUED,
  PIPELINE_TOOLS_HEADER,
  PRUNE_MISSING,
  RECONCILE,
  SCHEDULE_FOLDER_QUALITY,
  SECTION,
  STALE_PHASE,
  TOOLS_API,
} from '@/constants/pipelineTools'
import { usePipelineToolAction } from '@/hooks/usePipelineToolAction'
import { useUiStore } from '@/stores/uiStore'
import { Card, CardTitle } from '@/components/ui/card'

const PANEL = 'p-3 rounded bg-[#1e1e1e] border border-[#3c3c3c]'

function ToolCard({
  title,
  description,
  buttonText,
  onAction,
  isPending,
  disabled,
  icon: Icon = Play,
  variant = 'primary' as const,
}: {
  title: string
  description: string
  buttonText: string
  onAction: () => void
  isPending?: boolean
  disabled?: boolean
  icon?: React.ComponentType<{ size?: number; className?: string }>
  variant?: 'primary' | 'secondary' | 'outline'
}) {
  return (
    <div className={`flex flex-col gap-2 ${PANEL}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1">
          <h3 className="text-xs font-semibold text-[#cccccc]">{title}</h3>
          <p className="text-[11px] text-[#9d9d9d] mt-1 leading-relaxed">{description}</p>
        </div>
        <Button
          variant={variant}
          size="sm"
          onClick={onAction}
          disabled={disabled || isPending}
          loading={isPending}
          className="h-7 px-3 text-[11px] gap-1 shrink-0"
        >
          <Icon size={12} />
          {buttonText}
        </Button>
      </div>
    </div>
  )
}

function TierSection({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle: string
  children: ReactNode
}) {
  return (
    <section className="rounded-lg border border-[#3c3c3c] bg-[#252526] p-4">
      <div className="mb-4">
        <h2 className="text-sm font-semibold text-[#cccccc]">{title}</h2>
        <p className="text-xs text-[#9d9d9d] mt-0.5">{subtitle}</p>
      </div>
      <div className="grid grid-cols-1 gap-3">{children}</div>
    </section>
  )
}

function ResultBanner({ text, ok }: { text: string; ok: boolean }) {
  return (
    <div
      className={`flex items-start gap-2 text-xs rounded px-3 py-2 border ${
        ok
          ? 'bg-[#1e3a1e]/30 text-[#89d185] border-[#89d185]/20'
          : 'bg-[#3a1e1e]/30 text-[#f44747] border-[#f44747]/20'
      }`}
    >
      <div className="mt-0.5">{ok ? <RefreshCcw size={14} /> : <AlertCircle size={14} />}</div>
      <p className="leading-relaxed">{text}</p>
    </div>
  )
}

export function RunsToolsTab() {
  const selectedScopePath = useUiStore((s) => s.selectedScopePath)
  const setPendingTreeRevealPaths = useUiStore((s) => s.setPendingTreeRevealPaths)

  const [recalcScope, setRecalcScope] = useState<'all' | 'selected_folder'>('selected_folder')
  const [showRecalcConfirm, setShowRecalcConfirm] = useState(false)
  const [scheduleHealGlobal, setScheduleHealGlobal] = useState(false)

  const {
    run,
    envelope,
    isPending,
    pendingId,
    lastBanner,
    recalcSummary,
    scheduleQualityStats,
  } = usePipelineToolAction({
    onFullPipelineQueued: (folderPath) => setPendingTreeRevealPaths([folderPath]),
    onRecalculateSuccess: () => setShowRecalcConfirm(false),
  })

  const staleQuery = useQuery({
    queryKey: ['maintenance-stale-phases', STALE_PHASE.minAgeSeconds],
    queryFn: () => toolsApi.staleRunningPhases(STALE_PHASE.minAgeSeconds, STALE_PHASE.probeLimit),
    refetchInterval: STALE_PHASE.refetchIntervalMs,
  })

  const selectedScopeMissing = recalcScope === 'selected_folder' && !selectedScopePath?.trim()
  const recalcButtonHint = useMemo(() => {
    if (recalcScope === 'all') return 'Entire database'
    return selectedScopePath?.trim() ? `Selected: ${selectedScopePath.trim()}` : 'Select a folder first'
  }, [recalcScope, selectedScopePath])

  const toolsLocked =
    isPending || staleQuery.isFetching

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-2">
          <Wrench className="text-[#4fc1ff]" size={20} />
          <div>
            <p className="text-sm font-medium text-[#cccccc]">{PIPELINE_TOOLS_HEADER.title}</p>
            <p className="text-xs text-[#9d9d9d] mt-0.5">{PIPELINE_TOOLS_HEADER.subtitle}</p>
          </div>
        </div>
        <Link
          to="/diagnostics"
          className="inline-flex items-center gap-1 text-xs text-[#4fc1ff] hover:underline shrink-0"
        >
          Diagnostics
          <ExternalLink size={12} />
        </Link>
      </div>

      {lastBanner && <ResultBanner ok={lastBanner.ok} text={lastBanner.text} />}

      <TierSection title={SECTION.reconciliation.title} subtitle={SECTION.reconciliation.subtitle}>
        <div className={`flex flex-col gap-2 ${PANEL}`}>
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-semibold text-[#cccccc]">{RECONCILE.name}</h3>
              <div className="flex gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => staleQuery.refetch()}
                  disabled={toolsLocked}
                  className="h-7 px-2 text-[11px] gap-1"
                >
                  <RefreshCcw size={12} className={staleQuery.isFetching ? 'animate-spin' : ''} />
                  Refresh
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() =>
                    run({
                      kind: 'maintenance',
                      trackingId: 'reconcileStale',
                      action: RECONCILE.action,
                      label: RECONCILE.name,
                      limit: RECONCILE.limit,
                      invalidateStalePhases: true,
                    })
                  }
                  disabled={toolsLocked}
                  loading={isPending && pendingId === 'reconcileStale'}
                  className="h-7 px-3 text-[11px]"
                >
                  Run Fix
                </Button>
              </div>
            </div>
            <p className="text-[11px] text-[#9d9d9d] leading-relaxed">{RECONCILE.description}</p>
            {staleQuery.data && (
              <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-[#6d6d6d] font-mono">
                <span>
                  Stuck rows: <b className="text-[#cccccc]">{staleQuery.data.count_estimate}</b>
                </span>
                <span>
                  Reconcilable:{' '}
                  <b className="text-[#cccccc]">{staleQuery.data.reconcilable_count ?? '0'}</b>
                </span>
              </div>
            )}
          </div>
        </div>

        <ToolCard
          title={TOOLS_API.fixDb.name}
          description={TOOLS_API.fixDb.description}
          buttonText={TOOLS_API.fixDb.button}
          onAction={() => envelope.fixDb()}
          isPending={isPending && pendingId === 'fixDb'}
          disabled={toolsLocked}
          variant={TOOLS_API.fixDb.variant}
        />
        <ToolCard
          title={TOOLS_API.backfillIndexMeta.name}
          description={TOOLS_API.backfillIndexMeta.description}
          buttonText={TOOLS_API.backfillIndexMeta.button}
          onAction={() => envelope.backfillIndexMeta()}
          isPending={isPending && pendingId === 'backfillIndexMeta'}
          disabled={toolsLocked}
          variant={TOOLS_API.backfillIndexMeta.variant}
        />
        <ToolCard
          title={TOOLS_API.repairThumbnailPaths.name}
          description={TOOLS_API.repairThumbnailPaths.description}
          buttonText={TOOLS_API.repairThumbnailPaths.button}
          onAction={() => envelope.repairThumbnailPaths()}
          isPending={isPending && pendingId === 'repairThumbnailPaths'}
          disabled={toolsLocked}
          variant={TOOLS_API.repairThumbnailPaths.variant}
        />
      </TierSection>

      <TierSection title={SECTION.recalculate.title} subtitle={SECTION.recalculate.subtitle}>
        <ul className="list-disc pl-5 text-[11px] text-[#9d9d9d] space-y-1 mb-1 max-w-3xl">
          <li>
            Sets <span className="text-[#cccccc]">indexing</span> and{' '}
            <span className="text-[#cccccc]">metadata</span> to done when{' '}
            <span className="text-[#cccccc]">scoring</span> is done but those phases are missing.
          </li>
          <li>
            Aligns the <span className="text-[#cccccc]">keywords</span> phase when keyword rows exist.
          </li>
          <li>
            Repairs <span className="text-[#cccccc]">culling</span> rows stuck in{' '}
            <span className="text-[#cccccc]">failed</span> when stack or embedding data is present.
          </li>
          <li>Rebuilds folder aggregate flags and caches.</li>
        </ul>
        <div className={`${PANEL} space-y-2`}>
          <div className="flex flex-wrap items-center gap-3">
            <label className="text-xs text-[#9d9d9d] inline-flex items-center gap-1.5">
              <input
                type="radio"
                name="recalc-scope"
                checked={recalcScope === 'selected_folder'}
                onChange={() => setRecalcScope('selected_folder')}
                disabled={toolsLocked}
              />
              Selected folder
            </label>
            <label className="text-xs text-[#9d9d9d] inline-flex items-center gap-1.5">
              <input
                type="radio"
                name="recalc-scope"
                checked={recalcScope === 'all'}
                onChange={() => setRecalcScope('all')}
                disabled={toolsLocked}
              />
              Entire database
            </label>
          </div>

          <p className="text-xs text-[#6d6d6d]">{recalcButtonHint}</p>

          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="primary"
              size="sm"
              onClick={() => setShowRecalcConfirm(true)}
              disabled={toolsLocked || selectedScopeMissing}
              loading={isPending && pendingId === 'recalculate'}
              className="h-7 px-3 text-[11px]"
            >
              Recalculate Status from Data
            </Button>
          </div>

          {selectedScopeMissing && (
            <p className="text-xs text-[#6d6d6d]">Select a folder in Scope Navigator to run this scope.</p>
          )}

          {showRecalcConfirm && (
            <div className="rounded border border-[#6f4e00] bg-[#3a2d00] p-3">
              <p className="text-xs text-[#f2cc60]">
                Confirm recalculation for{' '}
                <span className="font-medium">
                  {recalcScope === 'all' ? 'entire database' : selectedScopePath?.trim() || 'selected folder'}
                </span>
                ?
              </p>
              <p className="text-xs text-[#d7ba7d] mt-1">
                This updates derivable per-image statuses and rebuilds folder rollups/flags.
              </p>
              <div className="flex items-center gap-2 mt-2">
                <Button
                  variant="danger"
                  size="sm"
                  onClick={() =>
                    run({
                      kind: 'recalculate',
                      trackingId: 'recalculate',
                      scope: recalcScope,
                      scopePath: recalcScope === 'selected_folder' ? selectedScopePath?.trim() || undefined : undefined,
                    })
                  }
                  disabled={toolsLocked || selectedScopeMissing}
                  loading={isPending && pendingId === 'recalculate'}
                  className="h-7 px-3 text-[11px]"
                >
                  Confirm and run
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setShowRecalcConfirm(false)}
                  disabled={toolsLocked}
                >
                  Cancel
                </Button>
              </div>
            </div>
          )}

          {recalcSummary && (
            <Card className="mt-3 border-[#3c3c3c] bg-[#1f1f1f]">
              <CardTitle className="mb-2">Last recalculation summary</CardTitle>
              <div className="space-y-1 text-xs text-[#9d9d9d]">
                <p>
                  Scope:{' '}
                  <span className="text-[#cccccc]">
                    {recalcSummary.scope === 'all' ? 'Entire database' : recalcSummary.scope_path || 'Selected folder'}
                  </span>
                </p>
                <p>
                  Changed rows (estimate):{' '}
                  <span className="text-[#cccccc] font-medium">
                    {recalcSummary.per_image_changes.total_rows_changed_estimate}
                  </span>
                </p>
                <p>
                  Per-image changes: index/meta={recalcSummary.per_image_changes.indexing_metadata_backfilled_images},
                  keywords={recalcSummary.per_image_changes.keywords_phase_backfilled_rows}, culling=
                  {recalcSummary.per_image_changes.culling_failed_to_done_rows}
                </p>
                <p>
                  Folder rebuild: recomputed={recalcSummary.folder_aggregate_changes.folders_recomputed}, keyword flags
                  updated={recalcSummary.folder_aggregate_changes.folders_marked_keywords_processed}
                </p>
                <p>
                  Remaining drift: index/meta={recalcSummary.after.missing_indexing_or_metadata_with_scoring_done},
                  keywords={recalcSummary.after.missing_keywords_status_with_keywords_data}, culling=
                  {recalcSummary.after.culling_failed_with_data_present}
                </p>
                {recalcSummary.warnings.length > 0 && (
                  <div className="mt-2 rounded border border-[#5a3a3a] bg-[#2a1a1a] p-2">
                    <p className="text-[#f44747] mb-1">Warnings</p>
                    <ul className="list-disc pl-4 space-y-0.5 text-[#d7a7a7]">
                      {recalcSummary.warnings.map((w) => (
                        <li key={w}>{w}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </Card>
          )}
        </div>
      </TierSection>

      <TierSection title={SECTION.backfill.title} subtitle={SECTION.backfill.subtitle}>
        <div className={`flex flex-col gap-2 ${PANEL}`}>
          <div className="flex items-start justify-between gap-2">
            <div className="flex-1">
              <h3 className="text-xs font-semibold text-[#cccccc]">{SCHEDULE_FOLDER_QUALITY.name}</h3>
              <p className="text-[11px] text-[#9d9d9d] mt-1 leading-relaxed">
                {SCHEDULE_FOLDER_QUALITY.description}
              </p>
              <label className="mt-2 flex items-center gap-2 text-[11px] text-[#9d9d9d] cursor-pointer">
                <input
                  type="checkbox"
                  checked={scheduleHealGlobal}
                  onChange={(e) => setScheduleHealGlobal(e.target.checked)}
                  disabled={toolsLocked}
                />
                Pre-queue global thumbnail regeneration if any folder has missing thumbs
              </label>
            </div>
            <Button
              variant="primary"
              size="sm"
              onClick={() =>
                run({
                  kind: 'scheduleFolderQuality',
                  trackingId: 'scheduleFolderQuality',
                  rootPath: selectedScopePath?.trim() || undefined,
                  healThumbnailsGlobal: scheduleHealGlobal,
                })
              }
              disabled={toolsLocked}
              loading={isPending && pendingId === 'scheduleFolderQuality'}
              className="h-7 px-3 text-[11px] gap-1 shrink-0"
            >
              <Play size={12} />
              {SCHEDULE_FOLDER_QUALITY.button}
            </Button>
          </div>
          <p className="text-[10px] text-[#6d6d6d]">
            Optional scope: select a folder in the Navigator to limit candidates to that subtree; leave unselected for
            the whole library.
          </p>
          {scheduleQualityStats && (
            <div className="mt-1 rounded border border-[#3c5c3c]/40 bg-[#1a2520]/40 px-2 py-1.5 text-[10px] text-[#8d8d8d] font-mono space-y-0.5">
              <div>
                Budget {scheduleQualityStats.budget} − active {scheduleQualityStats.active_jobs} ={' '}
                <span className="text-[#cccccc]">{scheduleQualityStats.capacity_slots}</span> slot(s) this round
              </div>
              <div>
                Scheduled {scheduleQualityStats.scheduled_this_round} · Folders still needing work:{' '}
                <span className="text-[#f2cc60]">{scheduleQualityStats.folders_remaining_after}</span>
              </div>
              {scheduleQualityStats.global_thumbnail_heal_run_id != null && (
                <div>Global thumb heal run ID: {scheduleQualityStats.global_thumbnail_heal_run_id}</div>
              )}
              {scheduleQualityStats.errors.length > 0 && (
                <div className="text-[#f44747]">Errors: {scheduleQualityStats.errors.join('; ')}</div>
              )}
            </div>
          )}
        </div>

        <div className={`flex flex-col gap-2 ${PANEL}`}>
          <div className="flex items-start justify-between gap-2">
            <div className="flex-1">
              <h3 className="text-xs font-semibold text-[#cccccc]">{FULL_PIPELINE.name}</h3>
              <p className="text-[11px] text-[#9d9d9d] mt-1 leading-relaxed">{FULL_PIPELINE.description}</p>
              {!selectedScopePath && (
                <p className="text-[10px] text-[#f44747] mt-1 italic">* Select a folder in the Navigator to enable</p>
              )}
            </div>
            <Button
              variant="primary"
              size="sm"
              onClick={() => {
                const p = selectedScopePath?.trim()
                if (!p) return
                run({ kind: 'fullPipeline', trackingId: 'fullPipeline', path: p })
              }}
              disabled={toolsLocked || !selectedScopePath?.trim()}
              loading={isPending && pendingId === 'fullPipeline'}
              className="h-7 px-3 text-[11px] gap-1 shrink-0"
            >
              <Play size={12} />
              {FULL_PIPELINE.button}
            </Button>
          </div>
        </div>

        {MAINTENANCE_QUEUED.map((t) => (
          <ToolCard
            key={t.id}
            title={t.name}
            description={t.description}
            buttonText={t.button}
            onAction={() =>
              run({
                kind: 'maintenance',
                trackingId: t.id,
                action: t.action,
                label: t.name,
                limit: t.limit,
              })
            }
            isPending={isPending && pendingId === t.id}
            disabled={toolsLocked}
            variant={t.variant}
          />
        ))}
      </TierSection>

      <TierSection title={SECTION.cleanup.title} subtitle={SECTION.cleanup.subtitle}>
        <ToolCard
          title={PRUNE_MISSING.name}
          description={PRUNE_MISSING.description}
          buttonText={PRUNE_MISSING.button}
          onAction={() =>
            run({
              kind: 'maintenance',
              trackingId: 'pruneMissing',
              action: PRUNE_MISSING.action,
              label: PRUNE_MISSING.name,
              limit: PRUNE_MISSING.limit,
            })
          }
          isPending={isPending && pendingId === 'pruneMissing'}
          disabled={toolsLocked}
          variant={PRUNE_MISSING.variant}
        />
      </TierSection>
    </div>
  )
}
