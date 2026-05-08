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
      'Per-phase repair: finds images that still fail completeness checks (including mistaken “done” rows where that phase resets them), resets phase status when applicable, and queues folder-scoped pipeline runs up to your folder budget (skipping folders already under active jobs).',
  },
  data_backfill: {
    title: 'Data Backfill',
    subtitle:
      'Maintenance jobs that fill gaps directly—compute missing default clustering embeddings or CLIP vectors, or re-read EXIF with exiftool—without resetting pipeline phase statuses.',
  },
  cleanup_stale: {
    title: 'Cleanup Stale Records',
    subtitle:
      'Remove or reconcile DB rows that no longer reflect reality—orphan rows for deleted files, stuck per-image phase statuses, and orphan stacks—so heal stops re-targeting folders it can never finish.',
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
    description:
      'Finds images with no thumbnail paths and no extracted EXIF/XMP rows (all absent together); resets mistaken completions and re-runs metadata extraction.',
  },
  {
    code: 'scoring',
    name: 'Heal Scoring',
    description:
      'Finds images missing required model scores, composite score, rating, or label; resets phase status and re-runs quality analysis.',
  },
  {
    code: 'culling',
    name: 'Heal Culling',
    description:
      'Finds images with no cull decision, images stuck with a decision but no stack while default clustering embeddings are missing, or multi-shot bursts that never stacked (2+ captures within one clustering time-gap span); resets mistaken completions and re-runs similarity clustering / selection.',
  },
  {
    code: 'keywords',
    name: 'Heal Keywords',
    description:
      'Finds images with no normalized keywords and an empty legacy keywords field; resets phase status and re-runs tagging.',
  },
  {
    code: 'bird_species',
    name: 'Heal Bird Species',
    description:
      'Finds bird-tagged images without a species keyword and queues classification for folders that still need work (including after the classifier executor version changes).',
  },
] as const

export const BACKFILL_STEPS = [
  {
    code: 'backfill_embeddings',
    name: 'Backfill MobileNet Vectors',
    description:
      'Finds images missing default clustering-space embeddings (MobileNet features via the clustering engine) and writes them in batches without changing phase statuses.',
  },
  {
    code: 'backfill_clip_vectors',
    name: 'Backfill CLIP Vectors',
    description:
      'Finds images missing CLIP ViT-B/32 image embeddings (clip_vit_b32_image space), extracts vectors with the tagging CLIP model, and stores them without changing phase statuses.',
  },
  {
    code: 'backfill_exif_camera_lens',
    name: 'Backfill EXIF Camera/Lens',
    description: 'Finds images missing camera or lens metadata and re-extracts them via exiftool.',
  },
  {
    code: 'backfill_exif_gps',
    name: 'Backfill EXIF GPS',
    description: 'Finds images missing GPS coordinates and re-extracts them via exiftool.',
  },
] as const

export const CLEANUP_STEPS = [
  {
    code: 'prune_missing',
    name: 'Prune Missing Files',
    description:
      'Scans image rows and deletes any whose underlying file is gone from disk. Use this when heal keeps re-targeting a folder because it still contains rows for deleted captures. Run with Dry Run first to see how many rows would be removed.',
    destructive: true,
  },
  {
    code: 'reconcile',
    name: 'Reconcile Phase Status',
    description:
      'Resets per-image phase rows that are stuck in “running” for jobs that have already terminated, and removes orphan stacks. Cosmetic but unblocks folders whose progress aggregates lie about pending work.',
    destructive: false,
  },
] as const
