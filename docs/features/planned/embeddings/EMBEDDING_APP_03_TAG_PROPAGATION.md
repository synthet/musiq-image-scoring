# 03 - Tag Propagation from Embedding Neighbors

*Part of [Possible Applications of image_embedding](EMBEDDING_APPLICATIONS.md).*

## Goal

Accelerate keyword coverage by propagating tags from visually similar, already-tagged images.

## Why this matters

CLIP tagging is effective but can be expensive at scale. Many images in bursts or repeated scenes share semantics and can inherit stable tags with high confidence.

## Proposed behavior

For each untagged image:

1. Find `k` nearest tagged neighbors by cosine similarity.
2. Aggregate neighbor keywords with weighted voting.
3. Apply keywords that pass confidence thresholds.
4. Mark tags as propagated for traceability.

This can be used as:

- a pre-pass before CLIP tagging,
- a fallback when model resources are unavailable,
- or a post-pass to fill sparse metadata.

## Integration points

- `modules/tagging.py`
  - Add `propagate_tags(...)` workflow and optional runner entrypoint.
- `modules/db.py`
  - Add helper queries for tagged vs untagged images with embeddings.
- `modules/ui/tabs/tagging.py`
  - Add action: "Quick Tag from Similar Images".
- `modules/mcp_server.py` (optional)
  - Add tool for automation workflows.

## Confidence model

Weighted keyword score example:

`keyword_score = sum(similarity_i * has_keyword_i) / sum(similarity_i)`

Apply keyword when:

- `keyword_score >= min_keyword_confidence`
- at least `min_support_neighbors` neighbors contain the keyword
- top neighbor similarity exceeds `min_anchor_similarity`

## Configuration

- `tagging.propagation_enabled` (bool, default `false`)
- `tagging.propagation_k` (int, default `5`)
- `tagging.propagation_min_similarity` (float, default `0.85`)
- `tagging.propagation_min_keyword_confidence` (float, default `0.60`)
- `tagging.propagation_min_support_neighbors` (int, default `2`)
- `tagging.propagation_write_mode` (`append|replace_missing_only`, default `replace_missing_only`)

## Data provenance

To keep auditability:

- Track source as `propagated` vs `model_generated`.
- Optionally store propagation metadata in `scores_json` or a dedicated field (future).

## Edge cases

- Propagation drift in heterogeneous folders: mitigate with high anchor similarity.
- Incorrect source tags can spread: restrict to trusted tags or high-confidence seeds.
- Empty neighbor set: no-op fallback to existing CLIP path.

## Performance notes

- Best implemented in batched nearest-neighbor mode to avoid repeated scans.
- Can reuse normalized embedding matrix for all untagged images in a folder.

## Validation plan

- Unit tests:
  - voting math and thresholds
  - append vs replace behavior
- Offline evaluation:
  - compare propagated tags vs CLIP tags on sampled set
  - measure precision@k for propagated keywords
- Safety checks:
  - cap max propagated keywords per image
  - dry-run mode to inspect candidate tags before write

## Success metrics

- Increase in keyword coverage rate.
- Acceptable precision on manually reviewed sample.
- Reduction in end-to-end tagging runtime for large folders.
