# Student Scorer Results

Append-only by run ID. Record failures and abandoned runs, not only winners.

| Run ID | Experiment | Manifest | Protocol | Val summary | Gates | Notes |
|--------|------------|----------|----------|-------------|-------|-------|
| `2026-07-30-e0-mobilenet` | E0 ridge | `msm_8ef568a5db3d9f79` | `ssp_429e3332d8ab` | general Spearman 0.564; median teacher Spearman 0.540; nonsat MAE 0.118 | **FAIL** all three fidelity gates | MobileNet 1280-d; 66,070/66,485 overlap (99.4%); full-target also fail |
| `2026-07-30-e1-mobilenet` | E1 MLP 1024→256 | `msm_8ef568a5db3d9f79` | `ssp_429e3332d8ab` | general Spearman 0.601; median teacher Spearman 0.450; nonsat MAE 0.115 | **FAIL** all three fidelity gates | Early-stop epoch 13; test general Spearman 0.678; OOD 0.480 — embedding heads insufficient; proceed to E2 |

## How to append

Copy the fidelity / culling JSON from `artifacts/student_scorer/<manifest_id>/...`
into a dated subsection below. Never edit prior rows in place — add a superseding run.

---

## 2026-07-30 — E0/E1 MobileNet baselines

**Space:** `mobilenet_v2_imagenet_gap` (1280-d)  
**NPZ:** `artifacts/student_scorer/msm_8ef568a5db3d9f79/embeddings/mobilenet_v2_imagenet_gap.npz`  
**Coverage:** 66,070 with embedding / 415 missing / full-target rows in NPZ: 56,221  
**Selection:** val only (`n=4426`); test/OOD report-only

### E0 (ridge)

| Head | Spearman | MAE | n |
|------|----------|-----|---|
| general | 0.564 | 0.118 | 4426 |
| technical | 0.599 | 0.107 | 4426 |
| aesthetic | 0.423 | 0.145 | 4426 |
| arniqa | 0.578 | 0.031 | 4426 |
| ava | 0.536 | 0.035 | 4426 |
| liqe | 0.543 | 0.112 | 4426 |
| spaq | 0.363 | 0.104 | 4426 |
| topiq | 0.540 | 0.044 | 4426 |

Gates failed: composite Spearman (≥0.95), median teacher Spearman (≥0.90), nonsaturated MAE (≤0.03).

### E1 (MLP)

| Head | Spearman | MAE | n |
|------|----------|-----|---|
| general | 0.601 | 0.116 | 4426 |
| technical | 0.623 | 0.100 | 4426 |
| aesthetic | 0.425 | 0.138 | 4426 |
| arniqa | 0.391 | 0.043 | 4426 |
| ava | 0.450 | 0.037 | 4426 |
| liqe | 0.602 | 0.109 | 4426 |
| spaq | 0.383 | 0.100 | 4426 |
| topiq | 0.508 | 0.048 | 4426 |

Same three gates failed. Stored MobileNet features approximate the ensemble only moderately; **backbone fine-tuning (E2 ConvNeXt) is required.**

Artifacts: `artifacts/student_scorer/msm_8ef568a5db3d9f79/baselines/E0|E1/report.json`
