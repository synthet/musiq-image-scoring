# Database Refactor: Remaining Next Steps

## Current Status (as of 2026-04-10)
- **Phase 1 (Integrity):** ✅ Complete.
- **Phase 2 (Normalization):** ✅ Complete.
  - `update_image_field` now calls `_sync_image_keywords` for keyword updates.
  - `_backfill_image_xmp` implemented (runs at startup for remaining images).
- **Phase 3 (Query Refactor):** ✅ Complete.
  - All 6 `keywords LIKE ?` locations replaced with `EXISTS` on `IMAGE_KEYWORDS`/`KEYWORDS_DIM`.
  - New `_add_keyword_filter()` helper centralizes the pattern.
- **Phase 4 (Validation & Cleanup):** ✅ **4a–4c complete** on the Python side (primary reads, soft-deprecation logging); **4d** (hard removal of legacy `IMAGES.KEYWORDS`) scheduled for v7.0 (July 2026). See [PHASE4_KEYWORDS_HUB.md](PHASE4_KEYWORDS_HUB.md), [PHASE4_STATUS_SUMMARY.md](PHASE4_STATUS_SUMMARY.md), [DB_STATUS_REPORT.md](DB_STATUS_REPORT.md).
- **Phase 5 (PostgreSQL Optimizations):** 🔲 Planned — **high-priority** items include embedding storage consolidation and status integrity constraints; see [POSTGRES_SCHEMA_OPTIMIZATIONS.md](POSTGRES_SCHEMA_OPTIMIZATIONS.md).

---

## Phase 4: Remaining work (ongoing + scheduled)

**Done (Python / catalog):** consistency scripts, performance benchmarks, keyword discovery via `KEYWORDS_DIM`, primary read cutover, soft-deprecation warnings (Phases 4a–4c).

**Ongoing / optional verification:** spot-checks that sampled rows stay in parity; large-corpus keyword search latency checks; manual WebUI/API keyword edits when upgrading deployments.

**Scheduled:** Phase **4d** — remove writable/legacy `IMAGES.KEYWORDS` column (v7.0). Coordinate **Electron** normalized-keyword read path with [AGENT_COORDINATION.md](../../technical/AGENT_COORDINATION.md) before hard removal.

---

## Verification Plan
1. **Manual Test:** Update an image keyword via WebUI/API and verify changes in both `IMAGES` and `IMAGE_KEYWORDS` tables.
2. **SQL Audit:** Run `SELECT COUNT(*) FROM IMAGE_KEYWORDS` to verify population.
3. **XMP Coverage:** Run `SELECT COUNT(*) FROM images i LEFT JOIN image_xmp x ON i.id = x.image_id WHERE x.image_id IS NULL AND (i.rating IS NOT NULL OR i.keywords IS NOT NULL)` — should return 0.
4. **Performance Test:** Execute a keyword search with 50,000+ images and measure latency improvements.

---

## Related: PostgreSQL and migration history

The normalized `IMAGE_KEYWORDS` / `KEYWORDS_DIM` / `IMAGE_XMP` tables exist in the Postgres
schema (`modules/db_postgres.py` `init_db()`).

See [`FIREBIRD_POSTGRES_MIGRATION.md`](FIREBIRD_POSTGRES_MIGRATION.md) for full history. The
Python backend is **PostgreSQL-native**; Firebird runtime and dual-write were decommissioned.
The function `_translate_fb_to_pg()` in `modules/db.py` remains as a **SQL dialect helper**
for legacy Firebird-style queries routed through the Postgres adapter — it is not a
dual-write gate.

**Electron / gallery:** The desktop app uses PostgreSQL (or backend `api` SQL mode); legacy Firebird runtime in the gallery is removed. Coordinate **normalized keyword** query shapes and any schema contract changes with [`AGENT_COORDINATION.md`](../../technical/AGENT_COORDINATION.md), especially ahead of Phase **4d** (legacy column removal).

---

## New Horizon: PostgreSQL Native Optimizations

With the primary migration to PostgreSQL complete, the focus shifts to native optimizations (JSONB, Vector tuning, the status fact table, etc.). 

See the detailed **[PostgreSQL Optimization Roadmap](POSTGRES_SCHEMA_OPTIMIZATIONS.md)** for more details.
