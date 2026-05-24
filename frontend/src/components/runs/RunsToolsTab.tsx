import { useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Wrench, RefreshCw, ExternalLink, Play, AlertTriangle, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  BACKFILL_STEPS,
  CLEANUP_STEPS,
  HEAL_STEPS,
  PIPELINE_TOOLS_HEADER,
  SECTION,
} from '@/constants/pipelineTools'
import { usePipelineToolAction } from '@/hooks/usePipelineToolAction'
import { useUiStore } from '@/stores/uiStore'

const PANEL = 'p-3 rounded bg-[var(--color-bg-primary)] border border-[var(--color-border-muted)]'

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
          <h3 className="text-xs font-semibold text-[var(--color-text-primary)]">{title}</h3>
          <p className="text-[11px] text-[var(--color-text-secondary)] mt-1 leading-relaxed">{description}</p>
        </div>
        <Button
          variant={variant}
          size="sm"
          onClick={onAction}
          disabled={disabled || isPending}
          loading={isPending}
          className="h-7 px-3 text-[11px] gap-1 shrink-0"
        >
          <Icon size={14} />
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
    <section className="rounded-lg border border-[var(--color-border-muted)] bg-[var(--color-bg-secondary)] p-4">
      <div className="mb-4">
        <h2 className="text-sm font-semibold text-[var(--color-text-primary)]">{title}</h2>
        <p className="text-xs text-[var(--color-text-secondary)] mt-0.5">{subtitle}</p>
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
          ? 'bg-[var(--color-success-bg)] text-[var(--color-success)] border-[var(--color-success-border)]'
          : 'bg-[var(--color-danger-bg)] text-[var(--color-danger)] border-[var(--color-danger-border)]'
      }`}
    >
      <div className="mt-0.5">{ok ? <RefreshCw size={14} /> : <AlertTriangle size={14} />}</div>
      <p className="leading-relaxed">{text}</p>
    </div>
  )
}

export function RunsToolsTab() {
  const selectedScopePath = useUiStore((s) => s.selectedScopePath)
  const setPendingTreeRevealPaths = useUiStore((s) => s.setPendingTreeRevealPaths)

  const [healBudget, setHealBudget] = useState(10)
  const [healDryRun, setHealDryRun] = useState(false)
  const [cleanupDryRun, setCleanupDryRun] = useState(true)

  const {
    run,
    isPending,
    pendingId,
    lastBanner,
    healStats,
  } = usePipelineToolAction({
    onHealSpawned: (folderPath: string) => setPendingTreeRevealPaths([folderPath]),
  })

  const toolsLocked = isPending

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-2">
          <Wrench className="text-[var(--color-accent-bright)]" size={20} />
          <div>
            <p className="text-sm font-medium text-[var(--color-text-primary)]">{PIPELINE_TOOLS_HEADER.title}</p>
            <p className="text-xs text-[var(--color-text-secondary)] mt-0.5">{PIPELINE_TOOLS_HEADER.subtitle}</p>
          </div>
        </div>
        <Link
          to="/diagnostics"
          className="inline-flex items-center gap-1 text-xs text-[var(--color-accent-bright)] hover:underline shrink-0"
        >
          Health
          <ExternalLink size={14} />
        </Link>
      </div>

      {lastBanner && <ResultBanner ok={lastBanner.ok} text={lastBanner.text} />}

      <TierSection title={SECTION.workflow_heal.title} subtitle={SECTION.workflow_heal.subtitle}>
        <div className={`${PANEL} flex flex-wrap items-end gap-4`}>
          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-[var(--color-text-muted)] uppercase font-bold">Max Folders (Budget)</label>
            <input
              type="number"
              min={1}
              max={100}
              value={healBudget}
              onChange={(e) => setHealBudget(Number(e.target.value))}
              className="h-7 w-20 bg-[var(--color-bg-secondary)] border border-[var(--color-border-muted)] text-[var(--color-text-primary)] px-2 text-xs rounded"
              disabled={toolsLocked}
            />
          </div>
          <label className="flex items-center gap-2 text-xs text-[var(--color-text-secondary)] h-7 cursor-pointer">
            <input
              type="checkbox"
              checked={healDryRun}
              onChange={(e) => setHealDryRun(e.target.checked)}
              disabled={toolsLocked}
            />
            Dry Run
          </label>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {HEAL_STEPS.map((step) => (
            <ToolCard
              key={step.code}
              title={step.name}
              description={step.description}
              buttonText="Heal"
              onAction={() =>
                run({
                  kind: 'heal',
                  trackingId: `heal-${step.code}`,
                  phaseCode: step.code,
                  budget: healBudget,
                  dryRun: healDryRun,
                  rootPath: selectedScopePath?.trim() || undefined,
                })
              }
              isPending={isPending && pendingId === `heal-${step.code}`}
              disabled={toolsLocked}
              variant="primary"
            />
          ))}
        </div>

        {healStats && (
          <div className="mt-1 rounded border border-[var(--color-success-border)]/40 bg-[var(--color-success-bg)]/40 px-3 py-2 text-[10px] text-[var(--color-text-secondary)] font-mono space-y-1">
            <div className="flex justify-between border-b border-[var(--color-success-border)]/20 pb-1 mb-1">
              <span className="text-[var(--color-success)] font-bold uppercase">Heal Results: {healStats.phase_code}</span>
              <span>{healStats.dry_run ? '[DRY RUN]' : '[LIVE]'}</span>
            </div>
            <div className="grid grid-cols-2 gap-x-4">
              <div>Identified False Dones: <span className="text-[var(--color-text-primary)]">{healStats.false_positives_found}</span></div>
              <div>Resets Performed: <span className="text-[var(--color-warning)] font-bold">{healStats.resets_performed}</span></div>
              <div>Eligible Folders: <span className="text-[var(--color-text-primary)]">{healStats.eligible_folders}</span></div>
              <div>Folders Needing Work: <span className="text-[var(--color-text-primary)]">{healStats.folders_needing_work}</span></div>
              <div>Scheduled Runs: <span className="text-[var(--color-accent-bright)] font-bold">{healStats.scheduled.length}</span></div>
              {(healStats.cohesion_suppressed ?? 0) > 0 && (
                <div>
                  Cohesion skipped (prior heals):{' '}
                  <span className="text-[var(--color-warning)] font-bold">{healStats.cohesion_suppressed}</span>
                </div>
              )}
              <div>Used Budget: <span className="text-[var(--color-text-primary)]">{healBudget}</span></div>
            </div>
            {healStats.scheduled.length > 0 && (
              <div className="mt-2 text-[9px] text-[var(--color-text-muted)]">
                <div className="uppercase font-bold mb-1 italic">Folders Processed:</div>
                <ul className="list-disc pl-3">
                  {healStats.scheduled.map((s, idx) => (
                    <li key={idx} className="truncate">
                      {s.folder_path} {s.job_id ? `(Job #${s.job_id})` : ''}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </TierSection>

      <TierSection title={SECTION.data_backfill.title} subtitle={SECTION.data_backfill.subtitle}>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {BACKFILL_STEPS.map((step) => (
            <ToolCard
              key={step.code}
              title={step.name}
              description={step.description}
              buttonText="Start"
              onAction={() =>
                run({
                  kind: 'backfill',
                  trackingId: `backfill-${step.code}`,
                  actionName: step.code,
                })
              }
              isPending={isPending && pendingId === `backfill-${step.code}`}
              disabled={toolsLocked}
              variant="secondary"
            />
          ))}
        </div>
      </TierSection>

      <TierSection title={SECTION.cleanup_stale.title} subtitle={SECTION.cleanup_stale.subtitle}>
        <div className={`${PANEL} flex flex-wrap items-end gap-4`}>
          <label className="flex items-center gap-2 text-xs text-[var(--color-text-secondary)] h-7 cursor-pointer">
            <input
              type="checkbox"
              checked={cleanupDryRun}
              onChange={(e) => setCleanupDryRun(e.target.checked)}
              disabled={toolsLocked}
            />
            Dry Run (recommended for destructive actions)
          </label>
          {selectedScopePath?.trim() && (
            <span className="text-[10px] text-[var(--color-text-muted)] font-mono truncate max-w-[60ch]">
              Scope: {selectedScopePath}
            </span>
          )}
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {CLEANUP_STEPS.map((step) => (
            <ToolCard
              key={step.code}
              title={step.name}
              description={step.description}
              buttonText={step.destructive && !cleanupDryRun ? 'Run (destructive)' : 'Run'}
              onAction={() =>
                run({
                  kind: 'cleanup',
                  trackingId: `cleanup-${step.code}`,
                  actionName: step.code,
                  dryRun: cleanupDryRun,
                  rootPath: selectedScopePath?.trim() || undefined,
                })
              }
              isPending={isPending && pendingId === `cleanup-${step.code}`}
              disabled={toolsLocked}
              icon={step.destructive ? Trash2 : RefreshCw}
              variant={step.destructive ? 'outline' : 'secondary'}
            />
          ))}
        </div>
      </TierSection>
    </div>
  )
}
