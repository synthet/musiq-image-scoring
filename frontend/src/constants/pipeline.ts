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
