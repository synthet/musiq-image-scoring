# 01 - Diversity-Aware Selection

*Part of [Possible Applications of image_embedding](EMBEDDING_APPLICATIONS.md).*

## Goal

Improve automatic pick/reject decisions so selected images are both high quality and non-redundant inside each stack.

## Why this matters

Current stack selection is primarily score-ranked (`score_general`) and split by policy bands. In burst-heavy stacks, top-scored images can be near-identical, which reduces practical value for photographers.

## Proposed behavior

After score sorting, re-rank candidate picks with a diversity objective:

- Preserve quality as the primary signal.
- Penalize images that are too similar to already picked items.
- Keep deterministic output for reproducibility.

Use an MMR-style criterion for each next pick:

`mmr = lambda * normalized_score - (1 - lambda) * max_similarity_to_selected`

Where:

- `lambda` in `[0,1]` controls quality vs diversity.
- `max_similarity_to_selected` is cosine similarity in embedding space.

## Integration points

- `modules/selection.py`
  - In `SelectionService._process_folder()`, after stack grouping and score ordering.
  - Replace direct top-N pick assignment with diversity-aware pick ordering.
- `modules/selection_policy.py`
  - Keep current band sizing logic, but use diversity-aware order for pick band.
- `modules/db.py`
  - Reuse `get_image_embedding(image_id)` for per-stack vectors.

## Configuration

Add optional settings:

- `selection.diversity_enabled` (bool, default `false`)
- `selection.diversity_lambda` (float, default `0.70`)
- `selection.diversity_min_similarity_penalty` (float, default `0.85`)
- `selection.diversity_fallback_on_missing_embedding` (enum: `score_only|skip|compute`, default `score_only`)

## Data flow

1. Stack images sorted by score (existing behavior).
2. Pull embeddings for all images in stack.
3. Normalize vectors once per stack.
4. Iteratively choose picks with MMR until pick quota reached.
5. Reject/neutral assignment remains policy-driven.
6. Persist decisions via existing `db.batch_update_cull_decisions()`.

## Edge cases

- Missing embedding for one or more images: fallback to score-only order for those items.
- Stack size `n <= 2`: keep current small-stack behavior.
- Tied scores and tied MMR: stable tie-break with `created_at`, then `id`.

## Performance notes

- Complexity per stack is roughly `O(k*n)` for selection phase when reusing precomputed similarities.
- Typical stack sizes are small, so overhead is minor.
- Cache per-stack similarity matrix to avoid recomputation.

## Validation plan

- Unit tests:
  - deterministic ordering with fixed embeddings
  - behavior with missing embeddings
  - tiny stacks (`n=1`, `n=2`)
- Integration tests:
  - compare pick diversity before/after (mean pairwise similarity of picks)
  - ensure total pick/reject/neutral counts unchanged for each stack size

## Success metrics

- Lower average pairwise cosine similarity among picked images.
- No regression in average `score_general` of picked images beyond an allowed delta.
- Positive user feedback in culling workflow (fewer manual deselections of redundant picks).
