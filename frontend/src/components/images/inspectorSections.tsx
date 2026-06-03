import { useState } from 'react'
import { Link } from 'react-router-dom'
import { clsx } from 'clsx'
import { CollapsibleInspectorSection, KeyValueTable, formatInspectorValue } from '@/components/images/InspectorPrimitives'
import {
  EmbeddingsInspectorChips,
  PRIMARY_EMBEDDING_SPACE_CODES,
} from '@/components/images/EmbeddingSpaceChip'
import { describePick, pickStatusOf } from '@/features/culling/utils/pickStatus'
import {
  buildPathsTableEntries,
  inspectorLabel,
  tryParseJson,
} from '@/components/images/imageInspectorPartition'
import type { ImageDetail, TechnicalFailureDetection } from '@/types/api'

export type InspectorSectionAnchors = {
  sectionId?: string
  collapseAllToken?: number
}

function RawJsonExpander({ label, raw }: { label: string; raw: unknown }) {
  const [open, setOpen] = useState(false)
  const text =
    typeof raw === 'string'
      ? raw
      : (() => {
          try {
            return JSON.stringify(raw, null, 2)
          } catch {
            return String(raw)
          }
        })()
  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="text-xs px-2 py-1 rounded border border-[var(--color-border)] text-[var(--color-accent-bright)] hover:bg-[var(--color-bg-elevated)] transition-colors"
      >
        {open ? 'Hide' : 'View'} {label}
      </button>
      {open && (
        <pre className="mt-2 text-[10px] font-mono text-[var(--color-text-secondary)] whitespace-pre-wrap break-all max-h-48 overflow-auto border border-[var(--color-border-muted)] rounded p-2 bg-[var(--color-bg-preview)]">
          {text}
        </pre>
      )}
    </div>
  )
}

function CullDecisionBadge({ value }: { value: unknown }) {
  if (value == null || value === '') return <span>—</span>
  const s = String(value).toLowerCase()
  const color =
    s === 'pick'
      ? 'text-[var(--color-success)] bg-[var(--color-success-muted)] border-[var(--color-success-border)]'
      : s === 'reject'
        ? 'text-[var(--color-danger)] bg-[var(--color-danger-muted)] border-[var(--color-danger-border)]'
        : 'text-[var(--color-text-secondary)] bg-[var(--color-bg-elevated)] border-[var(--color-border)]'
  return (
    <span className={clsx('inline-block px-1.5 py-0.5 rounded text-[10px] font-medium border', color)}>
      {String(value)}
    </span>
  )
}

