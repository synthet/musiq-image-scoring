import { useState, useEffect, useMemo } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { clsx } from 'clsx'
import { X, Plus, Trash2, FolderOpen } from 'lucide-react'
import { ApiError, parseApiErrorDetail } from '@/api/client'
import { runsApi, type RunSubmitRequest } from '@/api/runs'
import { scopeApi } from '@/api/scope'
import { Button } from '@/components/ui/button'
import { PhaseStatusIcon } from '@/components/status/PhaseStatusIcon'
import { useUiStore } from '@/stores/uiStore'
import { STAGE_DISPLAY } from '@/types/api'
import type { StageCode, ScopePreviewResult, ValidationRepairPreview } from '@/types/api'
import { FULL_PIPELINE_STAGE_CODES, pruneStageSelection, stagePrerequisitesMet, STAGE_PREREQUISITES } from '@/constants/pipeline'
import { RUNS_QUERY_ROOT } from '@/queryKeys/runs'

const ALL_STAGES: StageCode[] = [...FULL_PIPELINE_STAGE_CODES]

/** Trim and strip trailing `/` or `\\`; keep Windows drive roots (e.g. `D:\\`). */
function normalizeScopePathInput(p: string): string {
  let s = p.trim()
  while (s.length > 1 && (s.endsWith('/') || s.endsWith('\\'))) {
    const prev = s.slice(0, -1)
    if (prev.length === 2 && prev[1] === ':') break
    s = prev
  }
  return s
}

