import { useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Wrench, RefreshCcw, ExternalLink } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { toolsApi, formatToolError, type ApiEnvelope } from '@/api/tools'
import { runsApi } from '@/api/runs'
import { FULL_PIPELINE_STAGE_CODES } from '@/constants/pipeline'
import { STAGE_DISPLAY } from '@/types/api'
import { useUiStore } from '@/stores/uiStore'

const STALE_MIN_AGE = 3600
const BACKFILL_LIMIT = 1000

const FULL_PIPELINE_LABELS = FULL_PIPELINE_STAGE_CODES.map((c) => STAGE_DISPLAY[c].name).join(' → ')

function ToolSection({
  title,
  description,
  children,
}: {
  title: string
  description: string
  children: ReactNode
}) {
  return (
    <section className="rounded-lg border border-[#3c3c3c] bg-[#252526] p-4">
      <h2 className="text-sm font-semibold text-[#cccccc] mb-1">{title}</h2>
      <p className="text-xs text-[#9d9d9d] mb-3 leading-relaxed">{description}</p>
      {children}
    </section>
  )
}

function ResultBanner({ text, ok }: { text: string; ok: boolean }) {
  return (
    <p
      className={`text-xs mt-2 rounded px-2 py-1.5 ${
        ok ? 'bg-[#1e3a1e] text-[#89d185]' : 'bg-[#3a1e1e] text-[#f44747]'
      }`}
    >
      {text}
    </p>
  )
}

