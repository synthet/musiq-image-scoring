# Possible Applications of `image_embedding`

The project already stores a **MobileNetV2 1280-d feature vector** per image during clustering ([modules/clustering.py](../../../modules/clustering.py), lines 492-499) and consumes it in two places: **Agglomerative Clustering** for stack creation and **cosine-similarity search** in [modules/similar_search.py](../../../modules/similar_search.py). Below are seven additional applications, each with a concrete sketch of where it plugs into the existing code.

Detailed per-feature specs:

- [Index of detailed specs](EMBEDDING_APPLICATIONS_INDEX.md)
- [01 - Diversity-Aware Selection](EMBEDDING_APP_01_DIVERSITY_SELECTION.md)
- [02 - Near-Duplicate Detection](EMBEDDING_APP_02_NEAR_DUPLICATE_DETECTION.md)
- [03 - Tag Propagation](EMBEDDING_APP_03_TAG_PROPAGATION.md)
- [04 - Outlier Detection](EMBEDDING_APP_04_OUTLIER_DETECTION.md)
- [05 - 2D Embedding Map](EMBEDDING_APP_05_2D_EMBEDDING_MAP.md)
- [06 - Smart Stack Representative](EMBEDDING_APP_06_SMART_STACK_REPRESENTATIVE.md)
- [07 - More Like This UI](EMBEDDING_APP_07_MORE_LIKE_THIS_UI.md)

---

## 1. Diversity-Aware Selection (highest impact)

**Problem:** The current selection policy ([modules/selection.py](../../../modules/selection.py)) ranks images inside a stack purely by `score_general` and then applies a fixed 33/33/34% pick/reject/neutral split. When a stack contains several near-identical shots, the top picks can be visually redundant.

**Idea:** After sorting by score, penalize candidates that are too similar to already-picked images. This produces a set of picks that are both high-quality *and* visually varied.

**Where it fits:**

- In the per-stack loop of `SelectionService._process_folder()`, after `classify_sorted_ids()`.
- Load embeddings for the stack via `db.get_image_embedding()`, compute pairwise cosine distances, and apply a **Maximal Marginal Relevance (MMR)** re-ranking: each next pick maximizes `lambda * score - (1 - lambda) * max_sim_to_already_picked`.
- The lambda weight and a diversity threshold could live in `config.json` under `selection.diversity_lambda` (default ~0.7).

**Modules touched:** `modules/selection.py`, `modules/selection_policy.py`, config schema.

---

## 2. Near-Duplicate Detection

**Problem:** Images re-saved at different quality, slightly cropped, or exported at different resolutions have different SHA256 hashes but nearly identical embeddings. The current system cannot surface these.

**Idea:** Flag image pairs with cosine similarity above a high threshold (e.g., 0.98) as near-duplicates, even across folders.

**Where it fits:**

- New function `find_near_duplicates(threshold=0.98, folder_path=None)` in `modules/similar_search.py`.
- Reuse `db.get_embeddings_for_search()` to load all vectors, build a similarity matrix (or use batched dot products), filter pairs above threshold.
- Expose as an MCP tool in `modules/mcp_server.py` and optionally as a UI action in the Stacks tab.

**Modules touched:** `modules/similar_search.py`, `modules/mcp_server.py`, optionally `modules/ui/tabs/stacks.py`.

---

## 3. Tag Propagation (label spreading)

**Problem:** Tagging every image with CLIP is slow (GPU-bound). Many images that are visually very similar to already-tagged images could inherit those tags cheaply.

**Idea:** For untagged images, find the k nearest tagged neighbors in embedding space; if they agree on a keyword, propagate it. This could serve as a "quick tag" pre-pass or as a fallback when CLIP is unavailable.

**Where it fits:**

- New function in `modules/tagging.py` (or a helper module): `propagate_tags(k=5, min_similarity=0.85)`.
- Load embeddings and keywords, for each untagged image find k-NN among tagged images, take majority-vote keywords above agreement threshold.
- Could be offered as a "Quick Tag (from neighbors)" button in the tagging UI tab.

