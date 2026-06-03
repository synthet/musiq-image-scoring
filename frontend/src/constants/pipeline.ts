import type { StageCode } from '@/types/api'

/** Same order as New Run with every stage checked (canonical pipeline + bird_species). */
export const FULL_PIPELINE_STAGE_CODES: StageCode[] = [
  'indexing',
  'metadata',
  'scoring',
  'culling',
  'keywords',
  'bird_species',
]

/** Direct prerequisites per stage (aligned with backend ``modules.phases.PHASE_PREREQUISITES``). */
export const STAGE_PREREQUISITES: Record<StageCode, StageCode[]> = {
  indexing: [],
  metadata: ['indexing'],
  scoring: ['metadata'],
  culling: ['scoring'],
  keywords: ['scoring'],
  bird_species: ['keywords'],
  maintenance: [],
}

/** True when every prerequisite is scope-complete or selected for this run. */
export function stagePrerequisitesMet(
  code: StageCode,
  satisfied: ReadonlySet<StageCode>,
  selected: ReadonlySet<StageCode>,
): boolean {
  return STAGE_PREREQUISITES[code].every((pre) => satisfied.has(pre) || selected.has(pre))
}

/** Drop selections whose prerequisites are not satisfied by scope nor by the remaining selection. */
export function pruneStageSelection(selected: ReadonlySet<StageCode>, satisfied: ReadonlySet<StageCode>): Set<StageCode> {
  const next = new Set(selected)
  let changed = true
  while (changed) {
    changed = false
    for (const code of [...next]) {
      if (!stagePrerequisitesMet(code, satisfied, next)) {
        next.delete(code)
        changed = true
      }
    }
  }
  return next
}

