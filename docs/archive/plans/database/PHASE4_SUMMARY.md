---
name: Phase 4 Implementation Summary
description: Complete overview of Phase 4 keyword validation & cleanup work
status: in-progress
---

# Phase 4: Keyword Validation & Cleanup — Implementation Summary

**Date:** 2026-04-02  
**Status:** ✅ Tooling & planning complete; ready for execution

---

## What Was Done

### 1. **Consistency Check Tooling** ✅

**File:** `scripts/db/phase4_consistency_check.py`

- Verifies `IMAGES.KEYWORDS` (legacy) matches `IMAGE_KEYWORDS`/`KEYWORDS_DIM` (normalized)
- Works with both PostgreSQL and Firebird backends
- Reports mismatches and missing normalized rows
- Provides table statistics (`total_keywords`, `total_keyword_links`, etc.)

**How to run:**
```bash
python scripts/db/phase4_consistency_check.py
```

---

### 2. **Performance Benchmarking** ✅

**File:** `scripts/db/phase4_performance_benchmark.py`

- Measures keyword search latency on both paths:
  - Legacy: `IMAGES.KEYWORDS LIKE %keyword%`
  - Normalized: `IMAGE_KEYWORDS JOIN KEYWORDS_DIM`
- Tests with sample keywords (5 runs each, median + stdev reported)
- Compares against target: **<150ms at 50K+ images**

**How to run:**
```bash
python scripts/db/phase4_performance_benchmark.py
```

**Expected output:**
```
Keyword                  Legacy (ms)        Normalized (ms)     Ratio
nature                   45.12              32.45               1.39x
wildlife                 52.34              38.91               1.35x
landscape                41.23              29.87               1.38x
...
Average                  47.45              33.51               1.42x
✅ PASS: Normalized path averages 33.51ms (target: <150ms)
```

---

### 3. **Keyword Discovery Optimization** ✅

**File:** `modules/keyword_discovery.py`

Optimized queries using `KEYWORDS_DIM` directly instead of scanning `IMAGES` table:

#### Functions provided:

| Function | Use case | Optimization |
|----------|----------|--------------|
| `get_top_keywords(limit, folder_path)` | Keyword cloud | Direct aggregate on `KEYWORDS_DIM` instead of scanning `IMAGES` |
| `search_keywords(search_term, limit)` | Autocomplete | Index on `keyword_norm` + `keyword_display` in `KEYWORDS_DIM` |
| `get_keywords_for_folder(folder_path, limit)` | Folder keyword list | Pre-filtered by folder_id join |
| `get_keyword_cooccurrence(keyword, limit)` | Related keywords | Self-join on `image_keywords` + `keywords_dim` |
| `get_keyword_stats()` | Dashboard stats | Single query, no table scans |

**Import and use:**
```python
from modules.keyword_discovery import get_top_keywords, search_keywords

# Get top 50 keywords by usage
top_kws = get_top_keywords(limit=50)

# Search for keywords starting with "bird"
results = search_keywords("bird", limit=20)
```

---

### 4. **Deprecation Roadmap** ✅

**File:** `docs/plans/database/PHASE4_KEYWORDS_DEPRECATION.md`

Four-phase timeline for safely removing legacy `IMAGES.KEYWORDS`:

| Phase | Version | Timeline | Action |
|-------|---------|----------|--------|
| **4a** (now) | Current | 2026-04 | Consistency check + benchmarking |
| **4b** | v6.3 | 2026-05 | Switch primary reads to normalized schema |
| **4c** | v6.4 | 2026-06 | Soft deprecation (logging warnings) |
| **4d** | v7.0 | 2026-07+ | Hard deprecation (drop column) |

**Firebird compatibility strategy:**
- Keep dual-write through Phase 4c
- If Electron hasn't migrated by v7.0, provide a parallel `IMAGE_KEYWORDS` table in Firebird
- Document migration deadline in release notes

---

## What's Needed Next

### Immediate (Phase 4a)

