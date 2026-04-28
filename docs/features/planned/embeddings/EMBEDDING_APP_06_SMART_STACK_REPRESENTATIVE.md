# 06 - Smart Stack Representative (Centroid-Aware Best Image)

*Part of [Possible Applications of image_embedding](EMBEDDING_APPLICATIONS.md).*

## Goal

Choose a stack cover/best image that is both high quality and representative of the stack's visual content.

## Why this matters

Selecting best image by `score_general` alone can pick an outlier frame. For browsing and culling, users often expect the cover to represent the dominant scene in the stack.

## Proposed behavior

Support multiple best-image strategies:

- `score`: current behavior (highest quality score)
- `centroid`: closest image to stack embedding centroid
- `balanced`: weighted blend of score rank and centroid proximity

Recommended default for experimentation: `balanced`.

## Integration points

- `modules/clustering.py`
  - In stack creation logic where `best_image_id` is assigned.
  - Reuse embeddings already computed in clustering pass.
- Config
  - Add strategy setting and weight controls.

## Balanced strategy formulation

For image `i` in stack:

- `quality_i = normalized(score_general_i)`
- `represent_i = 1 - normalized_distance_to_centroid_i`
- `final_i = alpha * quality_i + (1 - alpha) * represent_i`

Pick image with highest `final_i`.

## Configuration

- `clustering.best_image_strategy` (`score|centroid|balanced`, default `score`)
- `clustering.best_image_alpha` (float, default `0.65`, only for `balanced`)
- `clustering.best_image_min_score` (float, optional)

## Data flow

1. Clustering produces stack members and embeddings.
2. Compute centroid vector for each stack.
3. Compute candidate representative score per member.
4. Persist selected `best_image_id` to `STACKS`.

## Edge cases

- Missing embeddings for stack members: fallback to score strategy.
- All equal scores and distances: deterministic tie-break by `created_at`, then `id`.
- Single-image stack: that image is best by definition.

## Performance notes

- Additional centroid computation is negligible relative to model inference.
- No extra model calls required.

## Validation plan

- Unit tests for each strategy branch.
- Regression tests to ensure no invalid `best_image_id`.
- Human review on sampled stacks comparing representativeness.

## Success metrics

- Higher subjective representativeness score in QA reviews.
- Reduced manual "set cover image" operations by users.
- No significant regression in average cover quality score.
