# Database Refactor Status Report

**Date:** 2026-04-10
**Current Target:** Phase 4 — Validation & Cleanup / Phase 5 — PostgreSQL Optimizations

## Executive Summary
Phases 1–3 are **complete**. Normalized tables exist and are populated, dual-write is active on all write paths, and all keyword queries now use `EXISTS` on the normalized `IMAGE_KEYWORDS`/`KEYWORDS_DIM` tables instead of legacy `LIKE` scans on the `IMAGES.KEYWORDS` BLOB.

---

## Phase 1: Integrity + Index Hardening
**Status:** ✅ COMPLETED

| Task | Status | Evidence |
|------|--------|----------|
| Add `UQ_IMAGES_FILE_PATH` | ✅ | Unique index exists in DB. |
| Add `UQ_IMAGES_IMAGE_UUID`| ✅ | Unique index exists in DB. |
| Add Composite Indexes | ✅ | `IDX_IMAGES_FOLDER_SCORE` and `IDX_IMAGES_STACK_SCORE` are present. |
| Remove Redundant Indexes | ✅ | `IDX_IMAGES_FOLDER_ID` and `IDX_IMAGES_STACK_ID` have been dropped. |
| Repair Orphan Stacks | ✅ | Database health check reports no integrity issues. |

---

## Phase 2: Hybrid 3NF Normalization
**Status:** ✅ COMPLETED

- **Keywords:**
  - `KEYWORDS_DIM` & `IMAGE_KEYWORDS` created. ✅
  - **Backfill:** ~60,200 links created. Population healthy for 45,617 images. ✅
  - **Dual-write:** `upsert_image()` and `update_image_field()` both call `_sync_image_keywords()`. ✅
- **Metadata (XMP):**
  - `IMAGE_XMP` created. ✅
  - **Backfill:** `_backfill_image_xmp()` implemented and runs at startup to populate remaining records. ✅
- **Stack Cache:**
  - `STACK_CACHE` created and has 8,500 records. ✅

> [!NOTE]
> The system uses application-layer dual-writes (`modules/db.py`) for `IMAGE_KEYWORDS` and `IMAGE_XMP` synchronization. No DB triggers are used.

---

## Phase 3: Query Refactor in App
**Status:** ✅ COMPLETED

All keyword queries now use the `_add_keyword_filter()` helper which generates:
```sql
EXISTS (SELECT 1 FROM image_keywords ik
  JOIN keywords_dim kd ON ik.keyword_id = kd.keyword_id
  WHERE ik.image_id = images.id AND kd.keyword_norm LIKE ?)
```

| Function | File | Status |
|----------|------|--------|
| `get_image_count()` | `modules/db.py` | ✅ Refactored |
| `get_images_paginated()` | `modules/db.py` | ✅ Refactored |
| `get_images_paginated_with_count()` | `modules/db.py` | ✅ Refactored |
| `get_filtered_paths()` | `modules/db.py` | ✅ Refactored |
| `_build_export_where_clause()` | `modules/db.py` | ✅ Refactored |
| `query_images()` | `modules/mcp_server.py` | ✅ Refactored |

---

## Phase 5: PostgreSQL Native Optimizations
**Status:** 🔲 PLANNED

| Category | Goal | Priority |
|----------|------|----------|
| **Vectors** | Consolidate to `image_embeddings` table; drop redundant indexes. | High |
| **Storage** | Migrate `scores_json` and `metadata` to `JSONB`. | Medium |
| **Integrity** | Enforce status `CHECK` constraints (jobs, phases). | High |
| **Schema** | Use composite PK for `image_phase_status`. | Medium |

See **[POSTGRES_SCHEMA_OPTIMIZATIONS.md](POSTGRES_SCHEMA_OPTIMIZATIONS.md)** for the full roadmap.

---

## Next Recommended Steps

1. **Validate data consistency:** Run spot-checks to confirm `IMAGE_KEYWORDS` data matches `IMAGES.KEYWORDS` for sampled images.
2. **Performance benchmarking:** Measure keyword search latency with 50K+ images and compare to baseline.
3. **Keyword discovery optimization:** Update keyword cloud generation to query `KEYWORDS_DIM` directly instead of scanning the `IMAGES` table.
4. **Phase 4 (Cutover):** After validation, plan deprecation of `IMAGES.KEYWORDS` as a writable column.
