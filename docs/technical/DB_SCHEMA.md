# Firebird Database Schema

This document describes the schema of the Image Scoring Firebird database (`scoring_history.fdb`).

## Overview

| Property | Value |
|----------|-------|
| **Database file** | `scoring_history.fdb` (project root) |
| **Engine** | Firebird 5.0.x |
| **Access** | Via `modules/db.py` → `get_db()` |
| **Charset** | UTF8 |

## Entity Relationship Diagram

```
                    ┌─────────────┐
                    │   FOLDERS   │
                    └──────┬──────┘
                           │ parent_id (self-ref)
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
┌───────────────┐   ┌─────────────┐   ┌─────────────────┐
│    IMAGES     │◄───│   STACKS    │   │ CULLING_SESSIONS│
└───────┬───────┘   └─────────────┘   └────────┬────────┘
        │                     ▲                │
        │ folder_id           │ best_image_id   │
        │                     │                │
        │              ┌───────┴────────┐       │
        │              │  CULLING_PICKS │◄──────┘
        │              └───────┬────────┘
        │                      │ image_id
        └──────────────────────┘
        
        │
        ├──────────────────┬──────────────────┐
        ▼                  ▼                  ▼
┌───────────────┐   ┌─────────────┐   ┌─────────────┐
│  FILE_PATHS   │   │ IMAGE_EXIF  │   │ IMAGE_XMP   │
└───────────────┘   └─────────────┘   └─────────────┘

┌──────────────────┐
│ CLUSTER_PROGRESS │  (standalone)
└──────────────────┘

┌──────────────────┐
│      JOBS        │  (standalone, referenced by IMAGES.job_id)
└──────────────────┘
```

---

## Tables

### IMAGES

Core table storing image metadata and quality scores.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | INTEGER | NO | Primary key (identity) |
| `job_id` | INTEGER | YES | References scoring job |
| `file_path` | VARCHAR(4000) | YES | Original/canonical path |
| `file_name` | VARCHAR(255) | YES | Basename |
| `file_type` | VARCHAR(20) | YES | Extension (e.g. NEF, JPG) |
| `score` | DOUBLE PRECISION | YES | Legacy/combined score |
| `score_general` | DOUBLE PRECISION | YES | General quality (0–1) |
| `score_technical` | DOUBLE PRECISION | YES | Technical quality (0–1) |
| `score_aesthetic` | DOUBLE PRECISION | YES | Aesthetic quality (0–1) |
| `score_spaq` | DOUBLE PRECISION | YES | SPAQ model score |
| `score_ava` | DOUBLE PRECISION | YES | AVA model score |
| `score_koniq` | DOUBLE PRECISION | YES | KonIQ model score |
| `score_paq2piq` | DOUBLE PRECISION | YES | PaQ-2-PiQ model score |
| `score_liqe` | DOUBLE PRECISION | YES | LIQE model score |
| `keywords` | BLOB SUB_TYPE TEXT | YES | Extracted keywords (JSON) |
| `title` | VARCHAR(500) | YES | Caption/title |
| `description` | BLOB SUB_TYPE TEXT | YES | Description |
| `metadata` | BLOB SUB_TYPE TEXT | YES | EXIF/metadata (JSON) |
| `thumbnail_path` | VARCHAR(4000) | YES | Cached thumbnail path |
| `scores_json` | BLOB SUB_TYPE TEXT | YES | Raw scores blob |
| `model_version` | VARCHAR(50) | YES | Scoring model version |
| `rating` | INTEGER | YES | User rating (0–5) |
| `label` | VARCHAR(50) | YES | Color label: Red (reject), Yellow (maybe), Green (reference), Blue (portfolio), Purple (creative) |
| `image_hash` | VARCHAR(64) | YES | Content hash (hex SHA-256); meaning depends on `hash_version` |
| `hash_version` | INTEGER | NO | `1` = full-file hash; `2` = embedded preview payload hash (see `modules/image_identity_hash.py`) |
| `image_uuid` | VARCHAR(36) | YES | Logical id from EXIF / metadata (`generate_image_uuid`); not interchangeable with `image_hash` |
| `folder_id` | INTEGER | YES | FK → FOLDERS.id |
| `stack_id` | INTEGER | YES | FK → STACKS.id |
| `created_at` | TIMESTAMP | YES | Creation timestamp |
| `burst_uuid` | VARCHAR(64) | YES | Burst/stack group UUID |
| `image_embedding` | BLOB SUB_TYPE 0 | YES | MobileNetV2 feature vector (1280 × float32 = 5120 bytes). Populated during clustering; used by similarity search. |

**Indexes:** `IDX_FOLDER_ID`, `IDX_STACK_ID`, `IDX_IMAGE_HASH`, `IDX_BURST_UUID`, `IDX_STACK_SCORE_GENERAL`, partial index on `(image_hash, hash_version)` for lookups (and optional unique constraint on the same pair where `image_hash` IS NOT NULL — see Alembic migrations).