export function RunsToolsTab() {
  const queryClient = useQueryClient()
  const selectedScopePath = useUiStore((s) => s.selectedScopePath)
  const setPendingTreeRevealPaths = useUiStore((s) => s.setPendingTreeRevealPaths)
  const [lastAction, setLastAction] = useState<{ ok: boolean; text: string } | null>(null)

  const staleQuery = useQuery({
    queryKey: ['maintenance-stale-phases', STALE_MIN_AGE],
    queryFn: () => toolsApi.staleRunningPhases(STALE_MIN_AGE, 50),
    refetchInterval: 60_000,
  })

  const setFromEnvelope = (label: string, r: ApiEnvelope) => {
    const ok = r.success
    const extra =
      r.data && typeof r.data === 'object'
        ? ` ${JSON.stringify(r.data)}`
        : ''
    setLastAction({ ok, text: `${label}: ${r.message}${extra}` })
  }

  const reconcileMut = useMutation({
    mutationFn: () => toolsApi.reconcileTerminalJobPhases(5000),
    onSuccess: (r) => {
      setFromEnvelope('Reconcile', r)
      void queryClient.invalidateQueries({ queryKey: ['maintenance-stale-phases'] })
    },
    onError: (e) => setLastAction({ ok: false, text: formatToolError(e) }),
  })

  const fixDbMut = useMutation({
    mutationFn: () => toolsApi.fixDatabase(),
    onSuccess: (r) => setFromEnvelope('Fix DB', r),
    onError: (e) => setLastAction({ ok: false, text: formatToolError(e) }),
  })

  const backfillMut = useMutation({
    mutationFn: () => toolsApi.backfillIndexMeta(BACKFILL_LIMIT),
    onSuccess: (r) => setFromEnvelope('Backfill', r),
    onError: (e) => setLastAction({ ok: false, text: formatToolError(e) }),
  })

  const healThumbMut = useMutation({
    mutationFn: () => toolsApi.healThumbnails(),
    onSuccess: (r) => setFromEnvelope('Thumbnails', r),
    onError: (e) => setLastAction({ ok: false, text: formatToolError(e) }),
  })

  const repairThumbDeepMut = useMutation({
    mutationFn: () => toolsApi.repairThumbnailPaths({ repairAll: true }),
    onSuccess: (r) => setFromEnvelope('Thumbnail paths (deep)', r),
    onError: (e) => setLastAction({ ok: false, text: formatToolError(e) }),
  })

  const fullPipelineMut = useMutation({
    mutationFn: () => {
      if (!selectedScopePath?.trim()) {
        return Promise.reject(new Error('No folder selected'))
      }
      return runsApi.submit({
        scope_type: 'folder_recursive',
        scope_paths: [selectedScopePath.trim()],
        stages: [...FULL_PIPELINE_STAGE_CODES],
        skip_done: true,
        force_rerun: false,
        fix_incomplete_stages: false,
      })
    },
    onSuccess: (data) => {
      setLastAction({
        ok: true,
        text: `Full pipeline: run ${data.run_id} queued (queue position ${data.queue_position}).`,
      })
      void queryClient.invalidateQueries({ queryKey: ['runs'] })
      void queryClient.invalidateQueries({ queryKey: ['folders-tree'] })
      if (selectedScopePath?.trim()) {
        setPendingTreeRevealPaths([selectedScopePath.trim()])
      }
    },
    onError: (e) => setLastAction({ ok: false, text: formatToolError(e) }),
  })

  const mutationPending =
    reconcileMut.isPending ||
    fixDbMut.isPending ||
    backfillMut.isPending ||
    healThumbMut.isPending ||
    repairThumbDeepMut.isPending ||
    fullPipelineMut.isPending
  /** Block concurrent tool actions (mutations or stale probe refetch). */
  const toolsLocked = mutationPending || staleQuery.isFetching

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-2">
          <Wrench className="text-[#4fc1ff]" size={20} />
          <div>
            <p className="text-sm font-medium text-[#cccccc]">Maintenance &amp; quick fixes</p>
            <p className="text-xs text-[#9d9d9d] mt-0.5">
              Local-operator helpers. Queued work appears under Active / History as runs.
            </p>
          </div>
        </div>
        <Link
          to="/diagnostics"
          className="inline-flex items-center gap-1 text-xs text-[#4fc1ff] hover:underline shrink-0"
        >
          System diagnostics
          <ExternalLink size={12} />
        </Link>
      </div>

      {lastAction && <ResultBanner ok={lastAction.ok} text={lastAction.text} />}

      <ToolSection
        title="Stuck phase rows"
        description={
          'Stale (>1h): per-image phase rows still in running state past the probe window. ' +
          'Reconcilable (terminal job): parent job finished but a per-image row stayed running — Reconcile marks those rows failed (crash/restart drift). Not age-filtered.'
        }
      >
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => staleQuery.refetch()}
            disabled={toolsLocked}
            className="gap-1"
          >
            <RefreshCcw size={13} className={staleQuery.isFetching ? 'animate-spin' : ''} />
            Refresh probe
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => reconcileMut.mutate()}
            disabled={toolsLocked}
            loading={reconcileMut.isPending}
          >
            Reconcile terminal-job phases
          </Button>
        </div>
        {staleQuery.isError && (
          <p className="text-xs text-[#f44747] mt-2">{formatToolError(staleQuery.error)}</p>
        )}
        {staleQuery.data && (
          <p className="text-xs text-[#9d9d9d] mt-2">
            Stale (&gt;{staleQuery.data.min_age_seconds}s):{' '}
            <span className="text-[#cccccc] font-medium">{staleQuery.data.count_estimate}</span> row(s).{' '}
            Reconcilable (terminal job):{' '}
            <span className="text-[#cccccc] font-medium">
              {staleQuery.data.reconcilable_count ?? '—'}
            </span>
            .
            {staleQuery.data.sample.length > 0 && (
              <span className="block mt-1 font-mono text-[#6d6d6d] break-all">
                Sample:{' '}
                {staleQuery.data.sample
                  .slice(0, 3)
                  .map((s) => `${s.phase_code} job=${s.job_id} ${s.file_path || ''}`)
                  .join(' · ')}
              </span>
            )}
          </p>
        )}
      </ToolSection>

      <ToolSection
        title="Fix incomplete scores (database)"
        description={
          'Queues a fix-db job to re-score rows missing model outputs or metadata. ' +
          'Requires the scoring runner to be idle. Watch Active / History and scoring status.'
        }
      >
        <Button
          variant="primary"
          size="sm"
          onClick={() => fixDbMut.mutate()}
          disabled={toolsLocked}
          loading={fixDbMut.isPending}
        >
          Start fix-db job
        </Button>
      </ToolSection>

      <ToolSection
        title="Backfill Discovery / Inspection phase status"
        description={
          'Global batch: for up to 1,000 images with scoring done but missing indexing or metadata phase rows, ' +
          'set Discovery (indexing) and Inspection (metadata) to done — repairs legacy import gaps. Repeat to drain.'
        }
      >
        <Button
          variant="primary"
          size="sm"
          onClick={() => backfillMut.mutate()}
          disabled={toolsLocked}
          loading={backfillMut.isPending}
        >
          Backfill (up to {BACKFILL_LIMIT.toLocaleString()})
        </Button>
      </ToolSection>

      <ToolSection
        title="Full pipeline (selected folder)"
        description={
          `Queues one run for the folder selected in Scope Navigator: ${FULL_PIPELINE_LABELS}. ` +
          'Skips phase work already completed (same as New Run → Skip completed). ' +
          'Select a folder on the left, then queue here after imports from Gallery or other registration.'
        }
      >
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="primary"
            size="sm"
            onClick={() => fullPipelineMut.mutate()}
            disabled={toolsLocked || !selectedScopePath?.trim()}
            loading={fullPipelineMut.isPending}
          >
            Queue full pipeline
          </Button>
        </div>
        {!selectedScopePath?.trim() && (
          <p className="text-xs text-[#6d6d6d] mt-2">Select a folder in Scope Navigator to enable this action.</p>
        )}
      </ToolSection>

      <ToolSection
        title="Thumbnails"
        description={
          'Step 1: quick path repair (normalize up to 1,000 thumbnail_path / thumbnail_path_win rows — no pixel decode). ' +
          'Step 2: regenerate up to 500 missing thumbnail rasters (RAW libraries may take several minutes). ' +
          'Deep normalize (full-table path scan) is separate — use only if paths still look wrong after heal.'
        }
      >
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="primary"
            size="sm"
            onClick={() => healThumbMut.mutate()}
            disabled={toolsLocked}
            loading={healThumbMut.isPending}
          >
            Heal thumbnails (repair + regen)
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => repairThumbDeepMut.mutate()}
            disabled={toolsLocked}
            loading={repairThumbDeepMut.isPending}
          >
            Deep normalize paths
          </Button>
        </div>
      </ToolSection>
    </div>
  )
}
