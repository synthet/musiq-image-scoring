/**
 * Centralized copy and configuration for Maintenance & Pipeline Tools.
 * This is the single source of truth for UI strings, tool descriptions, and limits.
 */
export const MaintenanceToolsCopy = {
  tier1: {
    title: "Reconciliation & Phase Fixes",
    subtitle: "Low-impact tools to fix UI drift and structural inconsistencies.",
    tools: {
      reconcile: {
        id: "reconcile",
        name: "Reconcile Finished Phases",
        description: "Scans for images stuck in 'running' belonging to jobs that are already finished. Fixes UI badge drift.",
        action: "reconcile",
        limit: 5000,
      },
      fixDb: {
        id: "fixDb",
        name: "Fix DB (Check Health)",
        description: "Performs low-level database integrity checks and minor repairs.",
        action: "check_health",
      }
    }
  },
  tier2: {
    title: "Backfill & Repair",
    subtitle: "Job-based tools that process large sets of images to repair data.",
    tools: {
      fullPipeline: {
        id: "fullPipeline",
        name: "Run Full Pipeline (Missing)",
        description: "Submits all images with missing composite scores to the full Scoring + Tagging pipeline.",
        action: "full_pipeline",
        limit: 1000,
      },
      healThumbnails: {
        id: "healThumbnails",
        name: "Heal Thumbnails",
        description: "Scans for images with missing or broken thumbnail files and regenerates them in the background.",
        action: "heal_thumbnails",
        limit: 500,
      },
      backfillExif: {
        id: "backfillExif",
        name: "Backfill EXIF Dates",
        description: "Re-extracts EXIF metadata for images missing timestamps due to legacy bugs.",
        action: "backfill_exif",
        limit: 1000,
      }
    }
  },
  tier3: {
    title: "Maintenance & Cleanup",
    subtitle: "Maintenance tasks for library management.",
    tools: {
      pruneMissing: {
        id: "pruneMissing",
        name: "Prune Missing Files",
        description: "Removes database records for files that no longer exist on the filesystem.",
        action: "prune_missing",
        limit: 10000,
      },
    }
  }
};
