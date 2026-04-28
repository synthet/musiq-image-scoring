# 02 - Near-Duplicate Detection

*Part of [Possible Applications of image_embedding](EMBEDDING_APPLICATIONS.md).*

## Goal

Detect visually duplicate or near-duplicate images even when file hashes differ.

## Why this matters

SHA256 catches exact byte duplicates only. Real libraries contain near-duplicates from re-export, resize, crop, or minor edits. These consume storage and clutter selection.

## Proposed behavior

Introduce a near-duplicate search utility based on cosine similarity over normalized embeddings.

- Candidate pair is near-duplicate if `cosine_similarity >= threshold`.
- Default threshold starts at `0.98`, configurable.
- Support folder-scoped and global modes.

## Integration points

- `modules/similar_search.py`
  - Add `find_near_duplicates(threshold=0.98, folder_path=None, limit=None)`.
  - Reuse existing embedding loading path from `db.get_embeddings_for_search()`.
- `modules/mcp_server.py`
  - Expose MCP tool: `find_near_duplicates`.
- Optional UI
  - Add actions in `modules/ui/tabs/stacks.py` for duplicate review.

## Algorithm options

### Baseline (exact pairwise for moderate N)

1. Load embeddings.
2. L2-normalize.
3. Compute block-wise dot products to avoid large peak memory.
4. Keep upper-triangle pairs above threshold.

### Scalable mode (future)

- Use ANN index (FAISS/HNSW) to retrieve high-similarity neighbors only.
- Persist index to disk and refresh incrementally.

## Output shape

Each duplicate group entry can include:

- `image_id_a`, `image_id_b`
- `file_path_a`, `file_path_b`
- `similarity`
- optional metadata (`score_general`, `created_at`, `stack_id`)

## Configuration

- `similarity.duplicate_threshold` (float, default `0.98`)
- `similarity.duplicate_min_group_size` (int, default `2`)
- `similarity.duplicate_max_pairs` (int, default `5000`)

## Edge cases

- Identical embedding vectors from cache collisions should be extremely rare; verify hashes before bulk deletion workflows.
- Very large collections can produce huge pair counts; enforce limit/pagination.
- Exclude same image ID self-matches.

## Performance notes

- Pairwise all-vs-all is `O(n^2)`; block processing is required for high N.
- Folder-scoped queries are preferred for interactive latency.

## Validation plan

- Unit tests:
  - threshold behavior at boundary values
  - no self pairs
  - deterministic pair ordering
- Integration tests:
  - curated duplicate fixture set (resize/re-encode/crop variants)
  - precision/recall estimate against manually labeled subset

## Success metrics

- High precision for returned near-duplicates at default threshold.
- Reduction in manual duplicate cleanup time.
- Stable runtime for folder-level scans.
