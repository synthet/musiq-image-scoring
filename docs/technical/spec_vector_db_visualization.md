# Vector DB Visualization (Legacy Specification)

> [!NOTE]
> This feature was removed on 2026-04-28 due to UX/UI limitations. This document serves as a reference for the technical implementation.

## Overview

The "Vector DB" feature provides a 2D interactive map of image embeddings. It allows users to visually explore the similarity between images in a high-dimensional space by projecting them into two dimensions.

## Architecture

### Frontend Components

- **EmbeddingsPage** (`frontend/src/pages/EmbeddingsPage.tsx`): The main container that manages state for selection, hover, and projection parameters.
- **ScatterCanvas** (`frontend/src/components/embeddings/ScatterCanvas.tsx`): A high-performance HTML5 Canvas-based renderer for thousands of points. Supports zooming, panning, and hit detection.
- **ControlsBar** (`frontend/src/components/embeddings/ControlsBar.tsx`): Interface for adjusting UMAP/t-SNE parameters and selecting embedding spaces.
- **SidePanel** (`frontend/src/components/embeddings/SidePanel.tsx`): Displays the selected image and its metadata.
- **HoverTooltip** (`frontend/src/components/embeddings/HoverTooltip.tsx`): Real-time tooltip showing image previews on hover.

### Backend Endpoints

- `GET /api/embedding_map`: The primary projection endpoint.
    - Parameters: `folder_path`, `method` (umap/tsne), `sample_limit`, `n_neighbors`, `min_dist`, `space_code`, `pca_dim`.
    - Returns: A list of points `{image_id, x, y}` and metadata.
- `GET /api/embedding_spaces`: Returns available embedding models (MobileNetV2, CLIP, etc.).

### Projection Logic (`modules/projections.py`)

The projection process follows these steps:
1. **Fetching Embeddings**: Loads high-dimensional vectors from the database (PostgreSQL `vector` columns or fallback storage).
2. **PCA Pre-reduction**: Optional step to reduce dimensions to ~50 using PCA to speed up UMAP/t-SNE.
3. **Dimensionality Reduction**:
    - **UMAP**: Uniform Manifold Approximation and Projection. Preferred for preserving global structure and speed.
    - **t-SNE**: t-distributed Stochastic Neighbor Embedding. Good for local clusters but slower.
4. **Caching**: Results are cached in `.cache/embedding_map/` based on a hash of the input parameters to avoid recomputing expensive projections.

## Technical Dependencies

- **Frontend**: `react-router-dom`, `@tanstack/react-query`, `lucide-react`, `clsx`.
- **Backend**: `umap-learn`, `scikit-learn`, `numpy`, `pandas`.

## Usage Flow

1. User selects "Vector DB" from the navigation.
2. The UI fetches the list of available embedding spaces.
3. A projection is requested for the current folder scope.
4. The backend computes or loads the 2D coordinates.
5. The frontend renders the points on a canvas.
6. User can click a point to see the image or hover to see a quick preview.
7. User can find similar images by selecting a point and seeing highlights in the map.
