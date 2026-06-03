# #185 — Calibration layer + percentile anchors: status & blockers

**Issue:** [#185](https://github.com/synthet/image-scoring-backend/issues/185) — *scoring stack: calibration layer + percentile anchors for new models* (sub-task of #180; dep: #184).
**Status:** Partially done; remaining work is **data-blocked**. Captured here so the issue can be moved to `Blocked` with a concrete unblock path.
**Last assessed:** 2026-05-23.

**Validation plan (gates, scripts, promotion criteria):** [QPT_V2_VALIDATION_GATES.md](QPT_V2_VALIDATION_GATES.md)

## What #185 asks for

1. Add empirical percentile anchors (`p02`/`p98`) for `qpt_v2` and `topiq` to
   `DEFAULT_PERCENTILE_ANCHORS` in [`modules/score_normalization.py`](../../../modules/score_normalization.py),
   computed from shadow scores over the corpus.
2. Implement the calibration layer from the proposal
   [§"Add a calibration layer"](IQA_MODEL_STACK_UPDATE_PROPOSAL.md) — z-score /
   percentile, optional isotonic/logistic — so raw outputs are comparable before fusion.

## Current state

| Deliverable | State | Notes |
|-------------|-------|-------|
| `topiq` percentile anchors | ✅ Done | `score_normalization.py:29` → `{p02: 0.390, p98: 0.709}` (also in `config.json` `percentile_anchors`). |
| `qpt_v2` percentile anchors | ⛔ Blocked | See Blocker A. |
| Calibration method: **percentile** | ✅ Done | `rescale_percentile()` (`score_normalization.py:124`), config-overridable via `percentile_anchors`. |
| Calibration method: **z-score** | ⛔ Blocked | Mechanism not built; params need a corpus. See Blocker B. |
| Calibration method: **isotonic / logistic** | ⛔ Blocked | Optional in the proposal. See Blocker C. |

## Blockers

### A. `qpt_v2` inference now runs locally — but scores are unvalidated
**Update (2026-05-23):** inference is no longer fully blocked. Upstream inference code is
still an open TODO ([KeiChiTse/QPT-V2](https://github.com/KeiChiTse/QPT-V2)), but we now
reconstruct the HiViT-T architecture locally in `modules/qpt_v2_arch.py` from the published
`iqa.pth` state dict — it strict-loads all 172 tensors, and `QptV2Scorer.available` becomes
`True` once `iqa.pth` is placed at `scoring.qpt_v2.checkpoint_path` (default
`models/qpt_v2.pth`, git-ignored). Verified on sample images: scores are produced and are
directionally sensitive to quality (Gaussian blur lowers them in every test case).

Two residual problems remain before calibration is meaningful:
1. **Recipe fidelity (accuracy risk).** The upstream inference recipe (preprocessing/crop,
   token pooling, patch-merge order) is undocumented. Our reconstruction produces a
   compressed range (~`[-0.25, 0]`, *not* 0–1) and mixed behavior on JPEG degradation — the
   same "not satisfactory" symptom reported in
   [QPT-V2 issue #2](https://github.com/KeiChiTse/QPT-V2/issues/2). Scores must be validated
   against a labelled IQA set (e.g. Spearman vs MOS) before trusting them.
2. **No corpus scores yet.** Empirical `p02`/`p98` need a population of scores in
   `image_model_scores`; computing them requires a scoring pass over the
   corpus, which needs the DB (see Blocker B).

#### Validation attempts (2026-05-24, 20–30 sample thumbnails)

Offline checks (no labelled set / corpus available — thumbnails are a weak substrate):

| Check | Result | Read |
|-------|--------|------|
| Graded blur monotonicity (σ 0→4), squash-resize | mean Spearman **−0.66** | correct sign, weak |
| Same, **resize-short-256 + center-crop** (now the default) | mean Spearman **−0.81** | better — preprocessing matters; adopted |
| QPT-V2 vs NIQE (same images) | Spearman **+0.36** (p≈0.05) | **wrong sign**, weak — NIQE unreliable on thumbnails, but not reassuring |

**Read:** the reconstruction is structurally exact (172/172 tensors) and directionally
sensitive to blur, but does **not** yet track quality reliably (target blur-Spearman ≤ −0.9;
NIQE cross-check wrong sign). Center-crop preprocessing was adopted (`QptV2Scorer._preprocess`)
as it both follows the standard eval recipe and measurably helps. Remaining gap is likely
further recipe details (token pooling, exact crop/resolution) and/or the thumbnail substrate.
**Do not trust scores yet; QPT V2 is fully disabled (unregistered).** Next: validate on full-resolution images
against a labelled MOS set, or recover the upstream recipe.

**Unblocks when:** (a) the reconstruction is validated against a labelled set (or upstream
ships the real recipe), and (b) a shadow-scoring pass populates `image_model_scores`, after
which anchors can be computed and the raw range mapped to 0–1.

#### Recovered architecture (from `iqa.pth`, 2026-05-23)

The checkpoint is self-describing — `torch.load(...)['params']` is a complete 18.9M-param
state dict. A local re-implementation no longer needs the unreleased upstream code; the
exact structure is:

- **Stem** `patch_embed`: `Conv2d(3→96, k=4, s=4)` + `LayerNorm(96)` → 56×56×96 from a 224² input.
- **Stage 1** `blocks.0–1`: FFN-only blocks (`x = x + mlp(norm2(x))`, no attention),
  dim 96, MLP ratio 3.0.
- **PatchMerge** `blocks.2`: `LayerNorm(384)` + `Linear(384→192, bias=False)`, 56²→28².
- **Stage 2** `blocks.3–4`: FFN-only, dim 192, MLP ratio 3.0.
- **PatchMerge** `blocks.5`: `LayerNorm(768)` + `Linear(768→384, bias=False)`, 28²→14²(=196).
- **+`absolute_pos_embed`** `(1, 196, 384)` added at stage 3.
- **Stage 3** `blocks.6–15` (10 blocks): full transformer (`norm1`+attn, `norm2`+mlp),
  dim 384, **6 heads**, MLP ratio 4.0, relative position bias table `(729=27², 6)` indexed
  by `relative_position_index (196, 196)`; `qkv` has bias.
- **Head**: `norm` `LayerNorm(384)` → mean-pool over 196 tokens →
  `quality_regressor.fc_cls = Linear(384→64) → GELU → Dropout → Linear(64→1)` → scalar.

**Residual uncertainty (issue #2):** the patch-merge neighbor ordering, attention rel-pos
detail, and especially the inference-time preprocessing (resize/crop/normalization, fixed
224² vs native) are not documented, and a community attempt got "not satisfactory" results.
The architecture is reproducible; matching the paper's *accuracy* is not guaranteed.
Treat any locally-produced scores as provisional until validated against a labelled set.

### B. z-score params need a held-out corpus, and the corpus DB is unreachable
z-score normalization needs per-model mean/std computed over the corpus. Neither
exists yet, and the database is not reachable from the Windows host:
- `database.engine = postgres`, but `localhost:5432` **timed out** (Docker Postgres
  not running, or only reachable from WSL).

**Unblocks when:** the Postgres corpus is online (typically from WSL). Then per-model
mean/std can be derived with the existing tooling
([`scripts/analysis/model_score_quality_report.py`](../../../scripts/analysis/model_score_quality_report.py),
currently untracked) which already pulls normalized 0–1 scores and computes
distribution stats.

### C. isotonic / logistic calibration needs human preference labels
Marked "optional" in the proposal. Requires labelled human-preference pairs/rankings,
which we do not collect today. No action until a labelling source exists.

## Proposed approach (once unblocked)

When the corpus DB is reachable, implement the calibration layer as a **pluggable
dispatcher** in `score_normalization.py` rather than hardcoding one method:

- Config key `calibration.method`: `"percentile"` (default — current behavior, zero
  change) | `"zscore"`.
- `calibrate_score(model, score)` dispatches; percentile path keeps using
  `DEFAULT_PERCENTILE_ANCHORS` / `percentile_anchors`.
- z-score path reads `DEFAULT_ZSCORE_PARAMS = {model: {mean, std}}` (config-overridable
  via `zscore_params`), squashed to `[0,1]` (e.g. clamp at ±2σ then linear, or logistic).
- `rescale_scores()` routes through the dispatcher so `compute_composites()` is unchanged.
- Per the proposal's module layout, this can later move under a `calibration/` package.

This keeps percentile as the default (no behavior change) and lets z-score be adopted
per-config once real params are computed. The mechanism itself is unit-testable with
synthetic data ahead of having corpus params — that is the first chunk of work to pick
up when the team decides to proceed despite the empirical-params blocker.

## Related files

- [`modules/score_normalization.py`](../../../modules/score_normalization.py) — anchors, percentile rescaling, composites.
- [`modules/qpt_v2.py`](../../../modules/qpt_v2.py) — QPT V2 scorer (not registered in live pipeline).
- [`modules/engines/qpt_v2_model.py`](../../../modules/engines/qpt_v2_model.py) — registry adapter (register when #185 unblocks).
- `scripts/analysis/model_score_quality_report.py` — corpus distribution/correlation report (anchor source).
- `scripts/analysis/recalc_composite_scores.py` — recompute composites from stored scores using current anchors.
- [`docs/technical/MODELS_SUMMARY.md`](../../technical/MODELS_SUMMARY.md), [`docs/technical/MULTI_MODEL_SCORING.md`](../../technical/MULTI_MODEL_SCORING.md) — live model status.