See [API_CONTRACT.md](API_CONTRACT.md) — *Image identity: `image_hash`, `hash_version`, and `image_uuid`* for HTTP and config semantics.

**Foreign keys:** `FK_IMAGES_FOLDERS` → FOLDERS(id) ON DELETE SET NULL

---

### JOBS

Scoring and tagging job queue and history.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | INTEGER | NO | Primary key (identity) |
| `input_path` | VARCHAR(4000) | YES | Input folder path |
| `status` | VARCHAR(50) | YES | pending, running, completed, failed |
| `created_at` | TIMESTAMP | YES | Job start time |
| `completed_at` | TIMESTAMP | YES | Job end time |
| `log` | BLOB SUB_TYPE TEXT | YES | Job log output |

---

### FOLDERS

Folder hierarchy for scanned directories.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | INTEGER | NO | Primary key (identity) |
| `path` | VARCHAR(4000) | YES | Folder path |
| `parent_id` | INTEGER | YES | FK → FOLDERS.id (parent) |
| `is_fully_scored` | INTEGER | YES | 1 if all images scored |
| `is_keywords_processed` | INTEGER | YES | 1 if keywords extracted |
| `created_at` | TIMESTAMP | YES | Creation timestamp |

**Foreign keys:** `FK_FOLDERS_PARENT` → FOLDERS(id) ON DELETE CASCADE

---

### STACKS

Image clusters (e.g. burst sequences, similar shots).

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | INTEGER | NO | Primary key (identity) |
| `name` | VARCHAR(255) | YES | Stack identifier |
| `best_image_id` | INTEGER | YES | Image with highest score |
| `created_at` | TIMESTAMP | YES | Creation timestamp |

---

### FILE_PATHS

Resolved paths for images (WSL, Windows, etc.). Multiple paths per image.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | INTEGER | NO | Primary key (identity) |
| `image_id` | INTEGER | NO | FK → IMAGES.id |
| `path` | VARCHAR(4000) | YES | Resolved path |
| `last_seen` | TIMESTAMP | YES | Last verification time |
| `path_type` | VARCHAR(10) | YES | 'WSL' or 'WIN' |
| `is_verified` | SMALLINT | YES | 1 if path exists |
| `verification_date` | TIMESTAMP | YES | When verified |

**Foreign keys:** `FK_FILE_PATHS_IMAGES` → IMAGES(id) ON DELETE CASCADE

**Indexes:** `IDX_FILE_PATHS_IMG_TYPE` (image_id, path_type)

---

### IMAGE_EXIF

Cached EXIF metadata for gallery filtering and sorting. One row per image. Populated during scoring pipeline or via `scripts/maintenance/backfill_exif_xmp.py`.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `image_id` | INTEGER | NO | Primary key, FK → IMAGES.id ON DELETE CASCADE |
| `make` | VARCHAR(100) | YES | Camera manufacturer |
| `model` | VARCHAR(200) | YES | Camera model |
| `lens_model` | VARCHAR(255) | YES | Lens model |
| `focal_length` | VARCHAR(50) | YES | Focal length (e.g. "600 mm") |
| `focal_length_35mm` | SMALLINT | YES | 35mm equivalent |
| `date_time_original` | TIMESTAMP | YES | Capture date |
| `create_date` | TIMESTAMP | YES | Fallback date |
| `exposure_time` | VARCHAR(30) | YES | Shutter speed |
| `f_number` | VARCHAR(20) | YES | Aperture |
| `iso` | INTEGER | YES | ISO sensitivity (INTEGER for high ISO e.g. 51200) |
| `exposure_compensation` | VARCHAR(20) | YES | EV compensation |
| `image_width` | INTEGER | YES | Pixel width |
| `image_height` | INTEGER | YES | Pixel height |
| `orientation` | SMALLINT | YES | Rotation (1–8) |
| `flash` | SMALLINT | YES | Flash status |
| `image_unique_id` | VARCHAR(64) | YES | For dedup/UUID |
| `shutter_count` | INTEGER | YES | Shutter count |
| `sub_sec_time_original` | VARCHAR(10) | YES | Sub-second precision |
| `extracted_at` | TIMESTAMP | YES | When cached |

**Indexes:** `date_time_original`, `make`, `model`, `lens_model`, `iso`

---

### IMAGE_XMP

