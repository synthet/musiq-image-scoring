# Backup Feature — Review, Defects & Fix Plan

**Date:** 2026-06-08
**Author:** review pass (Claude)
**Scope:** `image-scoring-gallery` (Electron backup pipeline) + `image-scoring-backend` (`/api/backup/plan`, `modules/backup_plan.py`)
**Trigger:** Post-incident review of the "Backup feature optimization" work captured in
`cursor_backup_feature_optimization.md`, where a backup run to `H:\Photos` deleted ~37,000 files
(manifest dropped from 40,164 → 2,950 entries).

> **Status (updated 2026-06-08):** Phases 0, 1, 2, 4D, 4F **implemented** (see Progress log
> below). Phases 3, 4E, 5 remain — 3 needs a maintainer decision.

### Progress log

| Item | Status | Notes |
|------|--------|-------|
| Bonus: f-string `SyntaxError` (`backup_plan.py:166`) | ✅ Done | Hard import failure on Python 3.11 → endpoint 500. Extracted strip out of f-string. |
| Finding A — null-stack collapse | ✅ Done | Fixed in gallery `applyStackPrefilter` + backend `_stack_prefilter`; unstacked images kept as singletons. Tests added both repos. |
| Phase 0 — lock safe defaults | ✅ Done | Already asserted by `backupConfig.test.ts` (both prune flags `false`, `minScore 0.5`). |
| Finding B — `pruneDroppedForSpace` ungated | ✅ Done | Space-drop deletions now in preview (`wouldDeleteDroppedForSpace`) + confirm gate; only deletes copies already on disk. |
| Run gate ordering | ✅ Done | All destructive confirmation gates evaluated **before** any unlink (no partial-mutation-then-throw). |
| Finding D — backend giant self-join | ✅ Done | `_similar_pairs_in_group` now batches by `pair_batch_size` with cross-batch combine + dedup. Tests added. |
| Finding F — non-atomic manifest write | ✅ Done | `writeManifestAtomic` (tmp + fsync + `.bak` rotate + rename). |
| Finding E — double plan build / TOCTOU | ✅ Mostly | Gate-before-mutation done; preview now uses a **lightweight fast path** (no dedup) when not pruning, so it no longer double-builds the heavy plan or blocks the modal. |
| Finding C / Phase 3 — single source of truth | ✅ Done | **Decision: gallery-only.** Removed `modules/backup_plan.py`, `tests/test_backup_plan.py`, the `BackupPlanRequest` model + `POST /api/backup/plan` endpoint, and the gallery's `fetchBackupPlan`/`fetchBackendBackupPlan` wiring. Single TS implementation now. |
| Finding I — dead dedup progress | ✅ Done | `buildBackupPlan` forwards `onDedupProgress`; run handler emits the `deduplicating` phase. |
| Preview hang | ✅ Done | Pre-flight fast path counts candidates via `countScoredImagesForBackup` and defers the exact plan to run time (shown as "computed during backup"). Heavy plan only built when a prune flag is enabled (needs accurate delete counts). |
| Findings G/H — polish | ⏳ Open | Backend `reason` parity is moot now (endpoint removed); cross-day week math still approximate (off by default). |

**Verification:** backend `pytest tests/test_backup_plan.py` → 9 passed, ruff clean; gallery
`tsc` (electron+node) exit 0, 4 backup vitest suites → 41 passed. (App-tsconfig has 14
pre-existing, unrelated errors in non-backup files.)

---

## 1. Background

The feature was reworked in three phases to back up "the most diverse, unique and highly scored"
images instead of everything:

- **Phase 1** — score floor (`minScore`), `capture_date` grouping, per-stack pre-filter, batched
  pgvector pair queries.
- **Phase 2** — MMR diversity selection, multi-keep clusters, proportional disk budgeting.
- **Phase 3** — backend `POST /api/backup/plan` as a "single source of truth", with the gallery
  falling back to local TypeScript logic when the API is down.

Mid-rollout, a run mass-deleted the destination. A follow-up fix made pruning **additive by
default** (`pruneStaleFiles: false`), added a `backup:preview` confirm gate, and lowered `minScore`
to `0.5`.

### What actually caused the mass deletion (root cause, confirmed)

The **previous** implementation (`HEAD:electron/main.ts`):

- Called `db.getAllScoredImagesForBackup()` with **no score floor** → backed up *all* scored images.
- Called `removeStaleBackupFiles(...)` **unconditionally** → mirror-prune was always on.

Because the old plan ≈ "all scored images", the stale set was small, so mirror-prune was harmless
in practice. The new plan is far more selective (score floor + stack pre-filter + embedding dedup),
so it collapsed ~40k previously-backed-up files into ~2.95k. With mirror-prune still on-by-default,
the ~37k now-"stale" entries were deleted. **The layout (`camera/lens/year/date`) did not change**,
so this was a selection-vs-prune interaction, not a path-mismatch.

