# Import, metadata, thumbnails, and RAW preview

**Purpose:** Register files on disk (including **import/register** flows), extract **EXIF/XMP**, cache structured rows, generate **thumbnails**, and serve **JPEG previews** for RAW formats to browsers and Electron.

**User-visible behavior:** Indexing/metadata phases during runs; on-demand thumbnail generation; `GET /api/raw-preview` for embedded-preview-first RAW serving; optional reverse/forward geocoding on image rows.

**Primary code paths:** `modules/exif_extractor.py`, `modules/xmp.py`, `modules/thumbnails.py`, geocoding under `modules/geocoding/`, indexing/metadata phase executors.

**Main HTTP API (prefix `/api`):**

- **Import:** `POST /import/register`, `POST /import/register/stream` — register paths into the library / indexing scope (see OpenAPI for body)
- **Folders:** `POST /folders/rebuild` — rebuild folder hierarchy metadata when supported by engine
- Image row reads: `GET /api/images`, `GET /api/images/{image_id}`, by hash/UUID variants, `PATCH /api/images/{image_id}`, `DELETE /api/images/{image_id}`
- Cached sidecars: `GET /api/images/{image_id}/exif`, `GET /api/images/{image_id}/xmp`, `POST /api/images/{image_id}/geocode/reverse`, `POST /api/images/{image_id}/geocode/forward`
- `GET /api/raw-preview?path=…` — JPEG bytes for RAW or other files (path resolution mirrors thumbnail endpoint)
- `POST /api/images/generate-thumbnail` — persist thumbnail + update DB paths
- **Public read-only mirror:** `/public/api/images…` (see `create_public_api_router()` in `modules/api.py`)

**Related docs:** [RAW_PROCESSING_GUIDE](../../technical/RAW_PROCESSING_GUIDE.md) · [INBROWSER_RAW_PREVIEW](../../technical/INBROWSER_RAW_PREVIEW.md) · [IMAGE_PIPELINE.md](../../IMAGE_PIPELINE.md)
