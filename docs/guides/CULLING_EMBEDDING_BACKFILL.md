# Backfill plan — optional culling embedding spaces

> **Status:** Operational runbook / plan (executable).
> **Date:** 2026-05-30.
> **Owner:** backend.
> **Related:** [two-level-culling.md](../features/planned/embeddings/two-level-culling.md) ·
> [CULLING_MODEL_RECOMMENDATION_2026-05-29.md](../reports/CULLING_MODEL_RECOMMENDATION_2026-05-29.md) ·
> [EMBEDDINGS.md](../technical/EMBEDDINGS.md) · [#220](https://github.com/synthet/image-scoring-backend/issues/220)

## Goal

Populate `image_embeddings_768` with **`openclip_l14_laion2b_image`** vectors for the full
production library so two-level culling can sub-stack on the validated-best tower, then
**enable** `culling.two_level`. "Done" =

1. every eligible image in `image_scoring` has an `openclip_l14_laion2b_image` embedding
   (or is accounted for as unreadable), and
2. `culling.two_level.enabled: true` with `level2.embedding_space:
   openclip_l14_laion2b_image` running on real vectors (no single-bucket fallback).

Optional follow-on: backfill `openai_clip_vit_l14_image`, `siglip2_base_image`,
`dinov2_reg_base_image` for A/B comparison (same procedure, different `--space`).

## Current state (2026-05-30)

| Item | State |
|------|-------|
| Spaces registered in prod `embedding_spaces` | ✅ all 8 (incl. 4 culling towers) |
| `sub_stacks` table | ✅ present |
| `openclip_l14_laion2b_image` coverage | ✅ **61,597 / 61,597 (100%)** — backfilled 2026-05-30 |
| Backfill code path | ✅ verified end-to-end (CUDA fp16, NEF decode, DB upsert) |
| Loader optimization | ✅ thumbnails + downscale-on-load (1024 px cap) → ~30 img/s (~48 min full run) |
| Blocker | ✅ resolved (was OOM from full-res decodes + degraded WSL VM; see Troubleshooting) |
| `culling.two_level.enabled` (prod) | ✅ `true` (enabled 2026-05-31, level2 = openclip_l14 @ 0.06) |

Library is **100% `.NEF`**; ~81% have on-disk thumbnails (the rest decode RAW on the fly).

## Files / components

| Path | Role |
|------|------|
| `scripts/backfill_culling_embeddings.py` | CLI driver (`--space`, `--folder-id`, `--limit`, `--no-thumbnails`, `--dry-run`) |
| `modules/embedding_extractors.py` | `CullingEmbedder` (loaders), `generate_and_persist` (batched, parallel load, progress log) |
| `modules/thumbnails.py` | `open_image_for_ml` — embedded-JPEG → rawpy → ImageMagick RAW decode |
| `modules/db.update_image_embeddings_batch_for_space` | upsert into per-dim fact table (no-op off Postgres) |
| `config.json` → `embeddings.culling_spaces`, `culling.two_level` | enable switches |
| Venv (WSL) | `~/.venvs/tf` (torch+CUDA, open_clip, timm, transformers) |

## Prerequisites

- Docker Postgres `image_scoring` reachable at `127.0.0.1:5432` (✅).
- WSL Ubuntu **stable** with GPU passthrough (`python -c "import torch; torch.cuda.is_available()"` → `True`).
- L/14 weights cached at `~/.cache/huggingface/.../CLIP-ViT-L-14-laion2B-s32B-b82K` (✅ from spike).
- ~1.6 GB free VRAM (fits alongside the webui container on the 8 GB 4060).

## Approach (in order)

### Step 0 — Recover WSL (required before a long run)

The distro is crashing under load. Reset it cleanly:

```powershell
wsl --shutdown
# Restart Docker Desktop (its WSL backend + the postgres/webui containers come back).
```

> `wsl --shutdown` stops **all** distros including `docker-desktop` → brief Postgres/webui
> downtime. Confirm containers are healthy afterward: `docker ps`.

Sanity after restart (WSL):
```bash
wsl -d Ubuntu bash -lc "source ~/.venvs/tf/bin/activate && python -c 'import torch;print(torch.cuda.is_available())'"
```

### Step 1 — Dry-run (no GPU): confirm DB + missing count

```bash
wsl -d Ubuntu bash -lc "cd /mnt/d/Projects/image-scoring-backend && source ~/.venvs/tf/bin/activate && \
  python -m scripts.backfill_culling_embeddings --space openclip_l14_laion2b_image --dry-run"
```
Expect `Images missing openclip_l14_laion2b_image: ~61164`.

### Step 2 — Full backfill (background, resumable)

```bash
wsl -d Ubuntu bash -lc "cd /mnt/d/Projects/image-scoring-backend && source ~/.venvs/tf/bin/activate && \
  python -u -m scripts.backfill_culling_embeddings --space openclip_l14_laion2b_image \
  > reports/clip-culling/backfill_openclip_l14.log 2>&1"
```
- Run via the harness background mechanism (stays attached, notifies on completion) — **not** bare `nohup`, which did not survive the WSL session exit.
- Idempotent: re-running skips rows that already have the embedding, so a crash just means rerun.
- Progress logged every 30 s: `N/total (%)  persisted=…  img/s  ETA … min`.

### Step 3 — Monitor

```bash
wsl -d Ubuntu bash -lc "grep -E 'img/s' /mnt/d/Projects/image-scoring-backend/reports/clip-culling/backfill_openclip_l14.log | tail -3"
```
If WSL dies mid-run: recover (Step 0) and re-launch Step 2 — it resumes from the DB.

### Step 4 — Verify coverage (Windows host, stable)

```python
# python - (host)
import psycopg2
c = psycopg2.connect(host="127.0.0.1", port=5432, dbname="image_scoring", user="postgres", password="postgres")
cur = c.cursor()
cur.execute("""select count(*) from image_embeddings_768 t
               join embedding_spaces e on e.id=t.embedding_space_id
               where e.code='openclip_l14_laion2b_image'""")
print("persisted:", cur.fetchone()[0], "of 61597")
```
Acceptable end state: persisted ≈ total minus a small unreadable-file remainder (logged as
WARNING `embed_paths: cannot open …`). Investigate if the gap is large.

### Step 5 — Tune threshold for within-stack sub-stacking

`level2.distance_threshold = 0.06` is exp8 *root-grouping*-tuned, not within-stack. Sweep:
```bash
wsl -d Ubuntu bash -lc "cd /mnt/d/Projects/image-scoring-backend && source ~/.venvs/tf/bin/activate && \
  python -m scripts.research.clip_culling.two_level_thresholds --space openclip_l14_laion2b_image \
  --thresholds 0.03,0.05,0.06,0.08,0.10,0.12"
```
Pick the threshold giving a sane mean leaf-substack count (avoid 1 leaf = whole stack, which
caps a 19-frame stack at M=3 picks). Set it in `config.json`.

> **For a production-representative sweep** (the E2E variant above only covers 4 folders), use
> `scripts/research/clip_culling/two_level_thresholds_prod.py` — pure CPU, runs on the **host**
> against prod `image_scoring`@5432, no GPU/WSL:
> ```powershell
> .venv\Scripts\python.exe -m scripts.research.clip_culling.two_level_thresholds_prod `
>   --thresholds 0.02,0.03,0.04,0.05,0.06,0.08,0.10,0.12,0.15
> ```
> **Result (2026-05-30, 9,083 multi-image stacks):** usable band is **0.05–0.08**; below it stacks
> shatter into singleton (neutral, never-rejected) leaves — 0.02 made 29.6k singletons / max 214
> leaves/stack — and at ≥0.10 only ~2–9% of stacks split (degenerates to whole-stack). **0.06 chosen**
> (35% split, mean 1.5 leaves) — already the configured value, so no config change for the threshold.

### Step 6 — Enable two-level

In `config.json`:
```json
"embeddings": { "culling_spaces": ["openclip_l14_laion2b_image"] },
"culling": { "two_level": { "enabled": true,
  "level2": { "embedding_space": "openclip_l14_laion2b_image", "distance_threshold": <tuned> } } }
```
Enable **only after** Step 4 passes — otherwise stacks with missing vectors fall back to a
single bucket (safe but defeats sub-stacking).

### Step 7 (optional) — A/B towers

Repeat Steps 2–4 with `--space openai_clip_vit_l14_image`, `siglip2_base_image`,
`dinov2_reg_base_image`. Compare with
`scripts/research/clip_culling/culling_pick_review.py`. Memo verdict: OpenCLIP L/14 primary,
DINOv2 HOLD.

### Step 8 — Backfill `sub_stacks` for existing stacks

Root **stacks** already exist from the clustering phase, but **sub-stacks**
(`sub_stacks` + `images.sub_stack_id`) are only written when Selection runs with
two-level enabled. After the embedding backfill (Steps 2–4) and threshold tuning
(Step 5), recompute sub-stacks + picks for the whole library **without**
re-clustering, using `scripts/backfill_sub_stacks.py`. It does **not** require
`culling.two_level.enabled: true` — it applies the two-level logic explicitly.

The script is idempotent: it clears each stack's `sub_stacks` and rebuilds, so a
crash or rerun just recomputes. Decisions are written under policy `2.0` and the
manual-override guard (`cull_decision` set + `cull_policy_version` NULL) is ON by
default.

```bash
# Dry-run smoke on first 10 stacks (no writes; reports leaf/pick histogram)
wsl -d Ubuntu bash -lc "cd /mnt/d/Projects/image-scoring-backend && source ~/.venvs/tf/bin/activate && \
  python -m scripts.backfill_sub_stacks --dry-run --limit 10"

# Live, whole library, background-friendly + resumable
wsl -d Ubuntu bash -lc "cd /mnt/d/Projects/image-scoring-backend && source ~/.venvs/tf/bin/activate && \
  python -u -m scripts.backfill_sub_stacks > reports/clip-culling/backfill_sub_stacks.log 2>&1"
```

`--embedding-space` / `--threshold` override the config `level2`; `--folder PATH`
restricts to a subtree; `--no-preserve-manual` disables the guard. If level2 is a
culling tower and embedding coverage is < 90%, the script logs a **LOW EMBEDDING
COVERAGE** warning (those stacks collapse to one leaf = whole-stack cap) — finish
Step 4 first.

Verify afterward (Windows host or `mcp__imgscore-py-sse__execute_sql`):

```sql
-- multi-image stacks still missing sub_stacks (expect ~0 after a full run)
SELECT s.id, COUNT(i.id) AS n
FROM stacks s
JOIN images i ON i.stack_id = s.id
LEFT JOIN sub_stacks ss ON ss.stack_id = s.id
WHERE ss.id IS NULL
GROUP BY s.id
HAVING COUNT(i.id) >= 2
LIMIT 20;

-- images in a stack but with no sub_stack assigned
SELECT COUNT(*) FROM images WHERE stack_id IS NOT NULL AND sub_stack_id IS NULL;
```

Rollback: `DELETE FROM sub_stacks;` + null `images.sub_stack_id`, then rerun
`scripts/backfill_subcluster_picks.py` to restore legacy bands.

## Throughput / runtime

| Loader | Observed | Full 61k estimate |
|--------|----------|-------------------|
| RAW decode per image (initial) | ~0.5 img/s | ~34 h (rejected) |
| Thumbnail + serial | ~2–4 img/s | ~6–8 h |
| Thumbnail + parallel load + **downscale-on-load (1024 px)** | **~30 img/s** (measured 2026-05-30, `--batch-size 16`) | **~48 min** (actual) |

GPU inference is not the bottleneck; image decode is. `generate_and_persist` loads
`batch_size*4` images per step across 8 threads, re-batching by `batch_size` for the GPU.

## Tests

- Registry/loader unit (no GPU/DB): `python -m pytest tests/test_culling_embedding_spaces.py -q`
- Two-level compute/selection: `python -m pytest tests/test_two_level_culling.py tests/test_two_level_selection.py -q`
- Lint touched files: `python -m ruff check modules/embedding_extractors.py scripts/backfill_culling_embeddings.py`
- Manual smoke (WSL): `--limit 5` writes 5 rows to `image_embeddings_768`.

## Rollback / flags

- **Fully reversible.** Vectors are additive in `image_embeddings_768`; to undo:
  ```sql
  DELETE FROM image_embeddings_768
   WHERE embedding_space_id = (SELECT id FROM embedding_spaces WHERE code='openclip_l14_laion2b_image');
  ```
- Disable the feature anytime: `culling.two_level.enabled: false` (reverts to legacy bands).
- `embeddings.culling_spaces` only drives this backfill script — no pipeline auto-generation.
- No default change: MobileNet remains the grouping/clustering default; this is opt-in per #220.

## Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| Process exits 15 / `dmesg` shows `Killed process … (python)` | **Host-RAM OOM** from holding a chunk of full-res NEF decodes (~70 MB each). Fixed in `embed_paths` (downscale-on-load, 1024 px cap); if it recurs, lower `--batch-size`. |
| Throughput stuck at <1 img/s | Same OOM cause — RAM thrashing near the ceiling. The downscale fix raises it to ~30 img/s. |
| `WslService/E_UNEXPECTED`, empty output, distro `Stopped` | WSL host relay break and/or degraded utility VM (often *after* an OOM event). Run **attached** (harness background keeps the distro alive) — a `setsid`-detached job lets WSL idle-terminate the distro right after a cold boot. Repeated crashes → full reset (Step 0: `wsl --shutdown` + Docker restart). See the `wsl-environment` skill. |
| `embed_paths: cannot open …` warnings | unreadable thumbnail/RAW; image skipped — rerun later or `--no-thumbnails` |
| `Images missing …: 0` but no vectors | wrong DB (check `database.postgres.dbname`/port) |
| `space … not registered` | run space seed/migration; prod already has all 8 |
| OOM / VRAM | lower `--batch-size`; ensure sequential model load |
