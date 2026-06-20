import type { ModelMembership } from '@/api/config'
import type { ModelScoreEntry } from '@/types/api'

/** Human-readable labels keyed by bare model name. */
export const SCORE_LABELS: Record<string, string> = {
  topiq: 'TOPIQ-NR',
  musiq: 'MUSIQ',
  qalign: 'Q-Align',
  cursor: 'Cursor (LLM)',
  claude: 'Claude (LLM)',
  liqe: 'LIQE',
  spaq: 'SPAQ',
  ava: 'AVA',
  paq2piq: 'PAQ2PIQ',
  koniq: 'KonIQ',
  arniqa: 'ARNIQA',
  clip_quality_v0: 'CLIP Quality',
  composite: 'Composite',
  general: 'General',
  technical: 'Technical',
  aesthetic: 'Aesthetic',
}

/** Deprecated / unused models — never shown in UI rosters. */
export const HIDDEN_SCORE_MODELS = new Set([
  'paq2piq',
  'koniq',
  'musiq',
  'qalign',
])

/** Auxiliary scores stored in image_model_scores but outside scoring.models fusion. */
export const AUXILIARY_SCORE_MODELS = ['clip_quality_v0'] as const

/** Preferred roster order for production IQA models. */
export const PRODUCTION_MODEL_DISPLAY_ORDER = [
  'spaq',
  'ava',
  'liqe',
  'topiq',
  'arniqa',
] as const

export function scoreLabel(key: string): string {
  if (key === 'score') return 'Score'
  const base = key.replace(/^score_/, '').replace(/_score$/, '')
  return SCORE_LABELS[base] ?? key
}

export function isProductionModel(name: string, membership: ModelMembership | undefined): boolean {
  if (HIDDEN_SCORE_MODELS.has(name)) return false
  if (!membership) {
    return PRODUCTION_MODEL_DISPLAY_ORDER.includes(
      name as (typeof PRODUCTION_MODEL_DISPLAY_ORDER)[number],
    )
  }
  if (membership.shadow) return false
  return membership.enabled !== false
}

/** Models shown in inspector / breakdown: production IQA + auxiliary scores. */
export function resolveVisibleModels(
  scoringModels: Record<string, ModelMembership> | undefined,
): string[] {
  const membership = scoringModels ?? {}
  const names = new Set<string>()

  for (const name of PRODUCTION_MODEL_DISPLAY_ORDER) {
    if (isProductionModel(name, membership[name])) names.add(name)
  }
  for (const [name, m] of Object.entries(membership)) {
    if (isProductionModel(name, m)) names.add(name)
  }
  for (const aux of AUXILIARY_SCORE_MODELS) {
    names.add(aux)
  }

  const ordered: string[] = []
  for (const name of PRODUCTION_MODEL_DISPLAY_ORDER) {
    if (names.has(name)) ordered.push(name)
  }
  for (const name of names) {
    if (
      !ordered.includes(name) &&
      !AUXILIARY_SCORE_MODELS.includes(name as (typeof AUXILIARY_SCORE_MODELS)[number])
    ) {
      ordered.push(name)
    }
  }
  for (const aux of AUXILIARY_SCORE_MODELS) {
    if (names.has(aux)) ordered.push(aux)
  }
  return ordered
}

export function resolveModelValue(
  raw: Record<string, unknown>,
  modelScores: Record<string, ModelScoreEntry>,
  name: string,
): number | null {
  const entry = modelScores[name]
  const fromBlock = entry ? entry.normalized ?? entry.raw_score : null
  if (typeof fromBlock === 'number') return fromBlock
  const legacy = raw[`score_${name}`]
  if (typeof legacy === 'number') return legacy
  const flat = raw[`${name}_score`]
  if (typeof flat === 'number') return flat
  return null
}

export function modelSortKey(name: string): string {
  return `model:${name}`
}
