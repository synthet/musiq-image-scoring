import { useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Wrench, RefreshCcw, ExternalLink, Play, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  HEAL_STEPS,
  PIPELINE_TOOLS_HEADER,
  SECTION,
} from '@/constants/pipelineTools'
import { usePipelineToolAction } from '@/hooks/usePipelineToolAction'
import { useUiStore } from '@/stores/uiStore'

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

  const [healBudget, setHealBudget] = useState(10)
  const [healDryRun, setHealDryRun] = useState(false)
  const [healRunMode, setHealRunMode] = useState('process_unprocessed_or_empty')

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

      <TierSection title={SECTION.workflow_heal.title} subtitle={SECTION.workflow_heal.subtitle}>
        <div className={`${PANEL} flex flex-wrap items-end gap-4`}>
          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-[#6d6d6d] uppercase font-bold">Max Folders (Budget)</label>
            <input
              type="number"
              min={1}
              max={100}
              value={healBudget}
              onChange={(e) => setHealBudget(Number(e.target.value))}
              className="h-7 w-20 bg-[#252526] border border-[#3c3c3c] text-[#cccccc] px-2 text-xs rounded"
              disabled={toolsLocked}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-[#6d6d6d] uppercase font-bold">Execution Mode</label>
            <select
              value={healRunMode}
              onChange={(e) => setHealRunMode(e.target.value)}
              className="h-7 bg-[#252526] border border-[#3c3c3c] text-[#cccccc] px-2 text-xs rounded"
              disabled={toolsLocked}
            >
              <option value="validate_and_repair">Validate & Repair</option>
              <option value="process_unprocessed_or_empty">Process Unprocessed</option>
              <option value="process_all_overwrite">Overwrite All</option>
            </select>
          </div>
          <label className="flex items-center gap-2 text-xs text-[#9d9d9d] h-7 cursor-pointer">
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
                  runMode: healRunMode,
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
          <div className="mt-1 rounded border border-[#3c5c3c]/40 bg-[#1a2520]/40 px-3 py-2 text-[10px] text-[#8d8d8d] font-mono space-y-1">
            <div className="flex justify-between border-b border-[#3c5c3c]/20 pb-1 mb-1">
              <span className="text-[#89d185] font-bold uppercase">Heal Results: {healStats.phase_code}</span>
              <span>{healStats.dry_run ? '[DRY RUN]' : '[LIVE]'}</span>
            </div>
            <div className="grid grid-cols-2 gap-x-4">
              <div>Identified False Dones: <span className="text-[#cccccc]">{healStats.false_positives_found}</span></div>
              <div>Resets Performed: <span className="text-[#f2cc60] font-bold">{healStats.resets_performed}</span></div>
              <div>Eligible Folders: <span className="text-[#cccccc]">{healStats.eligible_folders}</span></div>
              <div>Folders Needing Work: <span className="text-[#cccccc]">{healStats.folders_needing_work}</span></div>
              <div>Scheduled Runs: <span className="text-[#4fc1ff] font-bold">{healStats.scheduled.length}</span></div>
              <div>Used Budget: <span className="text-[#cccccc]">{healBudget}</span></div>
            </div>
            {healStats.scheduled.length > 0 && (
              <div className="mt-2 text-[9px] text-[#6d6d6d]">
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
    </div>
  )
}
