---
type: Documentation Index
title: Reports index
description: Index of historical reports, research, reviews, and debugging sessions under docs/reports/.
resource: docs/reports/INDEX.md
tags: [docs, reports, index]
timestamp: 2026-07-01T00:00:00Z
okf_version: 0.1
---

# Reports — Index

Historical reports, research, reviews, and debugging sessions.

## Work Summaries & Research

| Document | Description |
|----------|-------------|
| [WORK_SUMMARY_2026-03-08.md](WORK_SUMMARY_2026-03-08.md) | Work summary |
| [WORK_SUMMARY_2026-05-26.md](WORK_SUMMARY_2026-05-26.md) | Auto-drive run 3245 investigation + empty composite scores dry-run |
| [DEEP_RESEARCH_REPORT.md](DEEP_RESEARCH_REPORT.md) | Deep research report |
| [CLIP_MODELS_CULLING_SCORING_2026-05-23.md](CLIP_MODELS_CULLING_SCORING_2026-05-23.md) | CLIP / OpenCLIP / MetaCLIP for culling and prompt-based scoring |
| [CULLING_MODEL_RECOMMENDATION_2026-05-29.md](CULLING_MODEL_RECOMMENDATION_2026-05-29.md) | Model choice for grouping, mishot rejection, and stack selection (post L/14 spike) |
| [CULL_DISTRIBUTION_AUDIT_2026-06.md](CULL_DISTRIBUTION_AUDIT_2026-06.md) | Pick/reject/neutral distribution audit — policy 1.0 vs 2.0, stack/sub-stack invariants |
| [CODEBASE_SIZE_AUDIT_2026-06.md](CODEBASE_SIZE_AUDIT_2026-06.md) | LoC audit snapshot (≥1000 files, ≥150 functions) — backend + gallery; feeds refactor plan |
| [BRANCH_DOCS_SALVAGE_2026-07.md](BRANCH_DOCS_SALVAGE_2026-07.md) | Branch cleanup audit — docs-only gallery branches archived/deleted; UNMERGED code branches retained |
| [PICKED_ADVISORY_GAP_195193_2026-06-21.md](PICKED_ADVISORY_GAP_195193_2026-06-21.md) | Agent cull picked-image advisory gap — forensics, strict_v2 A/B, production defaults |
| [INPUT_SIZE_CULLING_2026-05-29.md](INPUT_SIZE_CULLING_2026-05-29.md) | Thumbnail / long-edge sweep for culling embeddings + IQA signal quality |
| [INPUT_SIZE_CULLING_PRELIMINARY_2026-05-30.md](INPUT_SIZE_CULLING_PRELIMINARY_2026-05-30.md) | Input-size study Phase 0 results, run blockers, future plan (partial run) |
| [AUTO_CULLING_ALGORITHMS_RESEARCH_2026-05-23.md](AUTO_CULLING_ALGORITHMS_RESEARCH_2026-05-23.md) | Image auto-culling algorithms and best practices |
| [PARTNER_UPDATES.md](PARTNER_UPDATES.md) | Updates from partner agents |
| [IAA_PAPER_ANALYSIS.md](IAA_PAPER_ANALYSIS.md) | Analysis of modern IAA models paper |
| [IAA_MODELS_LOCAL_DEPLOYMENT.md](IAA_MODELS_LOCAL_DEPLOYMENT.md) | IAA models overview (converted from PDF) |
| [IAA_MODELS_SURVEY_2024_2025.md](IAA_MODELS_SURVEY_2024_2025.md) | 2024–2025 IAA models survey (converted from PDF) |

## Architecture & pipeline notes

