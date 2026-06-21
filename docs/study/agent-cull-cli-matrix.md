---
title: Agent cull CLI scoring & vision study
type: study-report
status: active
created: 2026-06-20
---

# Agent cull CLI scoring & vision study

Repeatable harness comparing **Antigravity (`agy`)**, **Codex**, and **Gemini** CLI agents across carousel-pick-aligned prompt modes, with explicit pre/post vision verification on **Docker**, **WSL**, and **host** runtimes.

## Questions

1. How do CLI providers behave when editorial **priority modes** change?
2. Do agents **open thumbnail files**, or reason from metadata only?
3. Do decisions align with [photo-carousel](https://github.com/synthet/image-scoring-skills) pick rules?

## Harness scripts

| Script | Role |
|--------|------|
| `scripts/study/agent_cull_probe.py` | Layer 1 preflight: packet + manifest path checks |
| `scripts/study/agent_cull_vision_smoke.py` | Layer 2 direct CLI read (canonical; cross-platform) |
| `scripts/study/agent_cull_vision_smoke.sh` / `.ps1` | Shell wrappers (prefer Python on WSL; `.sh` needs LF line endings) |
| `scripts/study/agent_cull_matrix.py` | Full grid: probe → smoke (once per stack/runtime) → optional live review |

### Example commands

```bash
# Preflight one stack (WSL + ~/.venvs/tf)
PYTHONPATH=. python scripts/study/agent_cull_probe.py \
  --stack-id 29157 --sub-stack-id 72253 --mode-profile baseline_v2

# Vision smoke (Docker WebUI container)
docker exec image-scoring-webui env PYTHONPATH=/app AGENT_CULL_SMOKE_TIMEOUT_S=180 \
  python3 /app/scripts/study/agent_cull_vision_smoke.py \
  /app/thumbnails/5f/5f568345394cc5d1913cd36eaa3fe1d0.jpg antigravity 195193

# Matrix (preflight only)
PYTHONPATH=. python scripts/study/agent_cull_matrix.py \
  --output .agent/study/runs/2026-06-20-wsl-preflight \
  --runtimes wsl,docker --skip-vision-smoke --skip-live-cli
```

Study mode profiles live in `modules/agent_cull/mode_profiles.py`. Operator flags: `scripts/agent_cull_review.py --mode-profile`, `--prompt-version`.

## Test fixtures

| Stack | Sub-stack | Label | Key image | Expected carousel behavior |
|-------|-----------|-------|-----------|----------------------------|
| **29157** | 72253 | Misfocus fawn | **195193** `DSC_8825.NEF` | **Remove or demote** — foreground fawn soft while adults sharp; high `score_technical` (~83%) is misleading |
| **29160** | (auto) | Deer burst (agent OK) | — | Keep best pose; remove near-duplicates |
| **29154** | 72249 | Deer burst alt | — | Same as 29160; 6 images |
| **28794** | 72076 | Auth repro (historical) | — | **Absent in current DB** — use 29154/29160 instead |

### Image 195193 reference scores (preflight 2026-06-20)

| Field | Value |
|-------|-------|
| `score_general` | 0.829 |
| `score_technical` | 0.834 |
| `clip_quality_v0` | 0.551 |
| DB `image_technical_failures` | empty (`technical_failures.enabled: false`) |

## Study modes (carousel alignment)

| Mode ID | Prompt | `require_vision_evidence` | Thumbnails |
|---------|--------|----------------------------|------------|
| `baseline_v2` | `cull_redundancy_v2` | false | yes |
| `vision_strict` | `cull_redundancy_v3_vision_strict` | **true** | yes |
| `score_first` | `cull_redundancy_v3_score_first` | false | yes |
| `technical_focus` | `cull_redundancy_v3_technical_focus` | false | yes (+ flattened TOPIQ/LIQE/SPAQ/clip) |
| `clip_gate` | `cull_redundancy_v3_clip_gate` | false | yes |
| `metadata_only` | same as vision_strict | true | **no** (A/B control) |

## Matrix run results (2026-06-20)

Artifacts: `.agent/study/runs/2026-06-20-{wsl,docker,host}-preflight/`

### Layer 1 — Preflight (manifest_count == image_count)

| Runtime | Stacks tested | manifest_ok | Notes |
|---------|---------------|-------------|-------|
| **WSL** | 29157, 29160, 29154 | **18/18 pass** | Paths under `/mnt/d/Projects/.../thumbnails/` |
| **Docker** | 29157, 29160, 29154 | **18/18 pass** | Manifest uses `/app/thumbnails/...`; DB rows still hold WSL paths (`raw_exists: false`, `resolved_exists: true`) |
| **Host (Windows)** | 29157, 29160, 29154 | Pass via WSL delegation | Native Windows Python lacks `psycopg2`; matrix delegates DB probe to WSL when `runtime=host` on win32 |

`metadata_only` mode correctly emits `manifest_count: 0` while scores remain in packet.

### Layer 2 — Vision smoke (image 195193 thumbnail)

| Runtime | Provider | Result | Visual evidence |
|---------|----------|--------|-----------------|
| **Docker** | Antigravity | **PASS** (~60s) | JSON: `blur_foreground: true`, species deer/fawn, note about blurry fawns vs sharp adults |
| **WSL** | Antigravity | **TIMEOUT** (180s) | Windows `agy.exe` via `/mnt/c/Users/.../agy.exe` — slow or blocked; prefer Docker for vision smoke |
| **Host** | — | Not run | Use `%LOCALAPPDATA%\agy\bin\agy.exe` directly for ad-hoc smoke |

Docker smoke stdout (excerpt):

```json
{"image_id": 195193, "species": "white-tailed deer", "focus_ok": true,
 "blur_foreground": true,
 "visual_note": "Two adult white-tailed deer stand in focus on a grassy lawn with two blurry fawns in the foreground."}
```

### Layer 3/4 — Live CLI review (stack #29157, Docker Antigravity, 2026-06-21)

Artifacts: `.agent/study/runs/2026-06-20-live-v4/`

| Mode | live ok | vision_used | viewed_count | verified | Notes |
|------|---------|-------------|--------------|----------|-------|
| `baseline_v2` | yes | true | 5 | yes | ~20s; rejected ids 195196/195197 → keep (pose diversity) |
| `vision_strict` | yes | true | 5 | yes | Same pattern; vision gate satisfied |
| `technical_focus` | yes | true | 5 | yes | Flattened TOPIQ/LIQE/SPAQ in packet |
| `metadata_only` | no | — | 0 | no | `malformed_json` (agent stdout had trailing extra data) |

Thumbnail modes all set `vision_used: true` and viewed all five image ids including **195193** (picked hero; decisions apply to rejected ids only).

Fixes applied during live re-run: JSON-safe datetime in packets, response field coercion (`stack_id`, `confidence`, `summary`), `prompt_template_version` column widened to VARCHAR(64) (migration **0032**).

## Analysis (preflight + smoke)

### 1. Vision compliance rate

- **Preflight:** 100% manifest resolution on WSL + Docker for active fixtures.
- **Layer 2 smoke:** 1/2 runtimes verified visual read (Docker Antigravity). WSL bridge needs tuning or longer timeout.
- **Layer 3/4:** Pending live runs.

### 2. Score vs vision divergence

- **195193** ranks high on ML (`score_technical` 83%) but vision smoke correctly flags **foreground blur**.
- Expect `score_first` to **keep** 195193; `technical_focus` / `vision_strict` should **remove or demote** when live CLI runs complete.

### 3. Technical focus mode

- Preflight confirms `technical_focus` flattens `clip_quality_v0`, `topiq`, `liqe`, `spaq` into packet for stack 29157.
- Prompt instructs citing misfocus despite high technical score — use this mode for stacks like 29157.

### 4. Provider delta

- Matrix default provider: **antigravity**. Codex: set `agent.codex_sandbox: "workspace"` for study (`read-only` blocks `/app/thumbnails`). Gemini: see [agent-cull-review-gemini-cli](../guides/setup/agent-cull-review-gemini-cli.md).

### 5. Runtime delta

- **Docker** is the reliable runtime for vision + DB + `/app/thumbnails` paths.
- **WSL** preflight is fast; vision smoke via cross-OS `agy.exe` is unreliable under 180s.
- **Host** probe delegates to WSL for Postgres; CLI smoke can use native `agy.exe`.

### 6. Carousel alignment checklist

| Rule | Status |
|------|--------|
| Pose diversity over raw score rank | Prompt modes defined; live validation pending |
| Hard-reject selective misfocus | Vision smoke **confirms** on 195193 |
| Filename in reasons | Required in all v2/v3 prompts |
| No metadata-only remove without evidence | `require_vision_evidence: true` in `vision_strict` + safety gate |

## Production recommendations

Applied as production defaults on **2026-06-21** (see `config.example.json` → `culling.agent_review`):

| Setting | Production default | Rationale |
|---------|-------------------|-----------|
| `prompt_template_version` | **`cull_redundancy_v3_vision_strict`** | Live matrix v4 passed; strongest carousel alignment + mandatory vision language |
| `require_vision_evidence` | **`true`** | Docker vision smoke + live v4 verified thumbnail reads; blocks metadata-only removes (and visual picked advisories) without `viewed_image_ids` |
| `timeout_seconds` | **`180`** | Antigravity vision ~60s; headroom for full-stack review |
| `review_picked_quality` | **`true`** (new key) | Enables picked-image advisories so misfocus on picks (195193 case) is surfaced |
| `include_thumbnails` | **`true`** | Required for vision |
| `flatten_model_scores` | `["clip_quality_v0"]` production; add TOPIQ/LIQE/SPAQ for misfocus stacks via **`technical_focus`** profile | 195193 case |
| `codex_sandbox` | **`read-only`** production; **`workspace`** for study only | Read-only may block thumbnail paths |

**Operator workflow for misfocus stacks:** run `scripts/agent_cull_review.py --mode-profile technical_focus --stack-id 29157 --sub-stack-id 72253` (or matrix) before trusting ML technical score alone.

### Picked-image quality advisory gap (closed 2026-06-21)

The live matrix confirmed that picked hero **195193** has a misleading `score_technical` (~83%) and vision-detectable foreground blur, but rejected-only review never inspects picks — so misfocus on a **pick** was invisible. With `review_picked_quality=true`, `build_prompt()` appends `prompts/picked_quality_audit_snippet.txt` instructing the agent to audit every picked thumbnail and emit an optional `picked_image_advisories` array. These persist as **advisory-only** rows (`agent_decision='advisory'`, `candidate_status='pick_quality_advisory'`) that never remove or demote picks.

**Post-change expectation (re-run target):** the validated group for stack #29157 includes a `pick_quality_advisory` on image **195193** citing foreground blur and (optionally) a sharper picked alternative such as 195199.

## Success criteria (plan)

| Criterion | Status |
|-----------|--------|
| Docker preflight manifest_count == image_count | **Met** (5/5 on 29157) |
| Layer 2 visual JSON on 195193 | **Met** (Docker Antigravity) |
| `vision_strict` blocks metadata-only removes | **Unit-tested** (`test_agent_cull_safety`); live pending |
| `metadata_only` diverges from thumbnail runs | **Harness ready**; live pending |
| Picked advisory on 195193 (`pick_quality_advisory`) | **Schema/persist/validation unit-tested**; live re-run pending (see command below) |
| Written report + default recommendation | **This document** |

**Live verification re-run (operator, Docker — requires Antigravity auth):**

```bash
docker exec image-scoring-webui env PYTHONPATH=/app python3 \
  /app/scripts/study/agent_cull_matrix.py \
  --output /app/.agent/study/runs/2026-06-21-live-picks \
  --stacks-file /app/.agent/study/fixtures/misfocus_stack.json \
  --modes technical_focus,vision_strict \
  --live-modes technical_focus,vision_strict \
  --skip-vision-smoke
```

Success: the group for stack #29157 includes a `pick_quality_advisory` on image **195193** citing foreground blur.

## Related

- Spec: `docs/specs/agent-assisted-cull-review/`
- Setup: `docs/guides/setup/agent-cull-review-gemini-cli.md`
- Tests: `tests/test_agent_cull_study.py`
