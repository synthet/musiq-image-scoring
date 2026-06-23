---
type: Research Report
title: Picked-image quality advisory gap (image 195193)
description: Forensics, A/B prompt study, and production fix for agent cull picked_image_advisories returning empty on a misfocus hero pick despite vision evidence.
resource: PICKED_ADVISORY_GAP_195193_2026-06-21.md
tags: [reports, agent-cull-review, culling, vision, misfocus, antigravity, study]
timestamp: 2026-06-21T17:30:00Z
okf_version: 0.1
---

# Picked-image quality advisory gap (image 195193)

Point-in-time research report for stack **#29157** / image **195193** (`DSC_8825.NEF`): high `score_technical` (~0.834) but vision-detectable soft foreground fawn while background deer are sharp.

**Status:** Closed — production default promoted to `picked_quality_audit_snippet_strict_v2.txt`.

**Living harness reference:** [study/agent-cull-cli-matrix.md](../study/agent-cull-cli-matrix.md) (commands, mode profiles, matrix artifacts).

**Raw forensics JSON:** [raw/picked-advisory-forensics-2026-06-21.json](../raw/picked-advisory-forensics-2026-06-21.json)

## Problem

| Signal | Result |
|--------|--------|
| ML `score_technical` | ~0.834 (misleading) |
| Layer 2 vision smoke (Docker Antigravity) | `blur_foreground: true` |
| Full live review (groups 99/100) | `vision_used: true`, **195193 in `viewed_image_ids`**, but **`picked_image_advisories: []`** |

Infrastructure (snippet gating, schema, persist) was correct. The failure was **agent compliance / prompt wording** in the full packet, not wiring.

## Root cause

Isolated advisory smoke on the 195193 thumbnail returns `misfocus` with a populated `picked_image_advisories` array in ~11s. Full-packet runs viewed the same thumbnail but returned an empty advisory list — conservative “return [] when no problem” language and task ordering (rejected decisions dominate) encouraged false negatives on picks.

## Picked set (stack #29157, sub-stack 72253)

| image_id | file_name | score_technical | Notes |
|----------|-----------|-----------------|-------|
| 195201 | DSC_8828.NEF | 0.851 | Highest technical among picks |
| **195193** | **DSC_8825.NEF** | **0.834** | Hero misfocus — soft foreground fawn |
| 195199 | DSC_8829.NEF | 0.824 | Sharper alternative candidate |

## A/B results (Docker Antigravity, 2026-06-21)

Artifacts: `.agent/study/runs/2026-06-21-picked-ab/`

| Stack | Mode | Advisories | 195193 misfocus | FP note |
|-------|------|------------|-----------------|---------|
| 29157 | `technical_focus_strict_picks` | 1 | **yes** | suggests 195201/195199 |
| 29157 | `vision_strict_strict_picks` | 1 | **yes** | same |
| 29160 | both strict modes | 0 | — | clean |
| 29154 | `technical_focus_strict_picks` | 1 | — | ≤1 acceptable |
| 29154 | `vision_strict_strict_picks` | 0 | — | clean |

**Hints (`picked_quality_hints: true`):** watchlist flagged all three picks; **3 advisories** on 29157 — over-flags vs strict_v2 alone. Left **off** in production.

**Two-pass picked-only audit:** pass-2 alone emits 1 advisory on 195193 (~26s). Study-only unless single-pass regresses.

## Production recommendation

| Setting | Value |
|---------|-------|
| `review_picked_quality` | `true` |
| `picked_audit_snippet` | **`picked_quality_audit_snippet_strict_v2.txt`** |
| `picked_quality_hints` | **`false`** |
| `require_vision_evidence` | `true` |
| Misfocus-prone stacks | `--mode-profile technical_focus` or `technical_focus_strict_picks` |

Snippet files: `modules/agent_cull/prompts/picked_quality_audit_snippet*.txt`

Study modes: `technical_focus_strict_picks`, `vision_strict_strict_picks` (see `modules/agent_cull/mode_profiles.py`).

## Operator verification

```bash
docker exec image-scoring-webui env PYTHONPATH=/app python3 \
  /app/scripts/study/agent_cull_matrix.py \
  --output /app/.agent/study/runs/verify-picked-advisory \
  --stacks-file /app/.agent/study/fixtures/misfocus_stack.json \
  --modes technical_focus_strict_picks \
  --live-modes technical_focus_strict_picks \
  --runtimes docker --skip-vision-smoke
```

Success: `picked_image_advisories` contains image **195193** with `issue: misfocus` citing foreground softness.

## Related

- [Agent cull review (Gallery operator)](https://github.com/synthet/image-scoring-gallery/blob/main/docs/guides/04-agent-cull-review.md) — panel UI for `pick_quality_advisory`
- [Agent-assisted cull review — summary](../specs/agent-assisted-cull-review/summary.md)
- [Agent cull review CLI setup](../guides/setup/agent-cull-review-gemini-cli.md)
- [Agent cull CLI study harness](../study/agent-cull-cli-matrix.md)
- [CULLING_FEATURE.md](../technical/CULLING_FEATURE.md)