| Document | Description |
|----------|-------------|
| [GRADIO_SERVING_DECISION.md](GRADIO_SERVING_DECISION.md) | Why Gradio + FastAPI fits this product; when Triton/BentoML would matter |
| [CULLING_NO_STACKS_INVESTIGATION_2026-03-15.md](CULLING_NO_STACKS_INVESTIGATION_2026-03-15.md) | Culling phase done but no stacks — SelectionRunner phase-order bug (fixed) |
| [AUTODRIVE_REPROCESSING_INVESTIGATION_2026-05-26.md](AUTODRIVE_REPROCESSING_INVESTIGATION_2026-05-26.md) | Auto-drive false reprocessing (run 3245) — `stale_executor` / executor_version policy |
| [RUN_DATA_GAP_BADGES_FIX_2026-06-30.md](RUN_DATA_GAP_BADGES_FIX_2026-06-30.md) | Misleading "Data gaps" badge on completed runs (run 4555) — hash-based indexing completeness + phase-scoped post-run audit |
| [AUTO_DRIVE_FIX_SUMMARY.md](AUTO_DRIVE_FIX_SUMMARY.md) | Operator summary — fixes for planner version gate + runs_autodrive buckets |
| [AUTODRIVE_REPROCESSING_SUMMARY.md](AUTODRIVE_REPROCESSING_SUMMARY.md) | Short investigation summary (run 3245) — links to fix summary and full RCA |
| [RUN_ORCHESTRATION_AUDIT_2026-04-17.md](RUN_ORCHESTRATION_AUDIT_2026-04-17.md) | Run orchestration audit — MUSIQ import regression, dispatcher busy-as-fail, stale `running` rows, path-validation gap, MCP SSE event-loop stalls |
| [UNIFIED_INPUT_POLICY_2026-05-31.md](UNIFIED_INPUT_POLICY_2026-05-31.md) | Unified input pixel policy across the pipeline (resize / long-edge) |
| [CODE_REVIEW_2026-04-15.md](CODE_REVIEW_2026-04-15.md) | Code review of 2026-04-15 commits — job_type stability, MUSIQ imports, indexing log persistence, conflict-marker guard, `a6fdb34` scratch/junk blocker |
| [UI_RUNS_CODE_REVIEW_2026-04-18.md](UI_RUNS_CODE_REVIEW_2026-04-18.md) | Deep review of `/ui/runs` — 30 findings across cancel/pause races, enqueue-vs-phases race, limit=120 active drop, status enum drift, WS perf |

## Project Reviews

| Document | Description |
|----------|-------------|
| [project-reviews/INDEX.md](project-reviews/INDEX.md) | Project review summaries and detailed reviews |
| [project-reviews/UX_UI_REVIEW_2026-03-12.md](project-reviews/UX_UI_REVIEW_2026-03-12.md) | UX/UI heuristic review of current WebUI |
| [CODE_DESIGN_REVIEW_2026-04-18.md](CODE_DESIGN_REVIEW_2026-04-18.md) | Comprehensive code & design review — 3 critical, 5 high, 7 medium findings (execute_code RCE, cancelled/canceled duality, connection leaks, stuck jobs, god object) |
| [SECURITY_FIXES_2026_04_19.md](SECURITY_FIXES_2026_04_19.md) | Security & architecture fixes (RCE mitigation, connection leaks, thread safety, status normalization) |
| [STATIC_ANALYSIS_2026-05-23.md](STATIC_ANALYSIS_2026-05-23.md) | Static analysis of v7.20.0 (LLM judges, Runs auto-drive, DB Explorer) — 1 critical, 3 high, 5 medium findings; SQL exfiltration, /transaction DDL bypass, loop-guard blind spot |

## Archived point-in-time audits

Superseded or snapshot-only; kept under [`../archive/reports/`](../archive/reports/).

| Document | Description |
|----------|-------------|
| [CODE_DESIGN_REVIEW_legacy.md](../archive/reports/CODE_DESIGN_REVIEW_legacy.md) | Older undated code & design review |
| [2026_02_09_CODE_AND_DESIGN_REVIEW.md](../archive/reports/2026_02_09_CODE_AND_DESIGN_REVIEW.md) | February 2026 review snapshot |
| [RCA_runs_audit_2026-04-22.md](../archive/reports/RCA_runs_audit_2026-04-22.md) | RCA — runs audit (April 2026) |
| [FIX_PLAN_runs_audit_2026-04-22.md](../archive/reports/FIX_PLAN_runs_audit_2026-04-22.md) | Fix plan — runs audit (April 2026) |

## Debugging sessions (historical)

| Document | Description |
|----------|-------------|
| [DEBUGGING_SESSIONS_HUB.md](DEBUGGING_SESSIONS_HUB.md) | Hub — links to archived Gradio/fullscreen incident notes |

**Archive:** [archive/reports/debugging-sessions/](../archive/reports/debugging-sessions/INDEX.md) (full session files).

## Release snapshots (dated)

| Document | Description |
|----------|-------------|
| [RELEASE_HANDOFF_2026-04-10_2026-04-11.md](RELEASE_HANDOFF_2026-04-10_2026-04-11.md) | Cross-repo release handoff (dated snapshot) |

**See also:** [Main docs index](../INDEX.md) · [Plans & proposals](../planning/INDEX.md)
