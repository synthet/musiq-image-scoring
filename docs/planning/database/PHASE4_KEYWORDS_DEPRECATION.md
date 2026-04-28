---
name: Phase 4 Keywords Deprecation Plan
description: Timeline and strategy for deprecating IMAGES.KEYWORDS legacy column
status: draft
---

# Phase 4: IMAGES.KEYWORDS Deprecation Plan

**Navigation:** [PHASE4_KEYWORDS_HUB.md](PHASE4_KEYWORDS_HUB.md) (index of Phase 4 keyword docs and archived snapshots).

## Current State (as of 2026-04-02)

- **Legacy column:** `IMAGES.KEYWORDS` (TEXT, comma-separated string)
- **Normalized schema:** `KEYWORDS_DIM` + `IMAGE_KEYWORDS` (junction table)
- **Dual-write:** Active in `db.update_image_metadata()` and keyword sync paths
- **Dual-read:** Active in `db.get_images_by_folder()` and similar queries via `_add_keyword_filter()`
- **Tests:** All passing with normalized schema

---

## Deprecation Timeline

### Phase 4a — Validation & Benchmarking (current)

**Goal:** Verify data consistency and performance before deprecation.

- ✅ Data consistency check (`phase4_consistency_check.py`)
- ✅ Performance benchmarking (`phase4_performance_benchmark.py`)
- Target: Normalized path <150ms at 50K+ images

**Exit criteria:**
- No mismatches between legacy and normalized data
- Normalized path meets performance target
- Document baseline for future releases

---

### Phase 4b — Primary Source Cutover (v6.3 candidate)

**Goal:** Make `KEYWORDS_DIM` + `IMAGE_KEYWORDS` the primary source for keyword queries.

1. **Code migration:**
   - Audit all readers: which queries still prefer `IMAGES.KEYWORDS`?
   - Switch `db.get_images_by_folder()` and related getters to query `IMAGE_KEYWORDS` first
   - Keep fallback to legacy column for backward compatibility (Firebird galleries)

2. **Documentation:**
   - Update `CLAUDE.md` development guidelines:
     * "Always use `IMAGE_KEYWORDS` for keyword queries on Postgres"
     * "Legacy `IMAGES.KEYWORDS` is for Firebird compatibility only"

3. **API/UI:**
   - Verify gallery tab, keyword filters, tag propagation use normalized schema
   - Add deprecation warning to MCP `tag_propagation` if it reads legacy column

4. **Electron Compatibility:**
   - If Electron still reads `SCORING_HISTORY.FDB` (Firebird):
     * Create a VIEW `images_legacy` that includes `keywords` column from legacy source
     * Document that Electron views are read-only during transition
   - If Electron has migrated to Postgres:
     * No action needed; it already sees normalized schema

---

### Phase 4c — Soft Deprecation (v6.4)

**Goal:** Log warnings when legacy column is accessed, signal end-of-life.

1. **Code instrumentation:**
   ```python
   # In db.py
   def _read_legacy_keywords(image_id):
       logging.warning(
           "Reading IMAGES.KEYWORDS is deprecated; migrate to IMAGE_KEYWORDS. "
           "Will be removed in v7.0. Image ID: %s", image_id
       )
       # ... read from legacy column
   ```

2. **Changelog entry:**
   - "IMAGES.KEYWORDS deprecated; migrate to IMAGE_KEYWORDS in next major version."

3. **Release notes:**
   - Announce end-of-life date (e.g., v7.0 / 2026-07-01)

---

### Phase 4d — Hard Deprecation (v7.0, ~2026-07)

**Goal:** Remove legacy column and close deprecation window.

1. **Migration script:**
   ```sql
   ALTER TABLE images DROP COLUMN keywords;
   ```

2. **Code cleanup:**
   - Remove all Firebird-specific keyword fallbacks
   - Remove `_read_legacy_keywords()` and related helpers
   - Simplify `db.get_images_by_folder()` (no COALESCE)