Cached XMP sidecar metadata. One row per image. Populated during scoring or backfill. Used for Lightroom sync and burst/stack grouping.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `image_id` | INTEGER | NO | Primary key, FK → IMAGES.id ON DELETE CASCADE |
| `rating` | SMALLINT | YES | 0–5 (sync with IMAGES.rating) |
| `label` | VARCHAR(50) | YES | Color label |
| `pick_status` | SMALLINT | YES | 1=picked, -1=reject, 0=unflagged |
| `burst_uuid` | VARCHAR(64) | YES | Stack/burst grouping |
| `stack_id` | VARCHAR(64) | YES | MicrosoftPhoto:StackId |
| `keywords` | BLOB SUB_TYPE TEXT | YES | dc:subject (JSON array) |
| `title` | VARCHAR(500) | YES | xmp:Title |
| `description` | BLOB SUB_TYPE TEXT | YES | xmp:Description |
| `create_date` | TIMESTAMP | YES | xmp:CreateDate |
| `modify_date` | TIMESTAMP | YES | xmp:ModifyDate |
| `extracted_at` | TIMESTAMP | YES | When cached |

**Indexes:** `burst_uuid`, `pick_status`

---

### CULLING_SESSIONS

Culling workflow sessions.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | INTEGER | NO | Primary key (identity) |
| `folder_path` | VARCHAR(4000) | YES | Folder being culled |
| `mode` | VARCHAR(50) | YES | Session mode |
| `status` | VARCHAR(50) | YES | active, completed |
| `total_images` | INTEGER | YES | Total images |
| `total_groups` | INTEGER | YES | Total groups |
| `reviewed_groups` | INTEGER | YES | Groups reviewed |
| `picked_count` | INTEGER | YES | Picked count |
| `rejected_count` | INTEGER | YES | Rejected count |
| `created_at` | TIMESTAMP | YES | Start time |
| `completed_at` | TIMESTAMP | YES | End time |

---

### CULLING_PICKS

Individual picks/rejects within a culling session.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | INTEGER | NO | Primary key (identity) |
| `session_id` | INTEGER | YES | FK → CULLING_SESSIONS.id |
| `image_id` | INTEGER | YES | FK → IMAGES.id |
| `group_id` | INTEGER | YES | Group within session |
| `decision` | VARCHAR(50) | YES | pick, reject, etc. |
| `auto_suggested` | SMALLINT | YES | 1 if auto-picked |
| `is_best_in_group` | SMALLINT | YES | 1 if best in group |
| `created_at` | TIMESTAMP | YES | Creation timestamp |

**Foreign keys:**
- `FK_CULLING_PICKS_IMAGES` → IMAGES(id) ON DELETE CASCADE
- `FK_CULLING_PICKS_SESSIONS` → CULLING_SESSIONS(id) ON DELETE CASCADE

**Indexes:** `IDX_CULLING_PICKS_SESSION`, `IDX_CULLING_PICKS_IMAGE`

---

### CLUSTER_PROGRESS

Tracks last clustering run per folder.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `folder_path` | VARCHAR(512) | NO | Primary key |
| `last_run` | TIMESTAMP | YES | Last clustering timestamp |

---

## Foreign Key Summary

| Constraint | From | To | On Delete |
|------------|------|-----|-----------|
| FK_IMAGES_FOLDERS | IMAGES.folder_id | FOLDERS.id | SET NULL |
| FK_FOLDERS_PARENT | FOLDERS.parent_id | FOLDERS.id | CASCADE |
| FK_FILE_PATHS_IMAGES | FILE_PATHS.image_id | IMAGES.id | CASCADE |
| FK_CULLING_PICKS_IMAGES | CULLING_PICKS.image_id | IMAGES.id | CASCADE |
| FK_CULLING_PICKS_SESSIONS | CULLING_PICKS.session_id | CULLING_SESSIONS.id | CASCADE |

---

## Index Summary

| Index | Table | Columns |
|-------|-------|---------|
| IDX_FOLDER_ID | IMAGES | folder_id |
| IDX_IMAGES_FOLDER_ID | IMAGES | folder_id |
| IDX_STACK_ID | IMAGES | stack_id |
| IDX_IMAGES_STACK_ID | IMAGES | stack_id |
| IDX_IMAGE_HASH | IMAGES | image_hash |
| IDX_BURST_UUID | IMAGES | burst_uuid |
| IDX_STACK_SCORE_GENERAL | IMAGES | stack_id, score_general |
| IDX_FILE_PATHS_IMG_TYPE | FILE_PATHS | image_id, path_type |
| IDX_CULLING_PICKS_SESSION | CULLING_PICKS | session_id |
| IDX_CULLING_PICKS_IMAGE | CULLING_PICKS | image_id |

---

## Migration Notes

- **RESOLVED_PATHS** (legacy): Migrated into FILE_PATHS with `path_type='WIN'`.
- **Score columns**: Added via migration; `score_general`, `score_technical`, `score_aesthetic` are primary.
- **burst_uuid**: Added for burst/stack grouping.
- Schema initialization and migrations are in `modules/db.py` → `_init_db_impl()`.

---

## See Also

- [MCP Debugging Tools](MCP_DEBUGGING_TOOLS.md) – Database query tools
- [Culling Feature](CULLING_FEATURE.md) – Culling workflow
- [Stacks Manual Management](STACKS_MANUAL_MANAGEMENT.md) – Stack operations