The additive-default fix correctly neutralises the *deletion*. **But the selection is still far more
aggressive than intended** — and one cause is an outright bug (see Finding A).

---

## 2. Findings

| # | Severity | Area | Issue |
|---|----------|------|-------|
| A | **High (correctness)** | gallery `backupSelection.ts` + backend `backup_plan.py` | Stack pre-filter buckets **all `stack_id = NULL` images on a date into one "stack" and keeps only 2** — discards 90%+ of distinct unstacked photos |
| B | High (data-loss latent) | gallery `main.ts` | `pruneDroppedForSpace` deletes dropped-for-space destination files with **no confirm gate** and no preview accounting |
| C | Medium | both | Two divergent implementations of the same algorithm (TS + Python) already differ (batching, param handling); guaranteed to drift |
| D | Medium (perf/robustness) | backend `backup_plan.py` | `_similar_pairs_in_group` ignores `pair_batch_size` and issues one giant self-join (`IN (N)` twice) — can be very slow / time out on large date groups, silently disabling dedup for that day |
| E | Medium | gallery preview/run | Preview and run build the plan **twice** (double pgvector cost) and can disagree (TOCTOU): confirm gate is based on the preview snapshot, run re-derives a possibly larger deletion |
| F | Medium (durability) | gallery `main.ts` | Manifest is rewritten non-atomically (`writeFile`), no temp+rename, no rotation — a crash mid-write corrupts the only record of what is backed up |
| G | Low | backend confirm parity | Backend `score`/`reason` only ever returns `"selected"`; preview `wouldDeleteFiles` excludes prebuild (`id===0`) while a confirmed run deletes them too (undercount) |
| H | Low | gallery cross-day dedup | `crossDayBucketKey` ISO week math is ad-hoc/approximate; only matters when `crossDayDedup: true` (off by default) |
| I | Low (clarity) | gallery progress | `deduplicating` phase label exists but is never emitted; progress `n/total` during dedup is group-index, not images |

### Finding A — Null-stack bucket collapse (primary selection defect)

`applyStackPrefilter` (gallery) and `_stack_prefilter` (backend) group a date's images by `stack_id`,
mapping `NULL → 'none'` (TS) / `None` key (Python), then keep only the top `2` per bucket:

```ts
const key = img.stack_id ?? 'none';   // ALL unstacked images share one bucket
...
dedupeCandidates.push(...sorted.slice(0, maxKeepPerStack)); // keep 2, reject rest
```

Unstacked images are precisely the ones the culling phase did **not** find near-duplicates for —
they are distinct photos and must not be treated as one giant burst.

**Measured impact (live DB, this repo):**

- 62,976 scored images; **17,676 (28%) have `stack_id IS NULL`**.
- Of `score_general ≥ 0.7`: 5,472 are unstacked across 272 dates.
- After the null-bucket prefilter: **only 503 survive — 4,969 (91%) wrongly rejected.**

This alone explains most of the gap between the user's expectation and the 2,950 result, independent
of the deletion bug.

**Fix:** never bucket unstacked images together. Treat each `stack_id = NULL` image as its own
singleton (no stack-based rejection); only apply the top-2 keep to rows that share a real `stack_id`.

### Finding B — `pruneDroppedForSpace` ungated deletion

In `main.ts` (~1461) when `pruneDroppedForSpace: true`, every `droppedRelPaths` entry is `unlink`ed
and pruned from the manifest with no confirmation and no inclusion in the preview's `wouldDeleteFiles`
/ `requiresConfirm`. On an almost-full disk (the exact incident condition) `droppedForSpace` can be
large. This is a second, independent mass-deletion path that bypasses the new safety gate.

**Fix:** fold space-drop deletions into the same preview + confirm accounting as stale prune, or keep
it strictly additive (recommended default) and only ever delete dropped files behind the confirm gate.

---

## 3. Fix Plan (phased, ordered)

### Phase 0 — Stabilise defaults (ship immediately, lowest risk)

1. Confirm shipped safe defaults remain: `pruneStaleFiles: false`, `pruneDroppedForSpace: false`
   (`backupConfig.ts`). ✔ already in place — add a regression test asserting the defaults so they
   can't silently regress.
2. Document in `docs/architecture/backup-feature.md` that **both** prune flags are destructive and
   gated.

### Phase 1 — Fix the selection bug (Finding A) — highest value

Repos: gallery + backend (keep parity).

3. **gallery `applyStackPrefilter`**: change bucketing so `stack_id == null` rows are emitted as
   singletons (each its own bucket / pushed straight to `dedupeCandidates`), never trimmed against
   each other. Only real shared `stack_id` groups get the top-`maxKeep` trim.
4. **backend `_stack_prefilter`**: mirror the same fix (skip the `None` key from the top-2 trim).
5. Add unit tests in both repos covering: (a) many null-stack rows on one date all survive; (b) a
   real stack of N>2 keeps exactly 2. (The current `test_stack_prefilter_keeps_top_two` only covers
   shared `stack_id`.)
