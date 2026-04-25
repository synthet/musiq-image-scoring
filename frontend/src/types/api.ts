// ─── Run (maps to jobs table) ─────────────────────────────────────────────

export type RunStatus =
  | 'pending'
  | 'queued'
  | 'running'
  | 'paused'
  | 'completed'
  | 'failed'
  | 'canceled'
  | 'interrupted'

export interface Run {
  id: number
  scope_type: 'file' | 'folder' | 'folder_recursive' | 'path_list'
  scope_paths: string[]
  input_path: string  // legacy fallback
  job_type: string
  status: RunStatus
  queue_position: number | null
  cancel_requested: boolean
  created_at: string
  enqueued_at: string | null
  started_at: string | null
  finished_at: string | null
  log: string | null
  current_phase: string | null
  next_phase_index: number | null
  runner_state: string | null
  /** Parsed jobs.queue_payload — run_mode, force_rescan, scope, clustering params, etc. */
  queue_payload?: Record<string, unknown> | null
  /** Backend-derived feature flags for this run type / phase plan. */
  capabilities?: {
    execution_report?: boolean
  } | null
  /** Human-readable reason / scope for troubleshooting (jobs.description). */
  description?: string | null
}

// ─── Stage (maps to job_phases) ──────────────────────────────────────────

export type StageState =
  | 'pending'
  | 'queued'
  | 'running'
  | 'paused'
  | 'completed'
  | 'failed'
  | 'skipped'
  | 'interrupted'
  | 'cancel_requested'
  | 'restarting'
  | 'canceled'

// UI-facing stage codes
export type StageCode =
  | 'indexing'      // Discovery
  | 'metadata'      // Inspection
  | 'scoring'       // Quality Analysis
  | 'culling'       // Similarity Clustering
  | 'keywords'      // Tagging
  | 'bird_species'  // Bird Species ID

export const STAGE_DISPLAY: Record<StageCode, { name: string; description: string }> = {
  indexing:     { name: 'Discovery', description: 'Scan and register image files' },
  metadata:     { name: 'Inspection', description: 'Extract EXIF metadata and generate thumbnails' },
  scoring:      { name: 'Quality Analysis', description: 'AI-powered quality scoring (MUSIQ, LIQE, TOPIQ, Q-Align)' },
  culling:      { name: 'Similarity Clustering', description: 'Group similar images into stacks' },
  keywords:     { name: 'Tagging', description: 'Generate keywords and captions via BLIP/CLIP' },
  bird_species: { name: 'Bird Species ID', description: 'Identify bird species with BioCLIP 2 (run after Tagging)' },
}

export interface Stage {
  phase_order: number
  phase_code: StageCode
  state: StageState
  started_at: string | null
  completed_at: string | null
  error_message: string | null
  // extended from phase status
  items_done?: number
  items_total?: number
  throughput?: number
  eta_seconds?: number
}

// ─── Step (sub-task within a Stage) ─────────────────────────────────────

export type StepState = 'pending' | 'running' | 'completed' | 'failed' | 'skipped'

export interface Step {
  id: number
  step_code: string
  step_name: string
  status: StepState
  started_at: string | null
  completed_at: string | null
  items_done: number
  items_total: number
  throughput_rps: number | null
  error_message: string | null
}

export const STEP_DISPLAY: Record<string, string> = {
  musiq:   'Multi-Scale Quality',
  liqe:    'Learned Quality',
  topiq:   'Top-Down Quality',
  qalign:  'Alignment Quality',
  blip:    'BLIP Captioning',
  clip:    'CLIP Tagging',
}

// ─── Work Item (image being processed) ──────────────────────────────────

export interface WorkItem {
  image_id: number
  image_path: string
  filename: string
  status: 'pending' | 'running' | 'done' | 'skipped' | 'failed'
  duration_ms: number | null
  error: string | null
  skip_reason?: string | null
  skipped_by?: string | null
  attempt_count?: number | null
}

// ─── Scope ───────────────────────────────────────────────────────────────

export interface ScopePreviewResult {
  image_count: number
  folder_count: number
  stage_statuses: Record<StageCode, string>
  stage_counts: Record<
    StageCode,
    { done: number; failed: number; skipped: number; total: number; running?: number; queued?: number }
  >
}

export interface ValidationRepairPreview {
  issue_counts: Record<string, number>
  stage_queues: Record<string, number[]>
  issue_hits?: number
  actions: {
    reconciled_rows: number
    backfilled_index_meta: number
    scoring_fix_targets: number
  }
  repaired: number
  skipped: number
  failed: number
  dry_run: boolean
}

// ─── Execution Report (per-image action log & before/after snapshots) ────

export interface PhaseExecutionReport {
  images_in_scope: number
  images_targeted: number
  images_processed: number
  images_skipped: number
  images_failed: number
  duration_seconds: number
  incomplete_fields_breakdown?: Record<string, number>
}

export interface ScoreAggregate {
  score_mean: number
  score_stddev: number
  incomplete_count: number
}

export interface JobExecutionReport {
  run_mode: string
  phases: Record<string, PhaseExecutionReport>
  aggregate_before?: ScoreAggregate
  aggregate_after?: ScoreAggregate
}

export interface RunReportResponse {
  available: boolean
  report?: JobExecutionReport
  reason?: string
  message?: string
  run_type?: string
}

