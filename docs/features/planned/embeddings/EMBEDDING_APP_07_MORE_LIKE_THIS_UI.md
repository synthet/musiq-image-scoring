# 07 - "More Like This" Cross-Folder UI

*Part of [Possible Applications of image_embedding](EMBEDDING_APPLICATIONS.md).*

## Goal

Expose embedding-based similar-image retrieval directly in the Web UI for one-click visual discovery.

## Why this matters

The backend already supports similarity search, but current access is mostly MCP/tool-driven. A UI surface makes the feature useful to non-technical users and daily workflows.

## Proposed behavior

From image cards/detail view, add "Find Similar" action:

- calls backend similarity endpoint,
- shows ranked gallery of similar images,
- supports folder scope and minimum similarity filters,
- allows jump-to-image or batch actions (future).

## Integration points

- `modules/api.py`
  - Add endpoint: `GET /api/similar?image_id=<id>&limit=<n>&folder_path=<path>&min_similarity=<x>`.
- `modules/similar_search.py`
  - Reuse existing `search_similar_images(...)`.
- Frontend layer
  - Add action button and result panel in image browsing context.

## API response shape (proposal)

```json
{
  "query_image_id": 123,
  "results": [
    {"image_id": 456, "file_path": "...", "similarity": 0.947231}
  ],
  "count": 20
}
```

## UX details

- Show top result confidence as percentage.
- Allow sorting by similarity or score.
- Include "open containing folder" and "set as compare target" actions.
- Empty state message when no results meet threshold.

## Configuration

- `ui.similar_search_default_limit` (int, default `20`)
- `ui.similar_search_default_min_similarity` (float, default `0.80`)
- `ui.similar_search_enable_cross_folder` (bool, default `true`)

## Edge cases

- Query image missing embedding: backend computes on demand; UI shows loading state.
- No candidates in scope: clear guidance to run clustering first.
- Long-running global search: show progress indicator and cancellable request.

## Performance notes

- Folder-scoped search should be fast for interactive use.
- For global large datasets, cap result size and prefer incremental rendering.

## Validation plan

- API tests for parameter validation and error cases.
- UI tests for action visibility, loading, empty state, and pagination.
- End-to-end test: click image -> find similar -> open result.

## Success metrics

- Adoption: percent of sessions using "Find Similar".
- Engagement: click-through from similar results to detail view.
- Utility: user-reported reduction in manual browsing time.
