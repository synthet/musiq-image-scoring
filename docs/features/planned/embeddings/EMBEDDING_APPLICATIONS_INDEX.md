# Embedding Applications - Detailed Specs

This index breaks out each proposed `image_embedding` use case into a separate implementation document. See the [source document](EMBEDDING_APPLICATIONS.md) for the overview and summary.

## Documents

- [TODO.md](TODO.md) — Index to root backlog (canonical: [TODO.md](../../../TODO.md))
- [01 - Diversity-Aware Selection](EMBEDDING_APP_01_DIVERSITY_SELECTION.md)
- [02 - Near-Duplicate Detection](EMBEDDING_APP_02_NEAR_DUPLICATE_DETECTION.md)
- [03 - Tag Propagation](EMBEDDING_APP_03_TAG_PROPAGATION.md)
- [04 - Outlier Detection](EMBEDDING_APP_04_OUTLIER_DETECTION.md)
- [05 - 2D Embedding Map](EMBEDDING_APP_05_2D_EMBEDDING_MAP.md)
- [06 - Smart Stack Representative](EMBEDDING_APP_06_SMART_STACK_REPRESENTATIVE.md)
- [07 - More Like This UI](EMBEDDING_APP_07_MORE_LIKE_THIS_UI.md)

## Scope and assumptions

- Existing embedding source remains `MobileNetV2` from `modules/clustering.py`.
- Existing storage remains `images.image_embedding` (`BLOB SUB_TYPE 0`).
- Existing retrieval path remains `db.get_embeddings_for_search()`.
- No model retraining is required for any of these items.
