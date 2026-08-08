---
type: Report
title: "Student scorer E2 — activity checkpoint"
description: "Human review gate before any E2 ConvNeXt GPU train: P0 render cache result for manifest msm_8ef568a5db3d9f79, decode failures, and what must be decided before spending GPU time. Tracked by issue #323."
resource: docs/research/STUDENT_SCORER_E2_CHECKPOINT.md
tags: [research, student-scorer, checkpoint, training]
timestamp: 2026-08-03T00:00:00Z
okf_version: 0.1
---

# Student scorer E2 — activity checkpoint (2026-08-03)

**Repo:** `synthet/image-scoring-backend`  
**Status:** P0 render cache **complete** — human review gate before any E2 GPU train  
**Manifest:** `msm_8ef568a5db3d9f79` · **Protocol:** `ssp_429e3332d8ab`  
**Contract:** [`.agent/scratch/e2_autonomous_run_contract.md`](../../.agent/scratch/e2_autonomous_run_contract.md)

## Summary

The student-scorer program finished Phase 0–2 baselines (E0/E1 MobileNet embeddings **failed** fidelity gates), then built a real P0 image pipeline. The full P0 JPEG cache for the frozen manifest is now done. **Do not start E2 training until this checkpoint is reviewed.**

## Done

### Research package / pipeline code

- Offline package under `scripts/research/student_scorer/` (audit, manifest, E0/E1, evaluators, E2 trainer)
- Shadow runtime scaffold (`modules/student_scoring.py`, proxies) — **not enabled** in production fusion
- [`render_p0.py`](../../scripts/research/student_scorer/render_p0.py): production-mirrored decode tree; BytesIO rawpy; `ThreadPoolExecutor` (default 12 workers); skip only when `existing_method` known (orphans re-decode); `INDEX_FLUSH_EVERY=500` + atomic index write
- [`image_dataset.py`](../../scripts/research/student_scorer/image_dataset.py), [`torch_losses.py`](../../scripts/research/student_scorer/torch_losses.py), real loop in [`train_image_model.py`](../../scripts/research/student_scorer/train_image_model.py)
- Protocol notes (resolved decode methods, BytesIO, derived vs direct composites, frozen `musiq_version: unknown` discrepancy)

### E0/E1 (recorded)

| Run | Val general Spearman | Gates |
|-----|----------------------|-------|
| E0 ridge MobileNet | 0.564 | **FAIL** |
| E1 MLP 1024→256 | 0.601 | **FAIL** |

See [STUDENT_SCORER_RESULTS.md](./STUDENT_SCORER_RESULTS.md).

### P0 render cache (this checkpoint)

| Metric | Value |
|--------|-------|
| `n_index` | **66,485** |
| `ok` | **66,473** |
| `missing_source` | 9 |
| `error` | 3 |
| `rawpy_half` | 30,538 |
| `exiftool:JpgFromRaw` | 35,935 |
| `skipped_existing` | **none** |
| Wall time | ~4,490 s (~75 min), 12 workers |
| Cache | `~/.cache/student_scorer/msm_8ef568a5db3d9f79/p0_512/` (~**2.7 GB**, cap 10 GB) |

Artifacts:

- `artifacts/student_scorer/msm_8ef568a5db3d9f79/renders/render_index.json`
- `artifacts/student_scorer/msm_8ef568a5db3d9f79/renders/render_summary.json`

Failures (enumerated):

- 9× `source_missing`
- 3× `RuntimeError:P0 decode failed` on Z8 paths under `…/2026-04-09/DSC_{0004,0017,0086}.NEF`

## Explicitly not done (blocked on review)

1. E2 smoke: `train_image_model --experiment E2 --epochs 2 --limit 500`
2. Full E2 seed 42 → `artifacts/.../runs/E2_s42/`
3. Append RESULTS + `docs/log.md` with named gate pass/fail
4. Checkpoint export / shadow enablement

## Resume commands (WSL + `~/.venvs/tf`)

```bash
cd /mnt/d/Projects/image-scoring-backend && source ~/.venvs/tf/bin/activate
M=artifacts/student_scorer/msm_8ef568a5db3d9f79

# After review approval only:
python -m scripts.research.student_scorer.train_image_model --manifest-dir $M --experiment E2 --epochs 2 --limit 500
python -m scripts.research.student_scorer.train_image_model --manifest-dir $M --experiment E2 --seed 42
```

## Out of scope for next train pass

E3–E6 · rank/human losses · uncertainty calibration · `export_checkpoint` · shadow · re-split / new `protocol_id`

## See also

> Post-checkpoint train narrative (smoke + full E2 resume at 2026-08-05 pause):
> [`SESSION_STUDENT_SCORER_E2_2026-08-05.md`](SESSION_STUDENT_SCORER_E2_2026-08-05.md).
> Dual-arc hub: [`RESEARCH_SESSIONS_2026-08-05.md`](../reports/RESEARCH_SESSIONS_2026-08-05.md).
