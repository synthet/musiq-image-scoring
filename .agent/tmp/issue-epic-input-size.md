## Epic

Complete the **pipeline-wide input-size study**: find the ideal upstream pixel budget (thumbnail long edge, file decode cap, RAW→JPEG square size, optional ViT preprocess override) so scoring, culling, keywords, and captions produce the most valuable and diverse outputs.

**Harness is implemented** (2026-05-31); **NPZ/eval grid not run yet**. Do not change production defaults until Phase 6 sign-off.

### Canonical docs

- Runbook: [`docs/reports/INPUT_SIZE_CULLING_2026-05-29.md`](docs/reports/INPUT_SIZE_CULLING_2026-05-29.md)
- Status: [`docs/reports/INPUT_SIZE_CULLING_PRELIMINARY_2026-05-30.md`](docs/reports/INPUT_SIZE_CULLING_PRELIMINARY_2026-05-30.md)
- Policy draft: [`docs/reports/UNIFIED_INPUT_POLICY_2026-05-31.md`](docs/reports/UNIFIED_INPUT_POLICY_2026-05-31.md)
- Harness: `scripts/research/clip_culling/input_size_*.py`, `run_input_size_study.sh`
- Artifacts: `reports/clip-culling/input-size/`

### Sub-issues (dependency-ordered)

- [ ] #261 — Phase 1: PyTorch embedding NPZ grid + base IQA *(Ready candidate — run first)*
- [ ] #262 — Phase 2: MUSIQ SPAQ/AVA + TOPIQ/ARNIQA @768/1024 *(dep: #261)*
- [ ] #263 — Phase 3: Keyword + BLIP caption sweeps *(dep: #261)*
- [ ] #264 — Phase 5: ViT preprocess-size override *(conditional; dep: #261 eval)*
- [ ] #265 — Phase 6: Unified pixel policy sign-off *(dep: #262, #263, #264 if run)*
- [ ] #266 — Optional: MobileNet embedding grid (TF GPU isolation)
- [ ] [gallery #138](https://github.com/synthet/image-scoring-gallery/issues/138) — Cross-repo gallery policy adoption

### Environment

WSL + `~/.venvs/tf`, E2E Postgres `image_scoring_test` @5433, detached via `setsid`.

### Related (distinct work)

- #220 — Pipeline model upgrades (tower *choice* at fixed resolution; complementary)
- Gallery wiki: [`07-pipeline-input-size-study-2026-05.md`](https://github.com/synthet/image-scoring-gallery/blob/main/docs/reports/07-pipeline-input-size-study-2026-05.md)
