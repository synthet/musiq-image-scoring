---
type: Technical Reference
title: "Student scorer protocol"
description: "Frozen evaluation protocol for the student-scorer study — splits, fidelity gates, and the rule that evaluator changes never ship in the same commit that claims a metric win. Lock protocol_id after Phase 0 review."
resource: docs/research/STUDENT_SCORER_PROTOCOL.md
tags: [research, student-scorer, protocol, evaluation]
timestamp: 2026-07-29T00:00:00Z
okf_version: 0.1
---

# Student Scorer Protocol

**Status:** Draft freeze template — lock `protocol_id` after Phase 0 review; do not change
evaluator rules in the same change that claims a metric win.

## Scoring contract (resolve at Phase 0)

- Teachers = membership of `scoring.fusion` (example: spaq, ava, liqe, topiq, arniqa)
- Anchors = `percentile_anchors` / defaults in `modules/score_normalization.py`
- Rounding = 4 decimal places on composites; missing heads renormalize
- P0 preprocess = `MultiModelMUSIQ.preprocess_image` fingerprint (method, max_resolution, jpeg_quality, source hash)

## Provenance

| Field | Use |
|-------|-----|
| Teacher normalized | Primary distillation |
| Stored composites | B0 parity + consistency loss |
| Rating / pick | Human loss **only** if source ∈ {human, user, manual, …} |
| Auto rating / cull | Weak / exclude from human gates |

## Splits

Connected components: hash → burst → sub_stack → stack → session(folder+day).
Carve newest sessions as `ood_test` before IID 75/12.5/12.5. Near-dupe leakage forces rebuild.

## Gates (initial — revise after audit)

| Gate | Threshold |
|------|-----------|
| Composite Spearman (IID) | ≥ 0.95 |
| Median teacher Spearman | ≥ 0.90 |
| Non-saturated composite MAE | ≤ 0.03 |
| Confident within-stack pairs | ≥ 95% @ margin 0.04 |
| Subgroup Spearman drop | ≲ 0.05 |
| End-to-end speedup | ≥ 3× ensemble |
| Human top-frame | non-inferiority (margin frozen after Phase 0) |

Selection uses **val only**. Test / OOD are report-only.

## Commands

```bash
python -m scripts.research.student_scorer.audit_dataset --contract-only
python -m scripts.research.student_scorer.audit_dataset --out artifacts/student_scorer/audit.json
python -m scripts.research.student_scorer.export_manifest --audit artifacts/student_scorer/audit.json
python -m scripts.research.student_scorer.train_embedding_head --manifest-dir ... --embeddings-npz ... --experiment E1
# P0 render cache (WSL + ~/.venvs/tf; paths under /mnt/d/Photos are valid)
python -m scripts.research.student_scorer.render_p0 --manifest-dir artifacts/student_scorer/msm_8ef568a5db3d9f79 --workers 10
python -m scripts.research.student_scorer.train_image_model --manifest-dir ... --experiment E2 --dry-build-only
python -m scripts.research.student_scorer.train_image_model --manifest-dir ... --experiment E2 --seed 42
python -m scripts.research.student_scorer.export_checkpoint --manifest-dir ...
```

Shadow campaign: set each `vexlum_student_v1_*` to `{enabled:false, shadow:true}`, set
`scoring.student.bundle_dir`, ensure proxies registered via `ensure_student_proxies_registered`.

## P0 decode (resolved method)

The frozen manifest field `preprocessing.raw_conversion_method` is the **configured preference**
(`rawpy_half`), not the per-image outcome. Production `MultiModelMUSIQ.preprocess_image` gates
Nikon HE / Z8–Z9 compressed NEFs off rawpy and falls back to exiftool embedded JPEG.

| Camera family | Typical compression | Resolved P0 decode |
|---------------|---------------------|--------------------|
| Z8 (~54% of corpus) | High Efficiency* | `exiftool:JpgFromRaw` (or Preview/Other/Thumbnail) |
| Z6ii | Lossless | `rawpy_half` |
| D90 / D300 | Lossy (type 2) | `rawpy_half` |

`render_p0` records `resolved_method` per image in `renders/render_index.json` for reliability /
subgroup slices. Under WSL, rawpy is fed from `BytesIO(open(path,"rb").read())` so libraw avoids
pathological 9p small reads; output must stay byte-identical to path-based production preprocess
(enforced by `tests/test_student_scorer_render_p0.py`).

## Frozen-contract discrepancies (do not "fix" in place)

- `manifest.meta.json` may record `preprocessing.musiq_version: "unknown"` while
  `MultiModelMUSIQ.VERSION == "5.0.0"`. Correcting it changes `contract_hash` / `protocol_id` and
  invalidates prior baselines — leave frozen; treat as documentation debt only.
- **Derived vs direct composites:** E0/E1 reported direct aux heads. Image students (E2+) report
  **both**; fidelity **gates** bind to composites **derived** from predicted teacher heads via the
  frozen fusion/anchors. Direct `general`/`technical`/`aesthetic` heads remain auxiliary (and are
  reported for E0/E1 comparability only).

## Autonomous runs

Before unattended train/sweep, write an autonomous-run-contract (metric, budget, revert, stop).
