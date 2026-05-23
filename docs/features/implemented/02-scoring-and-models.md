# Scoring and models

**Purpose:** Batch and single-image **quality analysis** using multiple IQA / aesthetic models, persisting scores and derived rating/label metadata.

**User-visible behavior:** Folder or selector-based scoring jobs; optional skip of complete rows; force rescore; DB “fix” pass for incomplete rows; single-image score and metadata-only **fix-image** without re-inference.

**Primary code paths:** `modules/scoring.py`, model wrappers (`musiq_wrapper`, `liqe`, `topiq`, `qalign`, …), scoring runner wired from `modules/api.py` and `modules/engine.py`.

**Main HTTP API (prefix `/api`):**

- `POST /api/scoring/start` — enqueue scoring (`job_type` scoring; phases typically indexing → metadata → scoring)
- `POST /api/scoring/stop`, `GET /api/scoring/status`
- `POST /api/scoring/fix-db` — repair incomplete scores (uses runner directly; see OpenAPI description)
- `POST /api/scoring/single` — synchronous single file
- `POST /api/scoring/fix-image` — recompute weighted aggregates from DB model scores + XMP/thumbnail side effects

**LLM-judge engines (shadow, opt-in):** Two vision-LLM scorers can rate images
against a multi-dimensional rubric (composition, exposure, sharpness, subject +
overall, each 0–100) and register as `IScoringModel`s alongside the local
metrics:

| Engine | `name` | Backend | Code |
|--------|--------|---------|------|
| Cursor SDK | `cursor` | `cursor-sdk` (one-shot agent + `SDKImage`) | `modules/cursor_scorer.py`, `modules/engines/cursor_model.py` |
| Claude Agent SDK | `claude` | `claude-agent-sdk` (base64 image block + JSON-schema structured output, `allowed_tools=[]`) | `modules/claude_scorer.py`, `modules/engines/claude_model.py` |

- **Disabled by default.** Both ship as `{"enabled": false, "shadow": false}` in
  `scoring.models` (fully inert). Set `shadow: true` to run them as shadow models
  (scored and stored, never fused), or `enabled: true, shadow: false` for
  production/fusion.
- **How they run:** `ScoringRunner` uses registry-driven `MultiModelHost`
  (`modules/engines/factory.py`) as the live scorer. Active registry models
  (including shadow `topiq`, LLM judges, etc.) run in `MultiModelHost.run_all_models`
  and persist to `image_model_scores`. Legacy `ScoringWorker._run_registry_models()`
  injection remains only when a non-host scorer is injected (tests).
  The overall score lands in `image_model_scores`; the rubric rides in
  `scores_json` as `subscores`. Same path activates `topiq`.
- **Read path / API:** `_image_detail_payload` / `_images_list_payload`
  (`modules/api.py`) merge `image_model_scores` via
  `db.get_image_model_scores` / `db.get_batch_image_model_scores`: production
  models without a legacy `score_*` column get a flat `{name}_score` field, and a
  structured `model_scores` block carries every model (including shadow, with
  `is_shadow`). Shadow engines surface only in that block.
- **Optional deps:** `requirements/requirements_llm_judge.txt`. The Claude engine
  also needs the Claude Code CLI on PATH (`npm i -g @anthropic-ai/claude-code`).
- **Credentials** (never in `config.json`): `secrets.json` `"cursor": {"api_key": …}`
  / `"anthropic": {"api_key": "sk-ant-…"}`, or env `CURSOR_API_KEY` /
  `ANTHROPIC_API_KEY`.
- **Tuning:** `scoring.cursor.*` / `scoring.claude.*` — `model`, `max_dimension`,
  `timeout_seconds`. These are paid, network-bound calls; keep them shadow-only.

**Related docs:** [MODELS_SUMMARY](../../technical/MODELS_SUMMARY.md) · [MODEL_INPUT_SPECIFICATIONS](../../technical/MODEL_INPUT_SPECIFICATIONS.md) · [WEIGHTED_SCORING_STRATEGY](../../technical/WEIGHTED_SCORING_STRATEGY.md) · [SCORING_CHANGES](../../technical/SCORING_CHANGES.md) · [MODEL_WEIGHTS](../../reference/models/MODEL_WEIGHTS.md)
