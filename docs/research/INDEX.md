---
type: Documentation Index
title: Research index
description: Index of active research programs under docs/research/ — study designs, locked protocols, append-only results, and session records.
resource: docs/research/INDEX.md
tags: [docs, research, index, student-scorer]
timestamp: 2026-08-05T21:50:00-05:00
okf_version: 0.1
---

# Research — Index

Active research programs: study design, locked protocol, append-only results, and the session records
that explain how a result was reached. Point-in-time audits and finished investigations live in
[`../reports/`](../reports/INDEX.md) instead.

## Student scorer

Replacing the teacher ensemble (MUSIQ, LIQE, TOPIQ, Q-Align) with one multi-head student model.
**Shadow-only — not wired into fusion.**

| Document | Description |
|----------|-------------|
| [STUDENT_SCORER_STUDY.md](STUDENT_SCORER_STUDY.md) | Program design — ensemble → single multi-head student |
| [STUDENT_SCORER_PROTOCOL.md](STUDENT_SCORER_PROTOCOL.md) | Locked protocol, fidelity gates, commands |
| [STUDENT_SCORER_RESULTS.md](STUDENT_SCORER_RESULTS.md) | **Append-only** run register — failures recorded as failures |
| [STUDENT_SCORER_E2_CHECKPOINT.md](STUDENT_SCORER_E2_CHECKPOINT.md) | E2 human review gate — P0 render cache complete |
| [STUDENT_SCORER_MODEL_CARD.md](STUDENT_SCORER_MODEL_CARD.md) | Model card template for a shadow-ready checkpoint |
| [SESSION_STUDENT_SCORER_E2_2026-08-05.md](SESSION_STUDENT_SCORER_E2_2026-08-05.md) | Session record — render resume fix, 66k P0 cache, ConvNeXt train in flight |

**Status as of 2026-08-05:** E0 and E1 failed all three fidelity gates. The P0 render cache is complete
(66,473 of 66,485 ok). The E2 seed-42 train was still running at last record with no gate outcome.
Tracking issue [#323](https://github.com/synthet/image-scoring-backend/issues/323).

## Related research elsewhere in the wiki

| Document | Description |
|----------|-------------|
| [../reports/RESEARCH_SESSIONS_2026-08-05.md](../reports/RESEARCH_SESSIONS_2026-08-05.md) | Session hub — the 2026-08-05 bird-crop and student-scorer workstreams |
| [../reports/BIRD_BBOX_CROP_STUDY_2026-08-01.md](../reports/BIRD_BBOX_CROP_STUDY_2026-08-01.md) | Bird-bbox crop vs full frame, per pipeline phase |
| [../reports/BIRD_CROP_FOCUS_MEASURES_2026-08-03.md](../reports/BIRD_CROP_FOCUS_MEASURES_2026-08-03.md) | Classical focus measures + camera AF metadata |
| [../reports/CLIP_MODELS_CULLING_SCORING_2026-05-23.md](../reports/CLIP_MODELS_CULLING_SCORING_2026-05-23.md) | CLIP / OpenCLIP / MetaCLIP for culling and prompt scoring |
| [../MODEL_RECOMMENDATIONS_PIPELINES.md](../MODEL_RECOMMENDATIONS_PIPELINES.md) | Canonical pipeline model roadmap |

**See also:** [Main docs index](../INDEX.md) · [Reports index](../reports/INDEX.md) · [Plans & proposals](../planning/INDEX.md)