6. Re-measure expected plan size against the live DB after the fix (target: unstacked high-score
   images are retained subject to embedding dedup + disk budget, not the stack trim).

### Phase 2 — Close the second deletion path (Finding B)

Repo: gallery.

7. Route `pruneDroppedForSpace` deletions through the preview/confirm machinery: include them in
   `wouldDeleteFiles` and `requiresStaleDeleteConfirmation`, or hard-gate behind `confirmMassDelete`.
8. Surface `droppedForSpace` deletions distinctly in `BackupModal` post-run panel (already partially
   present) and in the **pre-flight** preview when the flag is on.

### Phase 3 — Single source of truth / reduce drift (Finding C)

9. Decide the contract: either (a) backend `/api/backup/plan` is authoritative and the gallery local
   path is a thin emergency fallback that is explicitly flagged in warnings, or (b) drop the backend
   endpoint and keep gallery-only. Given the incident and cross-repo cost, recommend **(a)** but make
   the gallery surface "used local fallback" in the result warnings so divergence is visible.
10. Add a shared fixture / golden test: same input rows → assert gallery and backend produce the same
    selected ID set (lock parity for stack pre-filter, threshold curve, MMR keep count).

### Phase 4 — Robustness & durability (Findings D, E, F)

11. **D:** make backend `_similar_pairs_in_group` batch IDs like the gallery (`pair_batch_size`),
    or cap group size and emit a warning; never let a slow/failed similarity query silently disable
    dedup without it showing in `warnings`.
12. **E:** compute the plan once and reuse it for preview → run (cache keyed on target + config +
    candidate snapshot), or at minimum re-validate `wouldDeleteFiles` at run time and re-prompt if it
    materially exceeds the previewed/confirmed number.
13. **F:** atomic manifest write — write `manifest.json.tmp`, `fsync`, rename over `manifest.json`,
    and rotate a single `.bak`. This also makes the existing `audit-backup-manifest-diff.mjs`
    recovery flow reliable.

### Phase 5 — Polish (Findings G, H, I)

14. Backend: return real per-item `reason` (e.g. `stack`, `cluster`, `score`) for parity with future
    UI; align prebuild accounting between preview and run.
15. Gallery: fix or gate the cross-day week bucketing; emit the `deduplicating` phase or remove the
    dead label; clarify the dedup progress denominator in the UI/tooltip.

---

## 4. Files / areas to touch

**Gallery (`image-scoring-gallery`):**
- `electron/backupSelection.ts` — Finding A (stack pre-filter)
- `electron/main.ts` — Findings B, E, F (run handler, preview, manifest write)
- `electron/backupConfig.ts` — Phase 0 default-lock test target
- `electron/backupSpace.ts` — Finding B accounting
- `src/components/Backup/BackupModal.tsx` — Findings B, E (pre-flight surfacing)
- tests: `backupSelection.test.ts`, `backupSpace.test.ts`, `backupConfig.test.ts`

**Backend (`image-scoring-backend`):**
- `modules/backup_plan.py` — Findings A, D, G
- `modules/api.py` — Finding G (response shape, if changed)
- `tests/test_backup_plan.py` — extend null-stack + parity coverage

---

## 5. Tests

- **Backend:** `python -m pytest tests/test_backup_plan.py -v`
  (add: null-stack survival, real-stack top-2, batched similarity, parity golden set).
- **Gallery:** `npm test` for `backup*` suites; `npx tsc --noEmit` clean.
- **Manual / data check:** re-run the live-DB measurement query (Section 2A) after the Phase 1 fix to
  confirm unstacked high-score images are no longer mass-rejected.
- **Safety regression:** assert default config has both prune flags `false`; assert a run with a
  drastically smaller plan does **not** delete files unless `pruneStaleFiles && confirmMassDelete`.

## 6. Rollback / flags

- All destructive behaviour stays behind `backup.pruneStaleFiles` / `backup.pruneDroppedForSpace`
  (default `false`) + UI confirm. Phase 1/2 changes only **expand** what is retained, so rollback is
  reverting the diff; no data migration.
- Backend endpoint is optional (gallery falls back); the parity fix can ship backend-first or
  gallery-first without a lockstep release, but Phase 1 should land in **both** to avoid the fallback
  path reintroducing the null-stack collapse.

## 7. Open questions (for maintainer)

1. **Intended `minScore`?** `0.5` (current) keeps ~49.7k images; `0.7` keeps ~24.4k. Which is the
   product target now that the null-stack bug is separated out?
2. **`maxPerCluster` intent** for genuinely unstacked images — confirm they should bypass the cluster
   keep entirely (recommended) vs. be eligible for embedding-dedup only.
3. **Keep the backend endpoint?** Confirm Phase 3 direction (authoritative backend vs gallery-only)
   before investing in parity tests.
4. **Recovery for `H:\Photos`:** source library copies still exist; re-running additively re-copies,
   but the disk is near-full — selection quality (Phase 1) matters before any re-run.
