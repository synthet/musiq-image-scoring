# Reports — Index

Historical reports, research, reviews, and debugging sessions.

## Work Summaries & Research

| Document | Description |
|----------|-------------|
| [WORK_SUMMARY_2026-03-08.md](WORK_SUMMARY_2026-03-08.md) | Work summary |
| [DEEP_RESEARCH_REPORT.md](DEEP_RESEARCH_REPORT.md) | Deep research report |
| [PARTNER_UPDATES.md](PARTNER_UPDATES.md) | Updates from partner agents |
| [IAA_PAPER_ANALYSIS.md](IAA_PAPER_ANALYSIS.md) | Analysis of modern IAA models paper |
| [IAA_MODELS_LOCAL_DEPLOYMENT.md](IAA_MODELS_LOCAL_DEPLOYMENT.md) | IAA models overview (converted from PDF) |
| [IAA_MODELS_SURVEY_2024_2025.md](IAA_MODELS_SURVEY_2024_2025.md) | 2024–2025 IAA models survey (converted from PDF) |

## Architecture & pipeline notes

| Document | Description |
|----------|-------------|
| [GRADIO_SERVING_DECISION.md](GRADIO_SERVING_DECISION.md) | Why Gradio + FastAPI fits this product; when Triton/BentoML would matter |
| [CULLING_NO_STACKS_INVESTIGATION_2026-03-15.md](CULLING_NO_STACKS_INVESTIGATION_2026-03-15.md) | Culling phase done but no stacks — SelectionRunner phase-order bug (fixed) |
| [RUN_ORCHESTRATION_AUDIT_2026-04-17.md](RUN_ORCHESTRATION_AUDIT_2026-04-17.md) | Run orchestration audit — MUSIQ import regression, dispatcher busy-as-fail, stale `running` rows, path-validation gap, MCP SSE event-loop stalls |
| [CODE_REVIEW_2026-04-15.md](CODE_REVIEW_2026-04-15.md) | Code review of 2026-04-15 commits — job_type stability, MUSIQ imports, indexing log persistence, conflict-marker guard, `a6fdb34` scratch/junk blocker |
| [UI_RUNS_CODE_REVIEW_2026-04-18.md](UI_RUNS_CODE_REVIEW_2026-04-18.md) | Deep review of `/ui/runs` — 30 findings across cancel/pause races, enqueue-vs-phases race, limit=120 active drop, status enum drift, WS perf |

## Project Reviews

| Document | Description |
|----------|-------------|
| [project-reviews/INDEX.md](project-reviews/INDEX.md) | Project review summaries and detailed reviews |
| [project-reviews/UX_UI_REVIEW_2026-03-12.md](project-reviews/UX_UI_REVIEW_2026-03-12.md) | UX/UI heuristic review of current WebUI |
| [CODE_DESIGN_REVIEW_2026-04-18.md](CODE_DESIGN_REVIEW_2026-04-18.md) | Comprehensive code & design review — 3 critical, 5 high, 7 medium findings (execute_code RCE, cancelled/canceled duality, connection leaks, stuck jobs, god object) |
| [SECURITY_FIXES_2026_04_19.md](SECURITY_FIXES_2026_04_19.md) | Security & architecture fixes (RCE mitigation, connection leaks, thread safety, status normalization) |

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
