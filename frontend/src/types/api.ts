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

export type { StageCode } from '@synthet/image-scoring-design'
export { STAGE_DISPLAY } from '@synthet/image-scoring-design'
import type { StageCode } from '@synthet/image-scoring-design'

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

// ─── Runs auto-drive buckets ─────────────────────────────────────────────

export interface RunFolderBucketPhase {
  code: StageCode
  name: string
  status: string
  done: number
  skipped: number
  failed: number
  running: number
  queued: number
  paused: number
  cancel_requested: number
  restarting: number
  total: number
  percent: number
}

export interface RunFolderBucket {
  path: string
  image_count: number
  bucket: string
  current_phase: StageCode | null
  next_phases: StageCode[]
  blocked_by: Record<string, string[]>
  overall_percent: number
  phase_statuses: RunFolderBucketPhase[]
  plan_key: string | null
}

export interface RunFolderBucketsResponse {
  items: RunFolderBucket[]
  total: number
  limit: number
  offset: number
  bucket_counts: Record<string, number>
  phase_counts: Record<string, number>
  target_phases: StageCode[]
}

export interface RunsAutoDriveRequest {
  root_path?: string
  folder_paths?: string[]
  target_phases?: string[]
  limit?: number
  dry_run?: boolean
  max_repeats?: number
  generate_captions?: boolean
}

export interface RunsAutoDriveResult {
  dry_run: boolean
  run_mode: string
  limit: number
  scheduled: Array<{
    folder_path: string
    phases: StageCode[]
    bucket?: string
    plan_key?: string
    dry_run?: boolean
    job_id?: number
    queue_position?: number
  }>
  skipped: Array<{
    folder_path: string
    phases: StageCode[]
    reason: string
    attempts?: number
    last_run_id?: number | null
    last_status?: string | null
    error?: string
    missing?: Record<string, string[]>
  }>
  candidates: number
  total_outstanding: number
  loop_detected: number
  bucket_counts: Record<string, number>
  phase_counts: Record<string, number>
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

/** One row from the backend `image_model_scores` table (see API_CONTRACT.md). */
export interface ModelScoreEntry {
  normalized?: number | null
  raw_score?: number | null
  status?: string | null
  is_shadow?: boolean
}

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
  // Structured per-model scores from image_model_scores (incl. shadow engines
  // like cursor/claude). Production models also appear as flat {name}_score above.
  model_scores?: Record<string, ModelScoreEntry> | null

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

  /** Presence flags for embedding spaces (mobilenet, clip, bioclip, blip) */
  embeddings_present?: Record<string, boolean> | null
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
  last_run_action?: {
    action: 'processed' | 'skipped' | 'failed' | 'unchanged'
    reason: string | null
    created_at: string
    job_id: number | null
  } | null
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

// ─── Similarity ─────────────────────────────────────────────────────────

export interface SimilarImage {
  image_id: number
  file_path: string
  similarity: number
}

export interface SimilarImagesResponse {
  query_image_id: number
  results: SimilarImage[]
  count: number
  embedding_space?: string | null
}

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