export function CullingInspectorSection({
  data,
  entries,
  sectionId = 'culling',
  collapseAllToken,
}: {
  data: ImageDetail
  entries: [string, unknown][]
} & InspectorSectionAnchors) {
  const pick = pickStatusOf(data)
  const pickLabel = describePick(pick)
  return (
    <CollapsibleInspectorSection
      title="Culling & picks"
      defaultOpen
      sectionId={sectionId}
      collapseAllToken={collapseAllToken}
    >
      <p className="text-[10px] text-[var(--color-text-muted)] mb-2">
        Pick flag is the gallery/library flag; auto cull decision comes from the clustering pipeline.
      </p>
      <div className="border border-[var(--color-border-muted)] rounded overflow-hidden text-[11px]">
        <table className="w-full border-collapse">
          <tbody>
            <tr className="border-b border-[var(--color-border-muted)] hover:bg-[var(--color-bg-tertiary)]">
              <td className="text-[var(--color-text-secondary)] px-2 py-1 w-[38%] border-r border-[var(--color-border-muted)] font-mono shrink-0">
                {inspectorLabel('pick_status')}
              </td>
              <td className="text-[var(--color-text-primary)] px-2 py-1">
                <span className="font-medium">{pickLabel}</span>
                <span className="ml-2 text-[var(--color-text-muted)] font-mono">({pick})</span>
              </td>
            </tr>
            {entries
              .filter(([k]) => k !== 'pick_status')
              .map(([k, v]) => (
                <tr key={k} className="border-b border-[var(--color-border-muted)] last:border-b-0 hover:bg-[var(--color-bg-tertiary)]">
                  <td className="text-[var(--color-text-secondary)] px-2 py-1 w-[38%] border-r border-[var(--color-border-muted)] font-mono shrink-0">
                    {inspectorLabel(k)}
                  </td>
                  <td className="text-[var(--color-text-primary)] px-2 py-1 font-mono break-all">
                    {k === 'cull_decision' ? <CullDecisionBadge value={v} /> : formatInspectorValue(v)}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </CollapsibleInspectorSection>
  )
}

export function ProvenanceInspectorSection({
  entries,
  sectionId = 'provenance',
  collapseAllToken,
}: { entries: [string, unknown][] } & InspectorSectionAnchors) {
  if (entries.length === 0) return null
  return (
    <CollapsibleInspectorSection
      title="Provenance"
      defaultOpen={false}
      sectionId={sectionId}
      collapseAllToken={collapseAllToken}
    >
      <KeyValueTable
        entries={entries}
        dense
        labelFor={inspectorLabel}
        renderValue={(k, v) => {
          if (k === 'job_id' && typeof v === 'number' && v > 0) {
            return (
              <Link to={`/runs/${v}`} className="text-[var(--color-accent-bright)] hover:underline">
                Run {v}
              </Link>
            )
          }
          return formatInspectorValue(v)
        }}
      />
    </CollapsibleInspectorSection>
  )
}

function indexingTableRows(meta: Record<string, unknown>): [string, unknown][] {
  const rows: [string, unknown][] = []
  if ('indexing_hash_mode' in meta) {
    rows.push(['indexing_hash_mode', meta.indexing_hash_mode])
  }
  const fp = meta.indexing_content_fp
  if (fp && typeof fp === 'object' && !Array.isArray(fp)) {
    const o = fp as Record<string, unknown>
    if (o.size != null) rows.push(['content_fp.size', o.size])
    if (o.mtime_ns != null) rows.push(['content_fp.mtime_ns', o.mtime_ns])
  }
  return rows
}

export function IndexingInspectorSection({
  data,
  sectionId = 'indexing',
  collapseAllToken,
}: { data: ImageDetail } & InspectorSectionAnchors) {
  const parsed =
    data.indexing_metadata ?? tryParseJson(data.metadata)
  const raw = data.metadata
  const rows = parsed ? indexingTableRows(parsed) : []
  if (!parsed && (raw == null || raw === '')) return null

  return (
    <CollapsibleInspectorSection
      title="Indexing"
      defaultOpen={false}
      badge={rows.length > 0 ? `${rows.length}` : undefined}
      sectionId={sectionId}
      collapseAllToken={collapseAllToken}
    >
      {rows.length > 0 ? (
        <KeyValueTable entries={rows} dense labelFor={inspectorLabel} />
      ) : (
        <div className="text-xs text-[var(--color-text-muted)]">Could not parse indexing metadata as JSON.</div>
      )}
      {raw != null && raw !== '' && <RawJsonExpander label="raw metadata JSON" raw={raw} />}
    </CollapsibleInspectorSection>
  )
}

const EMBEDDING_SPACES = PRIMARY_EMBEDDING_SPACE_CODES

export function EmbeddingsInspectorSection({
  embeddings,
  sectionId = 'embeddings',
  collapseAllToken,
}: {
  embeddings?: Record<string, boolean> | null
} & InspectorSectionAnchors) {
  const present = embeddings ?? {}
  const count = EMBEDDING_SPACES.filter((code) => present[code]).length
  return (
    <CollapsibleInspectorSection
      title="Embeddings"
      defaultOpen={false}
      badge={`${count}/${EMBEDDING_SPACES.length}`}
      sectionId={sectionId}
      collapseAllToken={collapseAllToken}
    >
      <EmbeddingsInspectorChips embeddings={embeddings} />
    </CollapsibleInspectorSection>
  )
}

export function TechnicalFailureInspectorSection({
  detection,
  sectionId = 'technical',
  collapseAllToken,
}: {
  detection: TechnicalFailureDetection
} & InspectorSectionAnchors) {
  const metrics = detection.technical_failures ?? {}
  const metricEntries = Object.entries(metrics).filter(([, v]) => v != null && v !== 0)
  return (
    <CollapsibleInspectorSection
      title="Technical quality flags"
      defaultOpen={false}
      sectionId={sectionId}
      collapseAllToken={collapseAllToken}
    >
      <KeyValueTable
        entries={[
          ['technical_failure_score', detection.technical_failure_score],
          ['primary_reject_reason', detection.primary_reject_reason ?? 'none'],
        ]}
        dense
        labelFor={inspectorLabel}
      />
      {metricEntries.length > 0 && (
        <div className="mt-2">
          <div className="text-[10px] text-[var(--color-text-muted)] mb-1">Metrics (non-zero)</div>
          <KeyValueTable entries={metricEntries} dense />
        </div>
      )}
    </CollapsibleInspectorSection>
  )
}

export function PathsInspectorSection({
  data,
  pathEntries,
  sectionId = 'paths',
  collapseAllToken,
}: {
  data: ImageDetail
  pathEntries: [string, unknown][]
} & InspectorSectionAnchors) {
  const rows = buildPathsTableEntries(data, pathEntries)
  if (rows.length === 0) return null

  return (
    <CollapsibleInspectorSection
      title="Paths"
      defaultOpen
      sectionId={sectionId}
      collapseAllToken={collapseAllToken}
    >
      <KeyValueTable
        entries={rows}
        dense
        preserveOrder
        labelFor={(k) => {
          if (k === 'file_paths') {
            const v = rows.find(([key]) => key === 'file_paths')?.[1]
            const n = Array.isArray(v) ? v.length : 0
            return n > 0 ? `File paths (${n})` : inspectorLabel(k)
          }
          return inspectorLabel(k)
        }}
        renderValue={(k, v) => {
          if (k === 'file_paths' && Array.isArray(v)) {
            return (
              <ul className="list-none space-y-1 m-0 p-0">
                {v.map((p, i) => (
                  <li key={i}>{String(p)}</li>
                ))}
              </ul>
            )
          }
          return formatInspectorValue(v)
        }}
      />
    </CollapsibleInspectorSection>
  )
}
