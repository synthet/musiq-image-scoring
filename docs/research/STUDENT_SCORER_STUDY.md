---
type: Feature Spec
title: "Vexlum student scorer study"
description: "Can one multi-head student model replace the teacher ensemble at fidelity? Study design, phases, and the shadow-only constraint. Tracked by issue #323."
resource: docs/research/STUDENT_SCORER_STUDY.md
tags: [research, student-scorer, distillation, planning]
timestamp: 2026-07-29T00:00:00Z
okf_version: 0.1
---

# Vexlum Student Scorer Study

Ingested and adapted for [image-scoring-backend](../../). Source research notes:
local Downloads study + architecture survey (background only).

## Objective

Train one multi-task student that accepts the same P0 rendered representation as
the live ensemble and predicts:

1. Per-teacher proxy scores (SPAQ, AVA, LIQE, TOPIQ, ARNIQA — actual fusion membership from Phase 0)
2. Derived `general` / `technical` / `aesthetic` via frozen composite function
3. Uncertainty / teacher-disagreement signal

Behavioral replacement of the ensemble is the goal — not proving superior photographic judgment.
**This program ships shadow evidence only; ensemble replacement is a separate human decision.**

## Important design decision

Do **not** train only against `score_general`. Predict the teacher vector; compute composites
from frozen anchors/weights (`modules/score_normalization.py`).

## Architectures

| Role | Backbone |
|------|----------|
| Primary reference | ConvNeXt-Tiny (E2/E3) |
| Data-efficiency | DINOv2 ViT-S/14 (E4/E5) |
| High ceiling | Swin-Tiny + multi-scale head (E6) |
| Compression (optional) | MobileNetV3 distilled from winner (E8) |

## Package layout

See `scripts/research/student_scorer/` and `docs/research/STUDENT_SCORER_PROTOCOL.md`.

## Execution order

1. Audit + protocol freeze (`audit_dataset.py --contract-only` then full audit)
2. Immutable manifest + splits (`export_manifest.py`)
3. E0/E1 embedding baselines
4. E2–E6 P0 backbone screen
5. Ranking / verified-human ablations
6. P1/P2 input ablations
7. Frozen eval + gates
8. Shadow campaign (`vexlum_student_v1_*`, `is_shadow=true`)

## Safety

- No checkpoints, NEFs, or path-bearing manifests in git (`artifacts/student_scorer/`)
- Never add student names to `scoring.fusion`
- Rollback: set every student proxy to `{enabled:false, shadow:false}`

## See also

- E2 session record (P0 render → train at 2026-08-05 pause): [`SESSION_STUDENT_SCORER_E2_2026-08-05.md`](SESSION_STUDENT_SCORER_E2_2026-08-05.md)
- Dual-arc hub: [`RESEARCH_SESSIONS_2026-08-05.md`](../reports/RESEARCH_SESSIONS_2026-08-05.md)
