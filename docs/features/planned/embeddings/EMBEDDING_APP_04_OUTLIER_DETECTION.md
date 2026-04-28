# 04 - Outlier and Anomaly Detection

*Part of [Possible Applications of image_embedding](EMBEDDING_APPLICATIONS.md).*

## Goal

Identify images that are visually atypical inside a folder or collection segment.

## Why this matters

Outliers often correspond to:

- misfiled images,
- corrupted or partial files,
- accidental imports from unrelated shoots,
- or unusual captures worth manual review.

## Proposed behavior

Compute an outlier score per image from local embedding neighborhood statistics, then flag low-cohesion images.

Baseline score options:

- Mean cosine similarity to all folder images.
- Mean similarity to top-K nearest neighbors.
- Distance to folder centroid.

Recommended initial metric: `top_k_mean_similarity` for robustness.

## Integration points

- `modules/similar_search.py`
  - Add `find_outliers(folder_path, z_threshold=2.0, k=10, limit=100)`.
- `modules/mcp_server.py`
  - Expose as MCP tool for diagnostics and automation.
- Optional UI
  - Add "Audit Outliers" section in Stacks or a dedicated diagnostics tab.

## Scoring and thresholding

For each image:

1. Normalize embedding.
2. Compute similarity to others.
3. Compute `score = mean(top_k_similarities)`.
4. Compute z-score within folder distribution.
5. Flag if `z <= -z_threshold`.

Return:

- `image_id`, `file_path`
- `outlier_score`
- `z_score`
- optional top similar neighbors for explainability

## Configuration

- `similarity.outlier_k_neighbors` (int, default `10`)
- `similarity.outlier_z_threshold` (float, default `2.0`)
- `similarity.outlier_min_folder_size` (int, default `20`)

## Explainability

Each flagged outlier should include:

- nearest 3 neighbors and similarities,
- folder mean/std,
- and threshold applied.

This makes review actionable and reduces false alarm skepticism.

## Edge cases

- Very small folders: skip or switch to simpler threshold.
- Multi-theme folders: cluster first, then detect outliers within cluster.
- Missing embeddings: report as `embedding_missing` anomaly class.

## Performance notes

- Folder-level computations are usually tractable.
- For large folders, use approximate neighbor search or chunked matrix operations.

## Validation plan

- Unit tests for z-score and threshold logic.
- Integration tests with synthetic injected anomalies.
- Manual review set to estimate precision at top-N outliers.

## Success metrics

- Useful precision on top flagged outliers.
- Faster cleanup of misfiled content.
- Stable runtime and memory for medium/large folders.