3. **Documentation:**
   - Update EMBEDDINGS.md, ARCHITECTURE.md
   - Announce Firebird + legacy keyword schema end-of-life

---

## Implementation Checklist

### Phase 4a (now)

- [ ] Run `scripts/db/phase4_consistency_check.py` against production snapshot
- [ ] Run `scripts/db/phase4_performance_benchmark.py` and document results
- [ ] Identify any remaining Firebird-only code paths for keywords
- [ ] Check Electron `electron/db.ts` for hardcoded column assumptions

### Phase 4b (v6.3 candidate)

- [ ] Audit keyword readers in `modules/db.py`:
  * [ ] `get_images_by_folder()` — switch to normalized if not already
  * [ ] `get_images_by_folder_and_stack()` — same
  * [ ] Tag propagation queries — verify using `IMAGE_KEYWORDS`
  * [ ] Gallery filter in `modules/api.py` — same

- [ ] Update `CLAUDE.md`:
  ```markdown
  ## Keyword Storage
  - **Primary (Postgres):** `IMAGE_KEYWORDS` junction + `KEYWORDS_DIM` catalog
  - **Legacy (Firebird):** `IMAGES.KEYWORDS` text field
  - Always write to `IMAGE_KEYWORDS` for new code; dual-write is active for compatibility
  ```

- [ ] Test with Electron if applicable:
  * Verify gallery keyword filters still work
  * Check keyword autocomplete/suggestions

- [ ] Commit and tag as "feat: normalize keyword queries to PRIMARY source"

### Phase 4c (v6.4)

- [ ] Add deprecation logging to any remaining legacy reads
- [ ] Update CHANGELOG: "Deprecated: IMAGES.KEYWORDS legacy column; EOL in v7.0"
- [ ] Create GitHub issue: "Remove IMAGES.KEYWORDS in v7.0" with removal tasks

### Phase 4d (v7.0)

- [ ] Remove `IMAGES.KEYWORDS` column via Alembic migration
- [ ] Remove all Firebird keyword compatibility code
- [ ] Update docs; mark Firebird as unsupported
- [ ] Close deprecation issue

---

## Firebird Compatibility Strategy

### Current (Phase 4a–4c)

Firebird galleries (Electron) may still read `SCORING_HISTORY.FDB`:

- Keep `IMAGES.KEYWORDS` populated via dual-write
- Provide a VIEW for new code: `SELECT id, ..., keywords FROM images` (backward-compatible interface)
- Document: "Keyword writes go to both `IMAGES.KEYWORDS` and `IMAGE_KEYWORDS` until Phase 4d."

### Future (Phase 4d+)

If Electron hasn't migrated by v7.0:

- Either:
  1. Keep a parallel `IMAGE_KEYWORDS` table in Firebird (if needed for gallery)
  2. Or, treat Firebird as read-only legacy (document migration deadline)

---

## Success Criteria

- ✅ Consistency check passes (no mismatches)
- ✅ Normalized path <150ms at 50K+ images
- ✅ All writers use `db.update_image_metadata()` (which dual-writes)
- ✅ All readers use `db.get_images_by_folder()` or similar (use normalized schema)
- ✅ No hardcoded `IMAGES.KEYWORDS` column access in new code (code review gate)
- ✅ Electron compatibility verified (or migration plan documented)

---

## Related Issues / References

- [NEXT_STEPS.md](NEXT_STEPS.md) — Phase 4 validation & cleanup steps
- [DB_SCHEMA_REFACTOR_PLAN.md](DB_SCHEMA_REFACTOR_PLAN.md) — Overall schema refactor context
- [DB_VECTORS_REFACTOR.md](DB_VECTORS_REFACTOR.md) — Parallel embedding work (not blocking)
- `CLAUDE.md` — Development guidelines (to be updated in Phase 4b)