**Modules touched:** `modules/tagging.py`, `modules/db.py`, `modules/ui/tabs/tagging.py`.

---

## 4. Outlier / Anomaly Detection

**Problem:** Images that are misfiled, corrupted, or simply "don't belong" in a folder are hard to spot manually in large collections.

**Idea:** For each image in a folder, compute its mean cosine similarity to all other images in the same folder. Flag images whose mean similarity falls below a threshold (e.g., 2 standard deviations below the folder mean) as outliers.

**Where it fits:**

- New function `find_outliers(folder_path, z_threshold=2.0)` in `modules/similar_search.py`.
- Expose via MCP tool and optionally surface in the Stacks tab or a new "Audit" section.

**Modules touched:** `modules/similar_search.py`, `modules/mcp_server.py`.

---

## 5. Embedding-Based 2D Visualization (collection map)

**Problem:** Large collections are hard to browse. A spatial "map" where visually similar images cluster together helps photographers explore and find gaps.

**Idea:** Use UMAP (or t-SNE) to project the 1280-d embeddings to 2D and render an interactive scatter plot in the Web UI, colored by folder/label/rating.

**Where it fits:**

- New API endpoint in `modules/api.py`: `/api/embedding_map?folder=...` returns `[{id, x, y, thumbnail, label, rating}, ...]`.
- Computation: load embeddings via `db.get_embeddings_for_search()`, run `umap.UMAP(n_components=2)`, cache result.
- Frontend: a new Gradio or JS-based scatter plot component in a new UI tab or inside the Stacks tab.
- Dependency: `umap-learn` package.

**Modules touched:** `modules/api.py`, new UI tab or extension of stacks tab, `requirements.txt`.

---

## 6. Smart Stack Representative (centroid-based best-image)

**Problem:** The current "best image" in a stack is the one with the highest `score_general`. This ignores how representative it is of the stack's visual content -- an outlier in the stack might score highest but look nothing like the rest.

**Idea:** Compute the stack centroid (mean embedding), then pick the image closest to the centroid *and* above a minimum score threshold. This balances quality with representativeness.

**Where it fits:**

- Modify or add an alternative to the best-image logic in `modules/clustering.py` (around line 540 where stacks are created and `best_image_id` is set).
- Could be a config toggle: `clustering.best_image_strategy: "score" | "centroid" | "balanced"`.

**Modules touched:** `modules/clustering.py`, config schema.

---

## 7. Cross-Folder "More Like This" Recommendations

**Problem:** The existing `search_similar_images` already supports cross-folder search, but it's only accessible via MCP. Photographers would benefit from a UI-driven "more like this" feature.

**Idea:** Add a "Find Similar" button next to each image in the web UI that calls the existing `search_similar_images()` and displays results in a gallery.

**Where it fits:**

- Add an API route in `modules/api.py`: `/api/similar?image_id=X&limit=20`.
- Wire it into the existing image detail view or gallery context menu in the frontend.
- Backend already exists in `modules/similar_search.py`; this is purely a UI/API wiring task.

**Modules touched:** `modules/api.py`, frontend templates/components.

---

## Summary

| #   | Suggestion                         | Effort | Value   | New Deps     |
| --- | ---------------------------------- | ------ | ------- | ------------ |
| 1   | Diversity-aware selection (MMR)    | Medium | High    | None         |
| 2   | Near-duplicate detection           | Low    | High    | None         |
| 3   | Tag propagation (k-NN)             | Medium | Medium  | None         |
| 4   | Outlier detection                  | Low    | Medium  | None         |
| 5   | 2D embedding map (UMAP)            | High   | Medium  | `umap-learn` |
| 6   | Centroid-based stack representative| Low    | Low-Med | None         |
| 7   | "More Like This" in UI             | Low    | Medium  | None         |

All suggestions reuse the existing `image_embedding` column and `db.get_embeddings_for_search()` infrastructure -- no model changes needed.
