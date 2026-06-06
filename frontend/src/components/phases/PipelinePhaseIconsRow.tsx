import { useMemo } from 'react'
import type { LucideIcon } from 'lucide-react'
import { Bird, FileText, Layers, Scan, Tag, Zap } from 'lucide-react'
import { FULL_PIPELINE_STAGE_CODES } from '@/constants/pipeline'
import { phaseStatusColor } from '@/constants/labelColors'
import type { ImagePhaseStatusRow, RunFolderBucketPhase, StageCode } from '@/types/api'
import { STAGE_DISPLAY } from '@/types/api'

/** Same order as Images table and full pipeline. */
export const PIPELINE_PHASE_ICON_ORDER = FULL_PIPELINE_STAGE_CODES

export const PHASES_HEADER_HINT =
  'Indexing · Metadata · Scoring · Culling · Keywords · Bird species (hover icons for status)'

export const STAGE_TYPE_ICONS: Record<StageCode, LucideIcon> = {
  indexing: Scan,
  metadata: FileText,
  scoring: Zap,
  culling: Layers,
  keywords: Tag,
  bird_species: Bird,
  maintenance: FileText,
}

function stageLabel(code: StageCode): string {
  return STAGE_DISPLAY[code]?.name ?? code.replace(/_/g, ' ')
}

function phaseBarFillClass(phase: RunFolderBucketPhase): string {
  if (phase.status === 'failed') return 'bg-[var(--color-danger)]'
  if (phase.status === 'running' || phase.status === 'queued') return 'bg-[var(--color-accent-bright)]'
  if (Math.round(phase.percent) >= 100 || phase.status === 'done' || phase.status === 'skipped') {
    return 'bg-[var(--color-success)]'
  }
  return 'bg-[var(--color-text-muted)]'
}

function PipelinePhaseIcon({
  code,
  status,
  error,
  percent,
  icon: Icon,
  titleOverride,
  className,
}: {
  code: StageCode
  status?: string
  error?: string | null
  percent?: number
  icon: LucideIcon
  titleOverride?: string
  className?: string
}) {
  const color = useMemo(() => phaseStatusColor(status), [status])

  const title = useMemo(() => {
    if (titleOverride) return titleOverride
    const label = stageLabel(code)
    const statusText = status || 'not_started'
    if (percent != null) {
      let t = `${label}: ${Math.round(percent)}% (${statusText})`
      if (error) t += `\nError: ${error}`
      return t
    }
    let t = `${code.charAt(0).toUpperCase() + code.slice(1)}: ${statusText}`
    if (error) t += `\nError: ${error}`
    return t
  }, [code, status, error, percent, titleOverride])

  return (
    <div
      className={`rounded-sm p-1 transition-colors hover:bg-[var(--color-bg-elevated)] ${className ?? ''}`}
      title={title}
      style={{ color }}
    >
      <Icon size={14} strokeWidth={2.5} />
    </div>
  )
}

function BucketPhaseCell({
  code,
  phase,
  showProgressBar,
}: {
  code: StageCode
  phase?: RunFolderBucketPhase
  showProgressBar: boolean
}) {
  const Icon = STAGE_TYPE_ICONS[code]
  const pct = phase ? Math.round(phase.percent) : 0
  const running = phase?.status === 'running' || phase?.status === 'queued'

  return (
    <div className="min-w-0">
      <div className="flex justify-center">
        <PipelinePhaseIcon
          code={code}
          icon={Icon}
          status={phase?.status}
          percent={phase?.percent}
        />
      </div>
      {showProgressBar && (
        <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-[var(--color-bg-elevated)]">
          <div
            className={`h-full rounded-full transition-[width] duration-300 ${
              phase ? phaseBarFillClass(phase) : 'bg-[var(--color-text-muted)]'
            } ${running ? 'animate-pulse' : ''}`}
            style={{
              width: `${pct <= 0 ? 0 : Math.max(6, Math.min(100, pct))}%`,
            }}
          />
        </div>
      )}
    </div>
  )
}

export interface PipelinePhaseIconsRowProps {
  phases?: Record<string, ImagePhaseStatusRow | string> | null
  bucketPhases?: RunFolderBucketPhase[]
  /** Bucket mode only: icon + thin progress bar per phase. */
  showProgressBars?: boolean
}

export function PipelinePhaseIconsRow({
  phases,
  bucketPhases,
  showProgressBars = false,
}: PipelinePhaseIconsRowProps) {
  if (bucketPhases !== undefined) {
    if (bucketPhases.length === 0) {
      return <span className="text-[var(--color-text-muted)]">—</span>
    }
    const byCode = new Map(bucketPhases.map((p) => [p.code, p]))

    if (showProgressBars) {
      return (
        <div className="grid auto-cols-fr grid-flow-col gap-1.5">
          {PIPELINE_PHASE_ICON_ORDER.map((code) => (
            <BucketPhaseCell
              key={code}
              code={code}
              phase={byCode.get(code)}
              showProgressBar
            />
          ))}
        </div>
      )
    }

    return (
      <div className="flex items-center gap-0.5">
        {PIPELINE_PHASE_ICON_ORDER.map((code) => {
          const phase = byCode.get(code)
          const Icon = STAGE_TYPE_ICONS[code]
          return (
            <PipelinePhaseIcon
              key={code}
              code={code}
              icon={Icon}
              status={phase?.status}
              percent={phase?.percent}
            />
          )
        })}
      </div>
    )
  }

  if (!phases) {
    return <span className="text-[var(--color-text-muted)]">—</span>
  }

  const getStatus = (code: string) => {
    const p = phases[code]
    if (typeof p === 'string') return { status: p }
    return p as ImagePhaseStatusRow | undefined
  }

  return (
    <div className="flex items-center gap-0.5">
      {PIPELINE_PHASE_ICON_ORDER.map((code) => {
        const row = getStatus(code)
        const Icon = STAGE_TYPE_ICONS[code]
        return (
          <PipelinePhaseIcon
            key={code}
            code={code}
            icon={Icon}
            status={row?.status}
            error={row?.last_error}
          />
        )
      })}
    </div>
  )
}

export interface NextChainPhaseIconsProps {
  codes: StageCode[]
  tooltipPrefix?: string
}

/** Subset of pipeline stage icons for the Dashboard next-chain column. */
export function NextChainPhaseIcons({ codes, tooltipPrefix = 'Would queue' }: NextChainPhaseIconsProps) {
  if (codes.length === 0) return null

  const codeSet = new Set(codes)
  const ordered = PIPELINE_PHASE_ICON_ORDER.filter((code) => codeSet.has(code))

  return (
    <div className="flex items-center gap-0.5">
      {ordered.map((code) => {
        const Icon = STAGE_TYPE_ICONS[code]
        return (
          <PipelinePhaseIcon
            key={code}
            code={code}
            icon={Icon}
            status="queued"
            titleOverride={`${tooltipPrefix}: ${stageLabel(code)}`}
          />
        )
      })}
    </div>
  )
}