export interface ImageAction {
  id: number
  image_id: number
  file_path: string | null
  phase_code: string
  action: 'processed' | 'skipped' | 'failed' | 'unchanged'
  reason: string | null
  before_snapshot: Record<string, number | string | null> | null
  after_snapshot: Record<string, number | string | null> | null
  created_at: string
}

export interface ImageActionsResponse {
  items: ImageAction[]
  total: number
}

// ─── Folder tree ─────────────────────────────────────────────────────────

export interface FolderNode {
  path: string
  name: string
  children: FolderNode[]
  phase_statuses?: Record<string, string>
  image_count?: number
}

// ─── Queue entry ─────────────────────────────────────────────────────────

export interface QueueEntry {
  run_id: number
  position: number
  input_path: string
  scope_paths: string[]
  created_at: string
  enqueued_at: string
}

// ─── Image (gallery) — field names match electron-image-scoring ImageRow ────
//
// electron/types.ts ImageRow fields are authoritative (Electron reads from DB directly).
// The Python REST API returns the same column names from the IMAGES table.
// DB naming convention: score_* prefix (score_general, score_liqe, …)

export interface Image {
  // Identity
  id: number
  file_path: string           // absolute file path
  file_name: string           // base filename (DB: file_name)
  folder_path?: string        // derived, may not be in DB row
  folder_id?: number | null

  // Thumbnails
  thumbnail_path?: string | null
  win_path?: string | null    // Windows path variant (from file_paths join)

  // User metadata
  rating: number | null       // 0–5 stars
  label: string | null        // 'Pick' | 'Reject' | 'Normal'
  title?: string | null
  description?: string | null
  keywords?: string | null    // stored as BLOB/string in DB (comma-separated)
  caption?: string | null

  // Quality scores — DB column names (score_* prefix matches Electron & DB)
  score?: number | null             // legacy composite (DB: score)
  score_general?: number | null     // general quality
  score_technical?: number | null   // technical quality
  score_aesthetic?: number | null   // aesthetic quality
  score_liqe?: number | null        // LIQE
  score_spaq?: number | null        // SPAQ (legacy)
  score_ava?: number | null         // AVA (legacy)
  score_koniq?: number | null       // KonIQ (legacy)
  score_paq2piq?: number | null     // PAQ2PIQ (legacy)
  // New model scores (added by this pipeline, not yet in Electron)
  musiq_score?: number | null       // MUSIQ
  topiq_score?: number | null       // TOPIQ
  qalign_score?: number | null      // Q-Align
  composite_score?: number | null   // computed composite

  // File metadata
  created_at?: string | null
  updated_at?: string | null
  file_type?: string | null
  file_size?: number | null
  image_hash?: string | null
  /** 1 = full-file SHA-256; 2 = embedded preview / content identity (see image_identity_hash) */
  hash_version?: number | null
  /** Stable identifier from metadata / indexing (DB: image_uuid) */
  image_uuid?: string | null
  stack_id?: number | null
  burst_uuid?: string | null
  scores_json?: string | null
  model_version?: string | null

  /** Phase-level status rows (mapping of phase_code -> status row) */
  phase_statuses?: Record<string, ImagePhaseStatusRow | string> | null
}

/** Per-phase row from `get_image_phase_statuses` (GET /api/images/{id}). */
export interface ImagePhaseStatusRow {
  status: string
  executor_version?: string | null
  app_version?: string | null
  updated_at?: string | null
  attempt_count?: number | null
  last_error?: string | null
  skip_reason?: string | null
  skipped_by?: string | null
}

/** Payload from GET /api/images/{id}, by-uuid, or by-hash */
export interface ImageDetail extends Image {
  file_paths?: string[] | null
  resolved_path?: string | null
  /** Phase code → status info (legacy responses may use plain string values). */
  phase_statuses?: Record<string, ImagePhaseStatusRow | string> | null
}

// ─── WebSocket events ────────────────────────────────────────────────────

export interface WsRunProgress {
  type: 'run_progress'
  run_id: number
  stage: string
  step?: string
  items_done: number
  items_total: number
  throughput: number
  eta_seconds: number
}

export interface WsStageTransition {
  type: 'stage_transition'
  run_id: number
  stage: string
  from_state: StageState
  to_state: StageState
}

export interface WsLogLine {
  type: 'log_line'
  run_id: number
  level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR'
  message: string
  ts: string
}

export interface WsQueueUpdate {
  type: 'queue_update'
  queue: QueueEntry[]
}

export interface WsWorkItemDone {
  type: 'work_item_done'
  run_id: number
  image_id: number
  stage: string
  status: string
}

export type WsEvent = WsRunProgress | WsStageTransition | WsLogLine | WsQueueUpdate | WsWorkItemDone

// ─── Electron-compatible type aliases ────────────────────────────────────
// Mirror electron-image-scoring's electron/types.ts for shared contracts

/** @alias Image — matches electron/types.ts ImageRow */
export type ImageRow = Image

/** Image updates shape — matches electron/types.ts ImageUpdates */
export interface ImageUpdates {
  rating?: number
  label?: string
  title?: string
  description?: string
  keywords?: string  // DB stores as string (BLOB); comma-separated
  write_sidecar?: boolean
}

/** Folder row — matches electron/types.ts FolderRow */
export interface ElectronFolderRow {
  id: number
  path: string
  parent_id: number | null
  is_fully_scored: number  // 0 or 1
  image_count: number
}

/** Stack row — matches electron/types.ts StackRow */
export interface StackRow extends Image {
  stack_id?: number | null
  stack_key?: number
  image_count?: number
  sort_value?: number
}
