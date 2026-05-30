# CLIP towers + ML heads culling harness — reference URLs

Consolidated list of every external and internal source referenced while planning the
offline CLIP/embedding culling experimentation harness. Grouped by purpose. Last
verified 2026-05-28.

> Hardware/license posture for this project: RTX 4060 Laptop, 8 GB VRAM, English-only
> prompts, permissive licenses preferred. Multilingual towers (MetaCLIP 2, SigLIP 2
> multilingual) are listed for completeness, not as defaults.

## Embedding towers (candidates + already in use)

| Model | Hugging Face / weights | Source repo |
|-------|------------------------|-------------|
| OpenAI CLIP ViT-L/14 (768-d) | https://huggingface.co/openai/clip-vit-large-patch14 | https://github.com/openai/CLIP |
| OpenAI CLIP ViT-B/32 (512-d, current keyword tower) | https://huggingface.co/openai/clip-vit-base-patch32 | https://github.com/openai/CLIP |
| OpenCLIP ViT-L/14 `laion2b_s32b_b82k` (768-d) | https://huggingface.co/laion/CLIP-ViT-L-14-laion2B-s32B-b82K | https://github.com/mlfoundations/open_clip |
| SigLIP 2 base patch16-224 (768-d, optional) | https://huggingface.co/google/siglip2-base-patch16-224 | https://github.com/google-research/big_vision |
| DINOv2 with registers, base (768-d, spike) | https://huggingface.co/facebook/dinov2-with-registers-base | https://github.com/facebookresearch/dinov2 |
| SigLIP2 base patch16-224 (768-d, spike) | https://huggingface.co/google/siglip2-base-patch16-224 | https://github.com/google-research/big_vision |
| BioCLIP 2 (768-d, already used for bird species) | https://huggingface.co/imageomics/bioclip-2 | https://github.com/mlfoundations/open_clip |
| BLIP base captioning (768-d, already used) | https://huggingface.co/Salesforce/blip-image-captioning-base | https://github.com/salesforce/BLIP |
| MetaCLIP 2 worldwide (NC, not a default) | https://huggingface.co/facebook/metaclip-2-worldwide-huge-quickgelu | https://github.com/facebookresearch/MetaCLIP |

MobileNetV2 (current default culling embedding, 1280-d) ships with Keras applications:
https://keras.io/api/applications/mobilenet/

## Scoring heads / IQA

| Head | Weights / repo |
|------|----------------|
| LAION aesthetic predictor (MLP on CLIP ViT-L/14, 768-d) | https://github.com/christophschuhmann/improved-aesthetic-predictor |
| LAION aesthetic weights file (`sac+logos+ava1-l14-linearMSE.pth`) | https://github.com/christophschuhmann/improved-aesthetic-predictor/blob/main/sac%2Blogos%2Bava1-l14-linearMSE.pth |
| pyiqa (CLIP-IQA, ARNIQA, TOPIQ, LIQE, MUSIQ implementations) | https://github.com/chaofengc/IQA-PyTorch |

## Papers

| Paper | arXiv |
|-------|-------|
| CLIP — Learning Transferable Visual Models (Radford et al., 2021) | https://arxiv.org/abs/2103.00020 |
| CLIPScore (Hessel et al., 2021) | https://arxiv.org/abs/2104.08718 |
| OpenCLIP — Reproducible scaling laws (Cherti et al., 2022) | https://arxiv.org/abs/2212.07143 |
| LAION-5B (Schuhmann et al., 2022) | https://arxiv.org/abs/2210.08402 |
| MetaCLIP (Xu et al., 2023) | https://arxiv.org/abs/2309.16671 |
| MetaCLIP 2: A Worldwide Scaling Recipe (Chuang et al., 2025) | https://arxiv.org/abs/2507.22062 |
| SigLIP (Zhai et al., 2023) | https://arxiv.org/abs/2303.15343 |
| SigLIP 2 (Tschannen et al., 2025) | https://arxiv.org/abs/2502.14786 |
| DINOv2 (Oquab et al., 2023) | https://arxiv.org/abs/2304.07193 |
| Vision Transformers Need Registers (Darcet et al., 2023) | https://arxiv.org/abs/2309.16588 |
| CLIP-IQA — Exploring CLIP for assessing look and feel (Wang et al., 2022) | https://arxiv.org/abs/2207.12396 |
| ARNIQA (Agnolucci et al., 2023) | https://arxiv.org/abs/2310.14918 |
| TOPIQ (Chen et al., 2023) | https://arxiv.org/abs/2308.03060 |
| MobileNetV2 (Sandler et al., 2018) | https://arxiv.org/abs/1801.04381 |
| BLIP (Li et al., 2022) | https://arxiv.org/abs/2201.12086 |
| BioCLIP (Stevens et al., 2024) | https://arxiv.org/abs/2311.18803 |

