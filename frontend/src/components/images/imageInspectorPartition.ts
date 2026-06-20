import type { ImageDetail } from '@/types/api'

/** Keys handled outside the scalar partition loop (dedicated sections or API-only). */
export const INSPECTOR_SKIP_KEYS = new Set([
  'file_paths',
  'resolved_path',
  'phase_statuses',
  'model_scores',
  'embeddings_present',
  'technical_failure_detection',
  'indexing_metadata',
])

/** All keys the inspector explicitly maps; anything else goes to `unmapped`. */
export const INSPECTOR_KNOWN_KEYS = new Set([
  ...INSPECTOR_SKIP_KEYS,
  'id',
  'image_uuid',
  'image_hash',
  'hash_version',
  'burst_uuid',
  'stack_id',
  'sub_stack_id',
  'folder_id',
  'file_name',
  'file_type',
  'file_size',
  'model_version',
  'file_path',
  'thumbnail_path',
  'thumbnail_path_win',
  'win_path',
  'score',
  'score_general',
  'score_technical',
  'score_aesthetic',
  'score_liqe',
  'score_spaq',
  'score_ava',
  'score_koniq',
  'score_paq2piq',
  'musiq_score',
  'topiq_score',
  'arniqa_score',
  'qalign_score',
  'clip_quality_v0_score',
  'composite_score',
  'rating',
  'label',
  'title',
  'description',
  'keywords',
  'caption',
  'created_at',
  'updated_at',
  'pick_status',
  'cull_decision',
  'cull_policy_version',
  'job_id',
  'metadata',
])

export const INSPECTOR_LABELS: Record<string, string> = {
  pick_status: 'Pick flag',
  cull_decision: 'Auto cull decision',
  cull_policy_version: 'Cull policy version',
  job_id: 'Indexing job',
  sub_stack_id: 'Sub-stack',
  stack_id: 'Stack',
  folder_id: 'Folder',
  hash_version: 'Hash version',
  thumbnail_path_win: 'Thumbnail (Windows)',
  thumbnail_path: 'Thumbnail',
  file_path: 'File path',
  resolved_path: 'Resolved path',
  file_paths: 'File paths',
  win_path: 'Windows path',
  metadata: 'Metadata (raw)',
}

/** Display order for the Paths inspector table. */
export const PATHS_TABLE_ROW_ORDER = [
  'file_path',
  'resolved_path',
  'win_path',
  'thumbnail_path',
  'thumbnail_path_win',
  'file_paths',
] as const

export function buildPathsTableEntries(
  data: ImageDetail,
  pathScalars: [string, unknown][],
): [string, unknown][] {
  const byKey = new Map(pathScalars)
  if (data.resolved_path) {
    byKey.set('resolved_path', data.resolved_path)
  }
  if (data.file_paths && data.file_paths.length > 0) {
    byKey.set('file_paths', data.file_paths)
  }
  const rows: [string, unknown][] = []
  for (const key of PATHS_TABLE_ROW_ORDER) {
    const v = byKey.get(key)
    if (v !== undefined && v !== null && v !== '') {
      rows.push([key, v])
      byKey.delete(key)
    }
  }
  for (const [k, v] of byKey) {
    if (v !== undefined && v !== null && v !== '') {
      rows.push([k, v])
    }
  }
  return rows
}

export function inspectorLabel(key: string): string {
  return INSPECTOR_LABELS[key] ?? key
}

export function isScoreKey(k: string): boolean {
  return (
    k === 'score' ||
    k.startsWith('score_') ||
    k === 'musiq_score' ||
    k === 'topiq_score' ||
    k === 'arniqa_score' ||
    k === 'qalign_score' ||
    k === 'clip_quality_v0_score' ||
    k === 'composite_score'
  )
}

export type InspectorBuckets = {
  identity: [string, unknown][]
  paths: [string, unknown][]
  scores: [string, unknown][]
  user: [string, unknown][]
  dates: [string, unknown][]
  culling: [string, unknown][]
  provenance: [string, unknown][]
  unmapped: [string, unknown][]
}

export function partitionScalars(data: ImageDetail): InspectorBuckets {
  const identityKeys = new Set([
    'id',
    'image_uuid',
    'image_hash',
    'hash_version',
    'burst_uuid',
    'stack_id',
    'sub_stack_id',
    'folder_id',
    'file_name',
    'file_type',
    'file_size',
    'model_version',
  ])
  const pathKeys = new Set(['file_path', 'thumbnail_path', 'thumbnail_path_win', 'win_path'])
  const userKeys = new Set(['rating', 'label', 'title', 'description', 'keywords', 'caption'])
  const dateKeys = new Set(['created_at', 'updated_at'])
  const cullingKeys = new Set(['pick_status', 'cull_decision', 'cull_policy_version'])
  const provenanceKeys = new Set(['job_id'])

  const identity: [string, unknown][] = []
  const paths: [string, unknown][] = []
  const scores: [string, unknown][] = []
  const user: [string, unknown][] = []
  const dates: [string, unknown][] = []
  const culling: [string, unknown][] = []
  const provenance: [string, unknown][] = []
  const unmapped: [string, unknown][] = []

  const raw = data as unknown as Record<string, unknown>
  for (const k of Object.keys(raw)) {
    if (INSPECTOR_SKIP_KEYS.has(k)) continue
    if (k === 'metadata') continue

    const v = raw[k]
    if (isScoreKey(k)) {
      scores.push([k, v])
      continue
    }
    if (identityKeys.has(k)) {
      identity.push([k, v])
      continue
    }
    if (pathKeys.has(k)) {
      paths.push([k, v])
      continue
    }
    if (userKeys.has(k)) {
      user.push([k, v])
      continue
    }
    if (dateKeys.has(k)) {
      dates.push([k, v])
      continue
    }
    if (cullingKeys.has(k)) {
      culling.push([k, v])
      continue
    }
    if (provenanceKeys.has(k)) {
      provenance.push([k, v])
      continue
    }
    if (!INSPECTOR_KNOWN_KEYS.has(k)) {
      unmapped.push([k, v])
    }
  }

  return { identity, paths, scores, user, dates, culling, provenance, unmapped }
}

export function tryParseJson(value: unknown): Record<string, unknown> | null {
  if (value == null) return null
  if (typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>
  }
  if (typeof value !== 'string' || !value.trim()) return null
  try {
    const parsed = JSON.parse(value) as unknown
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>
    }
  } catch {
    return null
  }
  return null
}