1. **Run consistency check:**
   ```bash
   cd /path/to/image-scoring-backend
   python scripts/db/phase4_consistency_check.py
   ```
   - Document results in a new `PHASE4_RESULTS_SNAPSHOT.md`
   - If mismatches found: run `db._backfill_keywords()` and re-check

2. **Run performance benchmark:**
   ```bash
   python scripts/db/phase4_performance_benchmark.py
   ```
   - Document median latencies for all keywords
   - Compare against target (<150ms)
   - Save output to `PHASE4_PERF_BASELINE.txt` for future releases

3. **Identify Electron impact:**
   - Check if Electron still reads `SCORING_HISTORY.FDB`
   - Coordinate with Electron team on Phase 4 timeline

### Phase 4b (v6.3) — Primary Source Cutover

1. **Code audit:** Find all readers of `IMAGES.KEYWORDS`:
   ```bash
   grep -r "\.keywords\|IMAGES\.KEYWORDS\|i\.keywords" --include="*.py"
   ```

2. **Refactor to use normalized schema:**
   - Update `db.get_images_paginated()` to prefer `IMAGE_KEYWORDS`
   - Update API endpoints that filter by keyword
   - Verify gallery UI works with normalized data

3. **Update development guidelines:**
   - Add to `CLAUDE.md`:
     ```
     ## Keyword Storage (Phase 4)
     - Always use `IMAGE_KEYWORDS` for new keyword queries
     - Dual-write is active; legacy `IMAGES.KEYWORDS` is for Firebird only
     - Use `db.update_image_metadata()` for writes (handles dual-write)
     ```

4. **Test thoroughly:**
   - Keyword search / filter in gallery
   - Keyword tagging via API/UI
   - Tag propagation between images

---

## Files Created/Modified

### New files
- ✅ `scripts/db/phase4_consistency_check.py` — Consistency check script
- ✅ `scripts/db/phase4_performance_benchmark.py` — Performance benchmark script
- ✅ `modules/keyword_discovery.py` — Optimized keyword queries
- ✅ `docs/plans/database/PHASE4_KEYWORDS_DEPRECATION.md` — Deprecation roadmap
- ✅ `docs/plans/database/PHASE4_SUMMARY.md` — This summary

### Updated files
- (None yet; Phase 4b will update `CLAUDE.md`, `modules/db.py`, etc.)

---

## Key Metrics

**Performance targets:**
- Normalized keyword search: <150ms at 50K+ images
- Top-N keywords query: <50ms
- Autocomplete response: <100ms

**Data quality targets:**
- 100% consistency between `IMAGES.KEYWORDS` and `IMAGE_KEYWORDS`
- No orphaned keywords (all in use)
- All images with keywords are indexed

---

## Questions for stakeholders

1. **Firebird migration timeline:** Is Electron migrating to PostgreSQL in Phase 4 or later? Affects deprecation urgency.
2. **Gallery compatibility:** Does keyword filtering / cloud display work correctly with the normalized schema?
3. **API contract:** Any external clients reading `IMAGES.KEYWORDS` directly (not via REST API)?

---

## Checklist for Phase 4 Completion

- [ ] Consistency check passed (no mismatches)
- [ ] Performance benchmark shows <150ms normalized path
- [ ] Keyword discovery module tested
- [ ] Electron impact assessed
- [ ] CLAUDE.md updated with keyword guidelines
- [ ] All readers switched to normalized schema
- [ ] Gallery and API tests passing
- [ ] Deprecation roadmap shared with team

---

## Related Documentation

- [NEXT_STEPS.md](NEXT_STEPS.md) — Original Phase 4 requirements
- [DB_VECTORS_REFACTOR.md](DB_VECTORS_REFACTOR.md) — Parallel embedding work (completed)
- [DB_SCHEMA_REFACTOR_PLAN.md](DB_SCHEMA_REFACTOR_PLAN.md) — Overall schema refactor context
- [FIREBIRD_POSTGRES_MIGRATION.md](FIREBIRD_POSTGRES_MIGRATION.md) — Migration status
