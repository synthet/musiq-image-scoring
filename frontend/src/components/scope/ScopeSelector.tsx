import { useState, useEffect } from 'react'
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
import { FULL_PIPELINE_STAGE_CODES } from '@/constants/pipeline'
import { RUNS_QUERY_ROOT } from '@/queryKeys/runs'

const ALL_STAGES: StageCode[] = [...FULL_PIPELINE_STAGE_CODES]

type RunOptionsMode = 'skip_completed' | 'force_all' | 'fix_incomplete' | 'validation_repair'

type RunOptionCopy = {
  title: string
  whatThisDoes: string
  whatThisDoesNotDo: string
}

const RUN_OPTION_COPY_BY_MODE = {
  skip_completed: {
    title: 'Process NEW / NOT processed',
    whatThisDoes:
      'Runs selected stages only where results are missing, while reusing already completed work.',
    whatThisDoesNotDo:
      'Does not recompute stages that are already marked done for an image.',
  },
  force_all: {
    title: 'Process ALL (overwrite existing results)',
    whatThisDoes: 'Re-runs selected stages for every image in scope, even when prior results exist.',
    whatThisDoesNotDo:
      'Does not preserve previous stage outputs for selected stages; existing results are replaced.',
  },
  fix_incomplete: {
    title: 'Fix missing/incomplete data',
    whatThisDoes:
      'Targets images missing required data for the selected pipeline stages so incomplete records can be fixed.',
    whatThisDoesNotDo:
      'Does not force a full re-run of complete images, avoiding unnecessary processing.',
  },
  validation_repair: {
    title: 'Validation-repair pipeline',
    whatThisDoes:
      'Scans selected scope for invalid, missing, or out-of-range fields, applies minimal safe repairs where configured, and builds stage-specific repair queues.',
    whatThisDoesNotDo:
      'Does not replace reviewing the dry-run preview before applying; use Refresh in Preview to inspect counts and queues first.',
  },
} satisfies Record<RunOptionsMode, RunOptionCopy>

