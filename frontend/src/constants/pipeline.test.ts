import { describe, it, expect } from 'vitest'
import type { StageCode } from '@/types/api'
import { pruneStageSelection, stagePrerequisitesMet, FULL_PIPELINE_STAGE_CODES } from '@/constants/pipeline'

describe('stagePrerequisitesMet / pruneStageSelection', () => {
  it('allows downstream phase when prerequisite is selected for same run', () => {
    const satisfied = new Set<StageCode>()
    const selected = new Set<StageCode>(['metadata', 'scoring'])
    expect(stagePrerequisitesMet('scoring', satisfied, selected)).toBe(true)
  })

  it('pruneStageSelection removes keywords when scoring is absent from scope and selection', () => {
    const satisfied = new Set<StageCode>()
    const sel = new Set<StageCode>(['keywords'])
    expect(pruneStageSelection(sel, satisfied).size).toBe(0)
  })

  it('keeps ordered chain when scope satisfies prerequisites', () => {
    const satisfied = new Set<StageCode>(['indexing', 'metadata', 'scoring'])
    const sel = new Set<StageCode>(['keywords'])
    expect(pruneStageSelection(sel, satisfied)).toEqual(new Set(['keywords']))
  })

  it('FULL_PIPELINE_STAGE_CODES matches prune stability when all selected', () => {
    const satisfied = new Set<StageCode>()
    const all = new Set<StageCode>(FULL_PIPELINE_STAGE_CODES as StageCode[])
    expect(pruneStageSelection(all, satisfied)).toEqual(all)
  })
})
