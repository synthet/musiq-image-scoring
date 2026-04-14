import { useMemo, useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Wrench, RefreshCcw, ExternalLink, Play, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { toolsApi, formatToolError, type ApiEnvelope, type RecalculateStatusSummary } from '@/api/tools'
import { runsApi } from '@/api/runs'
import { FULL_PIPELINE_STAGE_CODES } from '@/constants/pipeline'
import { MaintenanceToolsCopy } from '@/constants/runsToolsCopy'
import { useUiStore } from '@/stores/uiStore'
import { Card, CardTitle } from '@/components/ui/card'

const STALE_MIN_AGE_SECONDS = 3600
const STALE_PROBE_LIMIT = 50
const STALE_QUERY_REFETCH_INTERVAL_MS = 30000

function ToolCard({
  title,
  description,
  buttonText,
  onAction,
  isPending,
  disabled,
  icon: Icon = Play,
  variant = "primary" as const
}: {
  title: string
  description: string
  buttonText: string
  onAction: () => void
  isPending?: boolean
  disabled?: boolean
  icon?: any
  variant?: "primary" | "secondary" | "outline"
}) {
  return (
    <div className="flex flex-col gap-2 p-3 rounded bg-[#1e1e1e] border border-[#3c3c3c]">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1">
          <h3 className="text-xs font-semibold text-[#cccccc]">{title}</h3>
          <p className="text-[11px] text-[#9d9d9d] mt-1 leading-relaxed">
            {description}
          </p>
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
      <div className="grid grid-cols-1 gap-3">
        {children}
      </div>
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
      <div className="mt-0.5">
        {ok ? <RefreshCcw size={14} /> : <AlertCircle size={14} />}
      </div>
      <p className="leading-relaxed">{text}</p>
    </div>
  )
}

export function RunsToolsTab() {
  const queryClient = useQueryClient()
  const selectedScopePath = useUiStore((s) => s.selectedScopePath)
  const setPendingTreeRevealPaths = useUiStore((s) => s.setPendingTreeRevealPaths)
  const [lastAction, setLastAction] = useState<{ ok: boolean; text: string } | null>(null)
  const [recalcScope, setRecalcScope] = useState<'all' | 'selected_folder'>('selected_folder')
  const [showRecalcConfirm, setShowRecalcConfirm] = useState(false)
  const [recalcSummary, setRecalcSummary] = useState<RecalculateStatusSummary | null>(null)

  const setFromEnvelope = (label: string, r: ApiEnvelope) => {
    const ok = r.success
    const extra =
      r.data && typeof r.data === 'object' ? ` ${JSON.stringify(r.data)}` : ''
    setLastAction({ ok, text: `${label}: ${r.message}${extra}` })
  }

  const staleQuery = useQuery({
    queryKey: ['maintenance-stale-phases', STALE_MIN_AGE_SECONDS],
    queryFn: () => toolsApi.staleRunningPhases(STALE_MIN_AGE_SECONDS, STALE_PROBE_LIMIT),
    refetchInterval: STALE_QUERY_REFETCH_INTERVAL_MS,
  })

  const maintenanceMut = useMutation({
    mutationFn: (args: { action: string; label: string; limit?: number; input_path?: string }) => 
      runsApi.maintenanceStart({
        action: args.action,
        limit: args.limit,
        input_path: args.input_path,
        job_name: args.label,
      }),
    onSuccess: (r, variables) => {
      setLastAction({ 
        ok: true, 
        text: `${variables.label} job queued (Run ID: ${r.run_id}). Track progress in history.` 
      })
      void queryClient.invalidateQueries({ queryKey: ['runs'] })
      if (variables.action === 'reconcile') {
        void queryClient.invalidateQueries({ queryKey: ['maintenance-stale-phases'] })
      }
    },
    onError: (e) => setLastAction({ ok: false, text: formatToolError(e) }),
  })

  const fullPipelineMut = useMutation({
    mutationFn: () => {
      if (!selectedScopePath?.trim()) {
        return Promise.reject(new Error("Please select a folder in the Navigator first."))
      }
      return runsApi.submit({
        scope_type: 'folder_recursive',
        scope_paths: [selectedScopePath.trim()],
        stages: [...FULL_PIPELINE_STAGE_CODES],
        skip_done: true,
      })
    },
    onSuccess: (data) => {
      setLastAction({
        ok: true,
        text: `Full pipeline queued for folder (Run ID: ${data.run_id}). Position: ${data.queue_position}`,
      })
      void queryClient.invalidateQueries({ queryKey: ['runs'] })
      void queryClient.invalidateQueries({ queryKey: ['folders-tree'] })
      if (selectedScopePath?.trim()) {
        setPendingTreeRevealPaths([selectedScopePath.trim()])
      }
    },
    onError: (e) => setLastAction({ ok: false, text: formatToolError(e) }),
  })

  const recalcStatusMut = useMutation({
    mutationFn: () =>
      toolsApi.recalculateStatusFromData({
        scope: recalcScope,
        scopePath: recalcScope === 'selected_folder' ? selectedScopePath?.trim() || undefined : undefined,
      }),
    onSuccess: (r) => {
      setFromEnvelope('Recalculate status', r)
      const summaryCandidate = r.data?.summary
      if (summaryCandidate && typeof summaryCandidate === 'object') {
        setRecalcSummary(summaryCandidate as RecalculateStatusSummary)
      } else {
        setRecalcSummary(null)
      }
      void queryClient.invalidateQueries({ queryKey: ['maintenance-stale-phases'] })
      void queryClient.invalidateQueries({ queryKey: ['folders-tree'] })
      void queryClient.invalidateQueries({ queryKey: ['runs'] })
      setShowRecalcConfirm(false)
    },
    onError: (e) => {
      setLastAction({ ok: false, text: formatToolError(e) })
      setShowRecalcConfirm(false)
    },
  })

  const selectedScopeMissing = recalcScope === 'selected_folder' && !selectedScopePath?.trim()
  const recalcButtonHint = useMemo(() => {
    if (recalcScope === 'all') return 'Entire database'
    return selectedScopePath?.trim() ? `Selected: ${selectedScopePath.trim()}` : 'Select a folder first'
  }, [recalcScope, selectedScopePath])

  const toolsLocked =
    maintenanceMut.isPending ||
    fullPipelineMut.isPending ||
    recalcStatusMut.isPending ||
    staleQuery.isFetching

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-2">
          <Wrench className="text-[#4fc1ff]" size={20} />
          <div>
            <p className="text-sm font-medium text-[#cccccc]">Pipeline Tools</p>
            <p className="text-xs text-[#9d9d9d] mt-0.5">Maintain data integrity and perform batch repairs.</p>
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

      {lastAction && <ResultBanner ok={lastAction.ok} text={lastAction.text} />}

      {/* Tier 1 */}
      <TierSection 
        title={MaintenanceToolsCopy.tier1.title} 
        subtitle={MaintenanceToolsCopy.tier1.subtitle}
      >
        <div className="p-3 rounded bg-[#1e1e1e] border border-[#3c3c3c]">
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-semibold text-[#cccccc]">
                {MaintenanceToolsCopy.tier1.tools.reconcile.name}
              </h3>
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
                  onClick={() => maintenanceMut.mutate({ 
                    action: 'reconcile', 
                    label: MaintenanceToolsCopy.tier1.tools.reconcile.name,
                    limit: MaintenanceToolsCopy.tier1.tools.reconcile.limit
                  })}
                  disabled={toolsLocked}
                  loading={maintenanceMut.isPending && maintenanceMut.variables?.action === 'reconcile'}
                  className="h-7 px-3 text-[11px]"
                >
                  Run Fix
                </Button>
              </div>
            </div>
            <p className="text-[11px] text-[#9d9d9d] leading-relaxed">
              {MaintenanceToolsCopy.tier1.tools.reconcile.description}
            </p>
            {staleQuery.data && (
              <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-[#6d6d6d] font-mono">
                <span>Stuck rows: <b className="text-[#cccccc]">{staleQuery.data.count_estimate}</b></span>
                <span>Reconcilable: <b className="text-[#cccccc]">{staleQuery.data.reconcilable_count ?? '0'}</b></span>
              </div>
            )}
          </div>
        </div>

        <ToolCard
          title={MaintenanceToolsCopy.tier1.tools.fixDb.name}
          description={MaintenanceToolsCopy.tier1.tools.fixDb.description}
          buttonText="Start"
          onAction={() => maintenanceMut.mutate({ 
            action: 'fix_db', 
            label: MaintenanceToolsCopy.tier1.tools.fixDb.name
          })}
          isPending={maintenanceMut.isPending && maintenanceMut.variables?.action === 'fix_db'}
          disabled={toolsLocked}
        />
      </TierSection>

      {/* Recalculate status (sync API — not queued as a maintenance run) */}
      <TierSection
        title="Recalculate status from data"
        subtitle={
          'Recomputes derivable per-image phase states and rebuilds folder rollups. ' +
          'Use after crashes, import drifts, or legacy migrations when badges look inconsistent. ' +
          'Replaces the old “Legacy Phase Backfill” control (index/metadata only).'
        }
      >
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
        <div className="p-3 rounded bg-[#1e1e1e] border border-[#3c3c3c] space-y-2">
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
              loading={recalcStatusMut.isPending}
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
                  onClick={() => recalcStatusMut.mutate()}
                  disabled={toolsLocked || selectedScopeMissing}
                  loading={recalcStatusMut.isPending}
                  className="h-7 px-3 text-[11px]"
                >
                  Confirm and run
                </Button>
                <Button variant="secondary" size="sm" onClick={() => setShowRecalcConfirm(false)} disabled={toolsLocked}>
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
                  Scope: <span className="text-[#cccccc]">{recalcSummary.scope === 'all' ? 'Entire database' : recalcSummary.scope_path || 'Selected folder'}</span>
                </p>
                <p>
                  Changed rows (estimate):{' '}
                  <span className="text-[#cccccc] font-medium">{recalcSummary.per_image_changes.total_rows_changed_estimate}</span>
                </p>
                <p>
                  Per-image changes: index/meta={recalcSummary.per_image_changes.indexing_metadata_backfilled_images}, keywords={recalcSummary.per_image_changes.keywords_phase_backfilled_rows}, culling={recalcSummary.per_image_changes.culling_failed_to_done_rows}
                </p>
                <p>
                  Folder rebuild: recomputed={recalcSummary.folder_aggregate_changes.folders_recomputed}, keyword flags updated={recalcSummary.folder_aggregate_changes.folders_marked_keywords_processed}
                </p>
                <p>
                  Remaining drift: index/meta={recalcSummary.after.missing_indexing_or_metadata_with_scoring_done}, keywords={recalcSummary.after.missing_keywords_status_with_keywords_data}, culling={recalcSummary.after.culling_failed_with_data_present}
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

      {/* Tier 2 */}
      <TierSection 
        title={MaintenanceToolsCopy.tier2.title} 
        subtitle={MaintenanceToolsCopy.tier2.subtitle}
      >
        <div className="flex flex-col gap-2 p-3 rounded bg-[#1e1e1e] border border-[#3c3c3c]">
          <div className="flex items-start justify-between gap-2">
            <div className="flex-1">
              <h3 className="text-xs font-semibold text-[#cccccc]">
                {MaintenanceToolsCopy.tier2.tools.fullPipeline.name}
              </h3>
              <p className="text-[11px] text-[#9d9d9d] mt-1 leading-relaxed">
                {MaintenanceToolsCopy.tier2.tools.fullPipeline.description}
              </p>
              {!selectedScopePath && (
                <p className="text-[10px] text-[#f44747] mt-1 italic">
                  * Select a folder in the Navigator to enable
                </p>
              )}
            </div>
            <Button
              variant="primary"
              size="sm"
              onClick={() => fullPipelineMut.mutate()}
              disabled={toolsLocked || !selectedScopePath}
              loading={fullPipelineMut.isPending}
              className="h-7 px-3 text-[11px] gap-1 shrink-0"
            >
              <Play size={12} />
              Queue Run
            </Button>
          </div>
        </div>

        <ToolCard
          title={MaintenanceToolsCopy.tier2.tools.healThumbnails.name}
          description={MaintenanceToolsCopy.tier2.tools.healThumbnails.description}
          buttonText="Heal"
          onAction={() => maintenanceMut.mutate({ 
            action: 'heal_thumbnails', 
            label: MaintenanceToolsCopy.tier2.tools.healThumbnails.name,
            limit: MaintenanceToolsCopy.tier2.tools.healThumbnails.limit
          })}
          isPending={maintenanceMut.isPending && maintenanceMut.variables?.action === 'heal_thumbnails'}
          disabled={toolsLocked}
        />

        <ToolCard
          title={MaintenanceToolsCopy.tier2.tools.backfillExif.name}
          description={MaintenanceToolsCopy.tier2.tools.backfillExif.description}
          buttonText="Backfill"
          onAction={() => maintenanceMut.mutate({ 
            action: 'backfill_exif', 
            label: MaintenanceToolsCopy.tier2.tools.backfillExif.name,
            limit: MaintenanceToolsCopy.tier2.tools.backfillExif.limit
          })}
          isPending={maintenanceMut.isPending && maintenanceMut.variables?.action === 'backfill_exif'}
          disabled={toolsLocked}
        />
      </TierSection>

      {/* Tier 3 */}
      <TierSection 
        title={MaintenanceToolsCopy.tier3.title} 
        subtitle={MaintenanceToolsCopy.tier3.subtitle}
      >
        <ToolCard
          title={MaintenanceToolsCopy.tier3.tools.pruneMissing.name}
          description={MaintenanceToolsCopy.tier3.tools.pruneMissing.description}
          buttonText="Prune"
          onAction={() => maintenanceMut.mutate({ 
            action: 'prune_missing', 
            label: MaintenanceToolsCopy.tier3.tools.pruneMissing.name,
            limit: MaintenanceToolsCopy.tier3.tools.pruneMissing.limit
          })}
          isPending={maintenanceMut.isPending && maintenanceMut.variables?.action === 'prune_missing'}
          disabled={toolsLocked}
          variant="secondary"
        />
      </TierSection>
    </div>
  )
}