const RUN_OPTION_ORDER: RunOptionsMode[] = [
  'skip_completed',
  'force_all',
  'fix_incomplete',
  'validation_repair',
]

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
  const [runOptionsMode, setRunOptionsMode] = useState<RunOptionsMode>('skip_completed')
  const [preview, setPreview] = useState<ScopePreviewResult | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [repairPreview, setRepairPreview] = useState<ValidationRepairPreview | null>(null)
  const [repairPreviewLoading, setRepairPreviewLoading] = useState(false)

  // Modal stays mounted while closed (`return null`); reset local state whenever it opens
  // so preview is not left from a previous folder and paths re-apply even if `newRunInitialPath`
  // is unchanged (e.g. user cleared the field then double-clicked the same folder again).
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
    setRunOptionsMode('skip_completed')
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
      if (runOptionsMode === 'validation_repair') {
        setRepairPreviewLoading(true)
        const stagesOrdered = ALL_STAGES.filter((code) => stages.has(code))
        const rep = await scopeApi.validationRepairPreview(validPaths, stagesOrdered)
        setRepairPreview(rep)
      }
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
    // Pipeline order (not Set iteration order — checkbox order would scramble stages).
    const stagesOrdered = ALL_STAGES.filter((code) => stages.has(code))
    const skip_done = runOptionsMode !== 'force_all'
    const force_rerun = runOptionsMode === 'force_all'
    const fix_incomplete_stages = runOptionsMode === 'fix_incomplete'
    const validation_repair_mode = runOptionsMode === 'validation_repair'
    submitMut.mutate({
      scope_type: scopeType,
      scope_paths: validPaths,
      stages: stagesOrdered,
      skip_done,
      force_rerun,
      fix_incomplete_stages,
      validation_repair_mode,
      validation_repair_dry_run: false,
    })
  }

  function toggleStage(code: StageCode) {
    setStages((prev) => {
      const next = new Set(prev)
      if (next.has(code)) next.delete(code)
      else next.add(code)
      return next
    })
  }

  if (!newRunModalOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-[var(--color-bg-secondary)] border border-[var(--color-border)] rounded-lg shadow-2xl w-[600px] max-h-[90vh] overflow-y-auto">
        {/* Header */}
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
          {/* Scope type */}
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

          {/* Paths */}
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
              <Button
                size="xs"
                variant="ghost"
                onClick={() => setPaths([...paths, ''])}
              >
                <Plus size={14} />
                Add path
              </Button>
            </div>
          </div>

          {/* Preview */}
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
                  {validPaths.length > 0
                    ? 'Click Refresh to preview scope'
                    : 'Enter a path above to preview'}
                </div>
              )
            )}
          </div>

          {/* Workflow (stages) */}
          <div>
            <label className="block text-xs font-semibold text-[var(--color-text-secondary)] mb-2 uppercase tracking-wider">
              Workflow Stages
            </label>
            <div className="space-y-2">
              {ALL_STAGES.map((code) => {
                const display = STAGE_DISPLAY[code]
                const checked = stages.has(code)
                return (
                  <label
                    key={code}
                    className={clsx(
                      'flex items-start gap-3 rounded p-3 border cursor-pointer transition-colors',
                      checked
                        ? 'bg-[var(--color-bg-primary)] border-[var(--color-accent)]'
                        : 'bg-[var(--color-bg-primary)] border-[var(--color-border-muted)] opacity-60',
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
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

          {/* Options */}
          <div>
            <label className="block text-xs font-semibold text-[var(--color-text-secondary)] mb-2 uppercase tracking-wider">
              Options
            </label>
            <div className="space-y-2">
              {RUN_OPTION_ORDER.map((mode) => {
                const option = RUN_OPTION_COPY_BY_MODE[mode]
                const isFixIncomplete = mode === 'fix_incomplete'
                const isValidationRepair = mode === 'validation_repair'
                return (
                  <label
                    key={mode}
                    className="flex items-start gap-2 text-sm text-[var(--color-text-secondary)] cursor-pointer"
                  >
                    <input
                      type="radio"
                      name="run-options"
                      className="mt-1"
                      checked={runOptionsMode === mode}
                      onChange={() => setRunOptionsMode(mode)}
                      {...(isFixIncomplete ? { 'aria-describedby': 'fix-incomplete-help' } : {})}
                    />
                    <span>
                      <span className="flex flex-wrap items-center gap-2">
                        <span
                          className={
                            isValidationRepair
                              ? 'text-[var(--color-warning)] font-semibold'
                              : 'text-[var(--color-text-primary)]'
                          }
                        >
                          {option.title}
                        </span>
                      </span>
                      <span
                        className={
                          isValidationRepair
                            ? 'block text-xs text-[var(--color-warning)] mt-0.5'
                            : 'block text-xs text-[var(--color-text-muted)] mt-0.5'
                        }
                      >
                        What this does: {option.whatThisDoes}
                      </span>
                      <span
                        className={
                          isValidationRepair
                            ? 'block text-xs text-[var(--color-warning)] mt-0.5'
                            : 'block text-xs text-[var(--color-text-muted)] mt-0.5'
                        }
                      >
                        What this does not do: {option.whatThisDoesNotDo}
                      </span>
                    </span>
                  </label>
                )
              })}
              {runOptionsMode === 'validation_repair' && (
                <div className="ml-6 rounded border border-[var(--color-warning)]/40 bg-[var(--color-warning-bg)] p-3 text-xs text-[var(--color-warning)] space-y-1">
                  <div className="font-semibold">Dry-run repair preview</div>
                  <div>
                    Click <span className="text-[var(--color-text-primary)]">Refresh</span> in Preview to scan issue
                    counts and stage repair queues.
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
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
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
