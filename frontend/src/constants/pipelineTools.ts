/**
 * Pipeline Tools tab: copy, limits, and machine-readable tool lists (single source of truth).
 */

export const PIPELINE_TOOLS_HEADER = {
  title: 'Pipeline Tools',
  subtitle: 'Maintain data integrity and perform targeted repairs.',
} as const

export const SECTION = {
  workflow_heal: {
    title: 'Workflow Integrity & Healing',
    subtitle:
      'Per-step repair: identifies false completions (marked done but missing data), resets them, and spawns targeted runs for affected folders.',
  },
} as const

export const HEAL_STEPS = [
  {
    code: 'indexing',
    name: 'Heal Indexing',
    description: 'Finds images with no hash, resets false completions, and re-indexes.',
  },
  {
    code: 'metadata',
    name: 'Heal Metadata',
    description: 'Finds images missing thumbnails or exif, resets, and regenerates.',
  },
  {
    code: 'scoring',
    name: 'Heal Scoring',
    description: 'Finds images with missing AI scores, resets status, and re-scores.',
  },
  {
    code: 'culling',
    name: 'Heal Culling',
    description: 'Finds images missing stack/cluster IDs, resets, and re-clusters.',
  },
  {
    code: 'keywords',
    name: 'Heal Keywords',
    description: 'Finds images with no keywords, resets status, and re-tags.',
  },
  {
    code: 'bird_species',
    name: 'Heal Bird Species',
    description: 'Finds bird images with no species tags, resets, and re-classifies.',
  },
] as const
