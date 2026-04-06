import { useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Wrench, RefreshCcw, ExternalLink } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { toolsApi, formatToolError, type ApiEnvelope } from '@/api/tools'

const STALE_MIN_AGE = 3600
const BACKFILL_LIMIT = 1000

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

  const regenThumbMut = useMutation({
    mutationFn: () => toolsApi.regenerateThumbnails(),
    onSuccess: (r) => setFromEnvelope('Thumbnails', r),
    onError: (e) => setLastAction({ ok: false, text: formatToolError(e) }),
  })

  const repairThumbMut = useMutation({
    mutationFn: () => toolsApi.repairThumbnailPaths(),
    onSuccess: (r) => setFromEnvelope('Thumbnail paths', r),
    onError: (e) => setLastAction({ ok: false, text: formatToolError(e) }),
  })

  const repairThumbDeepMut = useMutation({
    mutationFn: () => toolsApi.repairThumbnailPaths({ repairAll: true }),
    onSuccess: (r) => setFromEnvelope('Thumbnail paths (deep)', r),
    onError: (e) => setLastAction({ ok: false, text: formatToolError(e) }),
  })

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-2">
          <Wrench className="text-[#4fc1ff]" size={20} />
          <div>
            <p className="text-sm font-medium text-[#cccccc]">Maintenance &amp; quick fixes</p>
            <p className="text-xs text-[#9d9d9d] mt-0.5">
              Local-operator helpers. Heavy work still appears under Active / History as runs where applicable.
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
          'Stale (>1h): per-image phase rows still running after the probe window. ' +
          'Reconcilable (terminal job): rows the Reconcile button can fix — parent job already finished ' +
          '(not filtered by age). Reconcile marks those rows failed (crash/restart drift).'
        }
      >
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => staleQuery.refetch()}
            disabled={staleQuery.isFetching}
            className="gap-1"
          >
            <RefreshCcw size={13} className={staleQuery.isFetching ? 'animate-spin' : ''} />
            Refresh probe
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => reconcileMut.mutate()}
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
          'Queues a DB fix job: re-score images missing model outputs or metadata. ' +
          'Requires the scoring runner to be idle. Monitor via Active and scoring status.'
        }
      >
        <Button variant="primary" size="sm" onClick={() => fixDbMut.mutate()} loading={fixDbMut.isPending}>
          Start fix-db job
        </Button>
      </ToolSection>

      <ToolSection
        title="Backfill Discovery / Inspection phase status"
        description={
          'Global: set indexing and metadata phase to done on up to 1,000 images that already have scoring done ' +
          'but are missing those phase rows (legacy import gap). Repeat to drain the library.'
        }
      >
        <Button variant="primary" size="sm" onClick={() => backfillMut.mutate()} loading={backfillMut.isPending}>
          Backfill (up to {BACKFILL_LIMIT.toLocaleString()})
        </Button>
      </ToolSection>

      <ToolSection
        title="Thumbnails"
        description={
          'Regenerate missing: up to 500 images where the DB thumbnail path does not resolve — may take several minutes on RAW libraries. ' +
          'Repair broken paths: normalize up to 1,000 row updates per click (no pixel regeneration). ' +
          'Quick repair targets Docker /app paths, repo-relative leaks, and one-sided columns (Postgres). ' +
          'Deep normalize rescans the full table for any path pair that would change — use if quick repair reports no updates but paths still look wrong. Repeat as needed.'
        }
      >
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="primary"
            size="sm"
            onClick={() => regenThumbMut.mutate()}
            loading={regenThumbMut.isPending}
          >
            Regenerate missing thumbnails
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => repairThumbMut.mutate()}
            loading={repairThumbMut.isPending}
          >
            Repair broken paths
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => repairThumbDeepMut.mutate()}
            loading={repairThumbDeepMut.isPending}
          >
            Deep normalize paths
          </Button>
        </div>
      </ToolSection>
    </div>
  )
}