export function ScopeSelector() {
  const { newRunModalOpen, setNewRunModalOpen, newRunInitialPath, setPendingTreeRevealPaths } =
    useUiStore()
  const qc = useQueryClient()

  const [scopeType, setScopeType] = useState<'folder_recursive' | 'folder' | 'file'>('folder_recursive')
  const [paths, setPaths] = useState<string[]>([''])
  const [stages, setStages] = useState<Set<StageCode>>(new Set(ALL_STAGES))
  const [preview, setPreview] = useState<ScopePreviewResult | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [repairPreview, setRepairPreview] = useState<ValidationRepairPreview | null>(null)
  const [repairPreviewLoading, setRepairPreviewLoading] = useState(false)

  const satisfiedStages = useMemo(() => {
    const st = preview?.stage_statuses
    if (!st) return new Set<StageCode>()
    const next = new Set<StageCode>()
    for (const code of ALL_STAGES) {
      if (st[code] === 'done') next.add(code)
    }
    return next
  }, [preview])

  const previewGateActive = preview !== null

  useEffect(() => {
    if (!preview?.stage_statuses) return
    const sat = new Set<StageCode>()
    for (const code of ALL_STAGES) {
      if (preview.stage_statuses[code] === 'done') sat.add(code)
    }
    setStages((prev) => pruneStageSelection(prev, sat))
  }, [preview])

  useEffect(() => {
    if (!newRunModalOpen) return
    if (newRunInitialPath) {
      setPaths([newRunInitialPath])
    } else {
      setPaths([''])
    }
    setPreview(null)
    setPreviewError(null)
    setRepairPreview(null)
  }, [newRunModalOpen, newRunInitialPath])

  useEffect(() => {
    if (!newRunModalOpen) return
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') setNewRunModalOpen(false)
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [newRunModalOpen, setNewRunModalOpen])

  const validPaths = paths
    .map((p) => p.trim())
    .filter((p) => p.length > 0)
    .map(normalizeScopePathInput)

  async function loadPreview() {
    if (validPaths.length === 0) return
    setPreviewLoading(true)
    setPreviewError(null)
    try {
      const res = await scopeApi.preview(validPaths, scopeType === 'folder_recursive')
      setPreview(res)
      qc.invalidateQueries({ queryKey: ['folders-tree'] })
      setRepairPreviewLoading(true)
      const stagesOrdered = ALL_STAGES.filter((code) => stages.has(code))
      const rep = await scopeApi.validationRepairPreview(validPaths, stagesOrdered, {
        alignAutoDrive: true,
      })
      setRepairPreview(rep)
    } catch (e) {
      setPreview(null)
      setRepairPreview(null)
      const msg = e instanceof ApiError ? parseApiErrorDetail(e.message) : String(e)
      setPreviewError(msg)
    } finally {
      setPreviewLoading(false)
      setRepairPreviewLoading(false)
    }
  }

  const submitMut = useMutation({
    mutationFn: (req: RunSubmitRequest) => runsApi.submit(req),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: RUNS_QUERY_ROOT })
      qc.invalidateQueries({ queryKey: ['folders-tree'] })
      const paths = variables.scope_paths ?? []
      setPendingTreeRevealPaths(paths.length > 0 ? [...paths] : null)
      setNewRunModalOpen(false)
      setPaths([''])
      setPreview(null)
    },
  })

  function submit() {
    const stagesOrdered = ALL_STAGES.filter((code) => stages.has(code))
    submitMut.mutate({
      scope_type: scopeType,
      scope_paths: validPaths,
      stages: stagesOrdered,
      run_mode: 'process_stale_or_missing',
    })
  }

  function toggleStage(code: StageCode) {
    setStages((prev) => {
      const next = new Set(prev)
      if (next.has(code)) next.delete(code)
      else next.add(code)
      return pruneStageSelection(next, satisfiedStages)
    })
  }

  if (!newRunModalOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-lg shadow-2xl w-[600px] max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-5 border-b border-[var(--color-border-muted)]">
          <h2 className="text-base font-semibold text-[var(--color-text-primary)]">New Run</h2>
          <button
            onClick={() => setNewRunModalOpen(false)}
            className="text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        <div className="p-5 space-y-5">
          <div>
            <label className="block text-xs font-semibold text-[var(--color-text-secondary)] mb-2 uppercase tracking-wider">
              Scope Type
            </label>
            <div className="flex gap-2">
              {(
                [
                  { value: 'folder_recursive', label: 'Folder (recursive)' },
                  { value: 'folder', label: 'Folder (flat)' },
                  { value: 'file', label: 'Single file' },
                ] as const
              ).map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setScopeType(opt.value)}
                  className={clsx(
                    'px-3 py-1.5 rounded text-xs font-medium border transition-colors',
                    scopeType === opt.value
                      ? 'bg-[var(--color-accent-dim)] border-[var(--color-accent)] text-[var(--color-accent-bright)]'
                      : 'bg-[var(--color-bg-elevated)] border-[var(--color-border)] text-[var(--color-text-secondary)] hover:border-[var(--color-accent-bright)]',
                  )}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-[var(--color-text-secondary)] mb-2 uppercase tracking-wider">
              Path{scopeType === 'folder_recursive' ? 's' : ''}
            </label>
            <div className="space-y-2">
              {paths.map((path, i) => (
                <div key={i} className="flex items-center gap-2">
                  <div className="flex-1 flex items-center gap-2 bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded px-3 py-2 focus-within:border-[var(--color-accent-bright)]">
                    <FolderOpen size={14} className="text-[var(--color-text-muted)] shrink-0" />
                    <input
                      value={path}
                      onChange={(e) => {
                        const next = [...paths]
                        next[i] = e.target.value
                        setPaths(next)
                        setPreview(null)
                        setPreviewError(null)
                      }}
                      placeholder="/path/to/folder"
                      className="flex-1 bg-transparent text-sm text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-muted)]"
                    />
                  </div>
                  {paths.length > 1 && (
                    <button
                      onClick={() => setPaths(paths.filter((_, j) => j !== i))}
                      className="text-[var(--color-text-muted)] hover:text-[var(--color-danger)] transition-colors"
                    >
                      <Trash2 size={14} />
                    </button>
                  )}
                </div>
              ))}
              <Button size="xs" variant="ghost" onClick={() => setPaths([...paths, ''])}>
                <Plus size={14} />
                Add path
              </Button>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs font-semibold text-[var(--color-text-secondary)] uppercase tracking-wider">
                Preview
              </label>
              <Button size="xs" variant="secondary" onClick={loadPreview} loading={previewLoading}>
                {previewLoading ? '' : 'Refresh'}
              </Button>
            </div>
            {previewError && (
              <div className="bg-[var(--color-bg-primary)] border border-[var(--color-danger)]/50 rounded p-3 text-xs text-[var(--color-danger)] whitespace-pre-wrap break-words">
                {previewError}
              </div>
            )}
            {preview ? (
              <PreviewPanel preview={preview} />
            ) : (
              !previewError && (
                <div className="bg-[var(--color-bg-primary)] border border-[var(--color-border-muted)] rounded p-3 text-xs text-[var(--color-text-muted)]">
                  {validPaths.length > 0 ? 'Click Refresh to preview scope' : 'Enter a path above to preview'}
                </div>
              )
            )}
          </div>

          <div>
            <label className="block text-xs font-semibold text-[var(--color-text-secondary)] mb-2 uppercase tracking-wider">
              Workflow Stages
            </label>
            <div className="space-y-2">
              {ALL_STAGES.map((code) => {
                const display = STAGE_DISPLAY[code]
                const checked = stages.has(code)
                const gateBlocked =
                  previewGateActive && !stagePrerequisitesMet(code, satisfiedStages, stages)
                const missingReq = STAGE_PREREQUISITES[code].filter(
                  (pre) => !satisfiedStages.has(pre) && !stages.has(pre),
                )
                const titleHint =
                  gateBlocked && missingReq.length > 0
                    ? `Requires ${missingReq.map((p) => STAGE_DISPLAY[p].name).join(', ')} completed on disk or selected for this run.`
                    : undefined
                return (
                  <label
                    key={code}
                    title={titleHint}
                    className={clsx(
                      'flex items-start gap-3 rounded p-3 border transition-colors',
                      gateBlocked ? 'cursor-not-allowed opacity-50' : 'cursor-pointer',
                      checked
                        ? 'bg-[var(--color-bg-primary)] border-[var(--color-accent)]'
                        : 'bg-[var(--color-bg-primary)] border-[var(--color-border-muted)] opacity-60',
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={gateBlocked}
                      onChange={() => toggleStage(code)}
                      className="mt-0.5"
                    />
                    <div>
                      <div className="text-sm font-medium text-[var(--color-text-primary)]">{display.name}</div>
                      <div className="text-xs text-[var(--color-text-muted)]">{display.description}</div>
                    </div>
                  </label>
                )
              })}
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-[var(--color-text-secondary)] mb-2 uppercase tracking-wider">
              Run behavior
            </label>
            <div className="rounded border border-[var(--color-border-muted)] bg-[var(--color-bg-primary)] p-3 text-sm text-[var(--color-text-secondary)] space-y-2">
              <div className="font-medium text-[var(--color-text-primary)]">Process STALE / MISSING only</div>
              <p className="text-xs text-[var(--color-text-muted)]">
                Runs only work that is missing, invalid, stale by executor version, or falsely marked done.
                Already-current image stages are skipped.
              </p>
              <div className="rounded border border-[var(--color-warning)]/40 bg-[var(--color-warning-bg)] p-3 text-xs text-[var(--color-warning)] space-y-1">
                <div className="font-semibold">Plan preview</div>
                <div>
                  Click <span className="text-[var(--color-text-primary)]">Refresh</span> in Preview to scan stale/missing
                  counts and stage queues before queueing.
                </div>
                {repairPreviewLoading && <div className="text-[var(--color-text-secondary)]">Scanning…</div>}
                {repairPreview && (
                  <div className="space-y-1">
                    <div>
                      Actions: reconcile={repairPreview.actions.reconciled_rows}, backfill=
                      {repairPreview.actions.backfilled_index_meta}, scoring_targets=
                      {repairPreview.actions.scoring_fix_targets}
                    </div>
                    <div>
                      Summary: repaired={repairPreview.repaired}, skipped(images)={repairPreview.skipped},
                      failed={repairPreview.failed}
                      {typeof repairPreview.issue_hits === 'number'
                        ? `, issue_hits=${repairPreview.issue_hits}`
                        : ''}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="flex items-center justify-between px-5 py-4 border-t border-[var(--color-border-muted)]">
          <Button variant="ghost" onClick={() => setNewRunModalOpen(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={submit}
            loading={submitMut.isPending}
            disabled={validPaths.length === 0 || stages.size === 0}
          >
            Queue Run →
          </Button>
        </div>
      </div>
    </div>
  )
}

function PreviewPanel({ preview }: { preview: ScopePreviewResult }) {
  return (
    <div className="bg-[var(--color-bg-primary)] border border-[var(--color-border-muted)] rounded p-3 space-y-2">
      <div className="flex items-center gap-3 text-sm">
        <span className="text-[var(--color-text-primary)] font-semibold">{preview.image_count.toLocaleString()}</span>
        <span className="text-[var(--color-text-secondary)]">images in</span>
        <span className="text-[var(--color-text-primary)] font-semibold">{preview.folder_count}</span>
        <span className="text-[var(--color-text-secondary)]">folder{preview.folder_count !== 1 ? 's' : ''}</span>
      </div>
      <div className="grid grid-cols-1 gap-1">
        {Object.entries(preview.stage_statuses).map(([code, status]) => {
          const display = STAGE_DISPLAY[code as StageCode]
          const counts = preview.stage_counts[code as StageCode]
          return (
            <div key={code} className="flex items-center gap-2 text-xs">
              <StageStatusIcon status={status} />
              <span className="text-[var(--color-text-secondary)] w-32">{display?.name ?? code}</span>
              <span className="text-[var(--color-text-muted)]">
                {status === 'not_started' && '— not started'}
                {status === 'done' && '✓ all done'}
                {status === 'running' &&
                  counts &&
                  (counts.running
                    ? `${counts.running} running`
                    : `${counts.done} / ${counts.total} in progress`)}
                {status === 'queued' && 'queued'}
                {status === 'partial' && counts && `${counts.done} / ${counts.total} done`}
                {status === 'failed' && counts && `${counts.failed} failed`}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function StageStatusIcon({ status }: { status: string }) {
  return <PhaseStatusIcon status={status} size={14} animated />
}