## This repo — GitHub issues and board

| Item | URL |
|------|-----|
| Project board (cross-repo queue) | https://github.com/users/synthet/projects/1 |
| #220 Pipeline model upgrades: DINOv2 culling, SigLIP2 keywords, ARNIQA shadow | https://github.com/synthet/image-scoring-backend/issues/220 |
| #185 Calibration layer | https://github.com/synthet/image-scoring-backend/issues/185 |
| #180 Modernize IQA / aesthetic scoring stack (QPT V2 + TOPIQ-NR) | https://github.com/synthet/image-scoring-backend/issues/180 |
| #181 Spike QPT V2 + TOPIQ-NR local inference | https://github.com/synthet/image-scoring-backend/issues/181 |
| #148 Labeled dataset + classifier on embeddings (DINOv2/CLIP) | https://github.com/synthet/image-scoring-backend/issues/148 |
| #144 Optional pyiqa and CLIP-IQA metrics | https://github.com/synthet/image-scoring-backend/issues/144 |
| #143 Technical failure detection | https://github.com/synthet/image-scoring-backend/issues/143 |
| #133 Atlas embedding_spaces dropdown | https://github.com/synthet/image-scoring-backend/issues/133 |

## This repo — internal documents

- [docs/MODEL_RECOMMENDATIONS_PIPELINES.md](../../../docs/MODEL_RECOMMENDATIONS_PIPELINES.md) — canonical phased model roadmap
- [docs/NEW_MODELS_SUMMARY.md](../../../docs/NEW_MODELS_SUMMARY.md) — consolidated new/roadmap model overview
- [docs/reports/CLIP_MODELS_CULLING_SCORING_2026-05-23.md](../../../docs/reports/CLIP_MODELS_CULLING_SCORING_2026-05-23.md) — CLIP-family research for culling/scoring
- [docs/reports/AUTO_CULLING_ALGORITHMS_RESEARCH_2026-05-23.md](../../../docs/reports/AUTO_CULLING_ALGORITHMS_RESEARCH_2026-05-23.md) — industry auto-culling patterns
- [docs/reports/DEEP_RESEARCH_REPORT.md](../../../docs/reports/DEEP_RESEARCH_REPORT.md) — IQA model selection
- [docs/technical/EMBEDDINGS.md](../../../docs/technical/EMBEDDINGS.md) — embedding-space registry contract + "adding a new space" checklist
- [docs/planning/database/DB_VECTORS_REFACTOR.md](../../../docs/planning/database/DB_VECTORS_REFACTOR.md) — pgvector multi-space storage
- [docs/technical/PIPELINE_TERMINOLOGY.md](../../../docs/technical/PIPELINE_TERMINOLOGY.md) — stage labels vs phase_code vs API job types

## This repo — code touchpoints for the harness

- `modules/bird_species.py` — `open_clip.create_model_and_transforms` load pattern (towers + tokenizer)
- `modules/embeddings_extract.py` — `l2_normalize` and per-model feature extractors
- `modules/embedding_spaces.py` — `SPACE_DIMS`, default space codes
- `modules/projections_db.py` — `get_embeddings_with_metadata_for_space(...)`
- `modules/similar_search.py` — pgvector cosine search per space
- `modules/clustering.py` — `ClusteringEngine` (AgglomerativeClustering, `CLUSTER_VERSION`)
- `modules/sub_clustering.py` — in-stack sub-clustering (`culling.sub_cluster_distance_threshold`)
- `modules/tagging.py` — `KeywordScorer.predict` (current CLIP B/32 keyword baseline)
- `scripts/analysis/model_score_quality_report.py` — score-pull + correlation report pattern
- `scripts/maintenance/backfill_arniqa.py` — standalone DB-writing script bootstrap + path resolution
- `docker-compose.yml` — `db-e2e` service: `image_scoring_test` on host port 5433
- `tests/conftest.py` / `modules/test_db_constants.py` — E2E DB activation + guards
- `scripts/research/clip_culling/input_size_native.py` — log native preprocess / max_dimension per tower
- `scripts/research/clip_culling/input_size_embed.py` — long-edge sweep → NPZ under `reports/clip-culling/input-size/npz/`
- `scripts/research/clip_culling/input_size_eval.py` — burst ARI, pick/reject gap, pair margin, IQA mishot ROC
- `docs/reports/INPUT_SIZE_CULLING_2026-05-29.md` — study memo and runbook
