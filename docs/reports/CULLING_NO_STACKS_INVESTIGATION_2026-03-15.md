# Culling “Done” but No Stacks (2026-03)

Investigation summary for a folder where every image showed culling phase **done** but **no stacks** (`stack_id` null). The root cause was a phase-status ordering bug in the selection/clustering path, since fixed.

---

## Root cause (fixed)

`SelectionRunner` set culling phase status to **RUNNING** before invoking `ClusteringEngine`. `clustering.py` then evaluated phase policy (`explain_phase_run_decision`), saw **RUNNING**, treated work as already in progress, and **skipped every image**. The runner still marked phases **DONE**, yielding zero stacks and no obvious error.

**Fix:** Do not set **RUNNING** in the runner before clustering; the clustering engine owns RUNNING/DONE transitions for that work.

The `force_rescan` path did not hit this bug because it avoided the premature RUNNING set.

---

## When zero stacks are still valid

Stacks require time-grouped batches, visual similarity under the distance threshold, and **at least two** images per group. A folder of unique shots can correctly finish culling with no stacks.

---

## Operational follow-up

After deploying the fix, affected folders may need **Force Rescan** on culling so images marked done are reprocessed. Optional tuning: `clustering.default_threshold`, `clustering.default_time_gap` in `config.json` (see [CULLING_FEATURE.md](../technical/CULLING_FEATURE.md)).

---

## See also

- [CULLING_FEATURE.md](../technical/CULLING_FEATURE.md)
- [PIPELINE_PHASE_RUNNERS.md](../technical/PIPELINE_PHASE_RUNNERS.md)
