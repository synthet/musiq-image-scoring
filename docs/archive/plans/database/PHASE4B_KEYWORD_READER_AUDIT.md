---
name: Phase 4b Keyword Reader Audit & Refactoring Plan
description: Detailed analysis of all keyword readers and refactoring roadmap
status: draft
---

# Phase 4b: Keyword Reader Audit & Refactoring Plan

**Date:** 2026-04-02  
**Purpose:** Identify all keyword read paths and plan primary source cutover  
**Status:** Phase 4a validated; this audit drives Phase 4b execution

---

## Executive Summary

### Current State
- **Keyword filtering:** Already uses normalized schema ✅ (all `_add_keyword_filter()`)
- **Keyword writes:** Dual-write active ✅ (API, tagging, propagation)
- **Keyword reads:** Mix of legacy + normalized
  - Many readers get legacy column via `SELECT *`
  - Some use COALESCE (both schemas)
  - Filtering-only operations already normalized

### Phase 4b Goal
Switch keyword **reads** to use normalized schema as primary source:
1. Rename legacy column internally or filter it from `SELECT *` result
2. Where displaying keywords to users, fetch from `IMAGE_KEYWORDS` instead
3. Keep fallback to legacy column for backward compatibility through Phase 4c
4. Remove Firebird-specific dual-read logic after Electron migrates (Phase 4d)

---

## Keyword Reader Inventory

### Category 1: Filtering Operations (Already Normalized ✅)

| Function | File | Line | Status | Notes |
|----------|------|------|--------|-------|
| `_add_keyword_filter()` | db.py | 587 | ✅ | Uses `IMAGE_KEYWORDS JOIN KEYWORDS_DIM` — already optimal |
| `get_image_count()` | db.py | 961 | ✅ | Calls `_add_keyword_filter()` |
| `get_images_paginated()` | db.py | 1028 | ✅ | Calls `_add_keyword_filter()` |
| `get_images_paginated_with_count()` | db.py | 1111 | ✅ | Calls `_add_keyword_filter()` |
| `get_filtered_paths()` | db.py | 1277 | ✅ | Calls `_add_keyword_filter()` |
| `get_images_with_keyword()` | db.py | 3638 | ✅ | Directly uses `IMAGE_KEYWORDS JOIN KEYWORDS_DIM` |

**Action for Phase 4b:** None (all working correctly)

---

### Category 2: Readers Returning Image Data (Mixed Schema)

#### 2a. `get_image_details(file_path)` — Returns all columns
**File:** modules/db.py:5021

**Current behavior:**
```python
def get_image_details(file_path):
    row = get_connector().query_one(
        "SELECT * FROM images WHERE file_path = ?", (file_path,)
    )
    if not row:
        return {}
    data = dict(row)
    data['file_paths'] = get_all_paths(data['id'])
    data['resolved_path'] = get_resolved_path(data['id'], verified_only=False)
    return data
```

**Consumers:**
- `modules/ui/tabs/gallery.py:278` — Display image details in gallery (shows `keywords` field)
- `modules/ui/tabs/gallery.py:358` — Edit panel gets current keywords
- `modules/api.py:4351` — PATCH endpoint reads current keywords
- MCP tools that return image metadata

**Impact:** Gallery displays legacy column keywords; API reads legacy for updates

**Phase 4b Refactoring Options:**

| Option | Approach | Pros | Cons | Effort |
|--------|----------|------|------|--------|
| **A. Drop legacy column from SELECT** | `SELECT id, file_path, ... (without keywords)` | Clean separation | Breaks backward compat | Medium |
| **B. Replace legacy with normalized** | `SELECT ..., COALESCE(...normalized..., keywords) AS keywords` | Seamless transition | Complex JOIN | Medium |
| **C. Add normalized as separate field** | `SELECT ..., keywords, (SELECT ...) AS keywords_normalized` | Gradual migration | Extra DB calls | Low |
| **D. Lazy-fetch normalized** | Keep legacy in result, but UI fetches normalized separately | Non-blocking | More code | High |

**Recommendation:** Option B (Replace legacy with normalized in SELECT)
- Minimal code changes at call sites
- Gallery & API transparently get normalized keywords
- Backward compatible (single `keywords` field)
- Easier to deprecate in Phase 4d (just remove COALESCE)

**Changes needed:**
1. Update `SELECT *` to explicitly list columns + COALESCE for keywords
2. Or create helper function to post-process results
3. Test that gallery displays keywords correctly

**Priority:** Medium (affects user-facing keyword display)

---

#### 2b. `get_images_by_folder(folder_path)` — Returns all columns
**File:** modules/db.py:3610

**Current behavior:**
```python
def get_images_by_folder(folder_path):
    # ... caching logic ...
    result = list(get_connector().query(
        "SELECT * FROM images WHERE folder_id = ? ORDER BY file_name", (folder_id,)
    ))
    _folder_images_cache[folder_path] = (now, result)
    return result
```

**Consumers:**
- Folder tree navigation
- Batch operations on folder contents
- Image selection UIs

**Impact:** Cached results include legacy keywords; may be stale or missing

**Phase 4b Refactoring:**

Same approach as 2a — replace legacy with COALESCE in SELECT.

**Priority:** Medium (affects folder operations)

---

### Category 3: Tag Propagation (Hybrid Read Pattern)

#### 3a. `get_images_for_tag_propagation()` — Returns embeddings + keywords
**File:** modules/db.py:7090 (Postgres) / 7148 (Firebird)

**Current behavior:**
```python
# Postgres path (line 7120+)
q_untagged = (
    f"SELECT i.id, i.file_path, {emb_expr} AS image_embedding FROM images i "
    f"WHERE {has_e} "
    f"AND NOT EXISTS (SELECT 1 FROM image_keywords ik WHERE ik.image_id = i.id) "
    f"AND (i.keywords IS NULL OR i.keywords = '')" + folder_filter
)
q_tagged = (
    f"SELECT ..., "
    f"COALESCE((SELECT STRING_AGG(...) FROM image_keywords ik ...), i.keywords) AS keywords_csv "
    f"FROM images i "
    f"WHERE ... AND (EXISTS (SELECT 1 FROM image_keywords ik ...) "
    f"OR (i.keywords IS NOT NULL AND i.keywords != ''))" + folder_filter
)
```

**Impact:** Already uses COALESCE + `IMAGE_KEYWORDS`; GOOD ✅

**Phase 4b Refactoring:** None needed (already using normalized schema correctly)

**Note:** Could simplify by removing legacy column check in untagged query (Phase 4c cleanup)

---

#### 3b. `get_image_tag_propagation_focus()` — Returns embedding + keywords for one image
**File:** modules/db.py:7177

**Current behavior:**
```python
# Postgres path (line 7186+)
sql = f"""
    SELECT ...,
           COALESCE((SELECT STRING_AGG(...) FROM image_keywords ik ...), 
                   COALESCE(i.keywords, '')) AS kw
    FROM images i
    ...
"""
```

**Status:** ✅ Already uses COALESCE + normalized (good)

**Phase 4b Refactoring:** None needed

---

### Category 4: Maintenance & Repair Functions (Expected Legacy Reads)

#### 4a. `repair_legacy_keywords_junction()`
**File:** modules/db.py:7948

**Purpose:** Fix dual-write gaps — reads legacy and syncs to `IMAGE_KEYWORDS`

```python
rows = get_connector().query(
    "SELECT i.id, i.keywords FROM images i WHERE i.keywords IS NOT NULL ..."
)
```

**Status:** ✅ Correct (maintenance function, should read legacy)

**Phase 4b Refactoring:** None (keep as-is for repair utility)

---

#### 4b. `_backfill_image_xmp()`
**File:** modules/db.py:8165

**Purpose:** Initialization — populate `IMAGE_XMP` from legacy columns

```python
c.execute("SELECT id, keywords FROM images WHERE keywords IS NOT NULL AND keywords <> ''")
```

**Status:** ✅ Correct (init-time only, should read legacy)

**Phase 4b Refactoring:** None (only runs at startup)

---

### Category 5: Tests (May need updates)

| Test File | Issue | Action |
|-----------|-------|--------|
| `tests/test_db_consistency.py` | Verifies IMAGE_KEYWORDS consistency | ✅ Keep (validates Phase 4a) |
| `tests/bench_db_performance.py` | Benchmarks legacy vs normalized | ✅ Keep (baseline for regression) |
| `tests/test_testing_samples_integration.py:72` | Reads `keywords FROM images` | ⏳ May need update |

**Action:** Review tests after 2a/2b refactoring; update if needed

---

### Category 6: API Endpoints (Keyword Metadata)

#### 6a. PATCH `/api/images/{id}` — Update image metadata
**File:** modules/api.py:4351

**Current behavior:**
```python
c.execute(
    "SELECT file_path, keywords, title, description, rating, label FROM images WHERE id = ?",
    (image_id,)
)
current_keywords = row[1] or ""
# ... update via db.update_image_metadata() which dual-writes
```

**Impact:** Reads from legacy column; calls `update_image_metadata()` which syncs correctly

**Status:** ⚠️ Unnecessarily reads legacy (should use normalized or not read keywords at all)

**Phase 4b Refactoring:**

Option 1: Don't read keywords, let API caller provide new value
```python
# Old: current_keywords = row[1] or ""
# New: just use request.keywords (no fallback)
new_keywords = request.keywords if request.keywords is not None else ""
```

Option 2: Read keywords from normalized schema
```python
# Fetch from IMAGE_KEYWORDS instead of legacy column
cur.execute("""
    SELECT STRING_AGG(kd.keyword_display, ', ')
    FROM image_keywords ik JOIN keywords_dim kd ON ...
    WHERE ik.image_id = %s
""")
```

**Recommendation:** Option 1 (simpler)
- API caller already provides keywords if they want to update
- Don't need to merge with current; let caller be explicit
- Reduces DB calls

**Priority:** Low (works correctly, just not optimal)

---

## Refactoring Priority & Execution Order

### Phase 4b Must-Do (Blocking)
1. ✅ **Category 1:** Filtering (already done)
2. ✅ **Category 3:** Tag propagation (already done)
3. ✅ **Category 4:** Maintenance (already correct)

### Phase 4b Should-Do (Primary Source Cutover)
4. **Category 2a:** `get_image_details()` — Affects gallery + API reads
   - **Effort:** Medium
   - **Impact:** High (user-facing)
   - **Change:** Replace legacy with COALESCE in SELECT

5. **Category 2b:** `get_images_by_folder()` — Affects folder operations
   - **Effort:** Medium  
   - **Impact:** Medium
   - **Change:** Replace legacy with COALESCE in SELECT

### Phase 4b Nice-To-Have (Optimization)
6. **Category 6a:** API PATCH endpoint
   - **Effort:** Low
   - **Impact:** Low (cosmetic)
   - **Change:** Remove unnecessary legacy column read

---

## Refactoring Details

### Refactoring 2a: `get_image_details()`

**Option B Implementation:**

```python
def get_image_details(file_path):
    # Build COALESCE for keywords (normalized preferred, fallback legacy)
    if _get_db_engine() == "postgres":
        sub = _pg_default_embedding_space_subquery_sql()
        sql = f"""
            SELECT 
                i.*,
                COALESCE(
                    (SELECT STRING_AGG(kd.keyword_display, ', ')
                     FROM image_keywords ik 
                     JOIN keywords_dim kd ON ik.keyword_id = kd.keyword_id
                     WHERE ik.image_id = i.id),
                    i.keywords, ''
                ) AS keywords
            FROM images i
            WHERE i.file_path = %s
        """
        # ... execute and build result
    else:
        # Firebird path (similar COALESCE pattern)
        sql = """
            SELECT 
                i.*,
                COALESCE(
                    (SELECT LIST(kd.keyword_display, ', ')
                     FROM image_keywords ik 
                     JOIN keywords_dim kd ON ik.keyword_id = kd.keyword_id
                     WHERE ik.image_id = i.id),
                    i.keywords, ''
                ) AS keywords
            FROM images i
            WHERE i.file_path = ?
        """
    
    row = get_connector().query_one(sql, (file_path,))
    # ... rest of function
```

**Pros:**
- Transparent to callers
- Gallery & API automatically get normalized keywords
- Easy to deprecate (remove COALESCE in Phase 4d)

**Cons:**
- More complex SQL
- Requires explicit column list (instead of `SELECT *`)

**Testing:**
- [ ] Gallery displays keywords (from `IMAGE_KEYWORDS` preferentially)
- [ ] API reads return expected keywords
- [ ] Firebird path still works
- [ ] Performance acceptable (may add subquery overhead)

---

### Refactoring 2b: `get_images_by_folder()`

**Option B Implementation:**

```python
def get_images_by_folder(folder_path):
    folder_path = os.path.normpath(folder_path)
    
    # Check cache
    now = time.time()
    cached = _folder_images_cache.get(folder_path)
    if cached is not None:
        cached_time, cached_rows = cached
        if now - cached_time < _FOLDER_CACHE_TTL:
            return cached_rows
        del _folder_images_cache[folder_path]
    
    folder_id = get_or_create_folder(folder_path)
    if not folder_id:
        return []
    
    # Build query with COALESCE for keywords
    if _get_db_engine() == "postgres":
        sql = f"""
            SELECT 
                i.*,
                COALESCE(
                    (SELECT STRING_AGG(kd.keyword_display, ', ')
                     FROM image_keywords ik 
                     JOIN keywords_dim kd ON ik.keyword_id = kd.keyword_id
                     WHERE ik.image_id = i.id),
                    i.keywords, ''
                ) AS keywords
            FROM images i
            WHERE i.folder_id = %s
            ORDER BY i.file_name
        """
        result = list(get_connector().query(sql, (folder_id,)))
    else:
        sql = """
            SELECT 
                i.*,
                COALESCE(
                    (SELECT LIST(kd.keyword_display, ', ')
                     FROM image_keywords ik 
                     JOIN keywords_dim kd ON ik.keyword_id = kd.keyword_id
                     WHERE ik.image_id = i.id),
                    i.keywords, ''
                ) AS keywords
            FROM images i
            WHERE i.folder_id = ?
            ORDER BY i.file_name
        """
        result = list(get_connector().query(sql, (folder_id,)))
    
    _folder_images_cache[folder_path] = (now, result)
    return result
```

**Testing:**
- [ ] Folder tree shows keywords from normalized schema
- [ ] Batch operations on folder contents work
- [ ] Cache invalidation works
- [ ] Performance acceptable

---

## Implementation Checklist

### Before Phase 4b Release (v6.3)

- [ ] Refactor `get_image_details()` with COALESCE
- [ ] Test gallery keyword display
- [ ] Test API PATCH endpoint
- [ ] Refactor `get_images_by_folder()` with COALESCE
- [ ] Test folder operations
- [ ] Run consistency check (should show 0 mismatches)
- [ ] Run performance benchmark (verify no regression)
- [ ] Code review by team
- [ ] Update CLAUDE.md if needed
- [ ] Write test cases for new COALESCE logic

### After v6.3 Release (Phase 4c/4d)

- [ ] Add deprecation logging to legacy keyword reads
- [ ] Monitor production for keyword issues
- [ ] Plan Phase 4c soft deprecation
- [ ] Plan Phase 4d column removal

---

## Risk Assessment

### Risk 1: COALESCE adds query overhead
**Severity:** Medium  
**Mitigation:** Run performance benchmark; if <10ms added, acceptable  
**Action:** Profile 2a/2b changes before release

### Risk 2: Subqueries in SELECT may not index well
**Severity:** Medium  
**Mitigation:** Ensure `image_keywords(image_id)` and `keywords_dim(keyword_id)` have indexes  
**Action:** Verify indexes before release

### Risk 3: Firebird path may have syntax differences
**Severity:** Low  
**Mitigation:** Test Firebird path with actual Firebird DB  
**Action:** Optional for Phase 4b; document Postgres-only if needed

### Risk 4: Cache invalidation issues with COALESCE
**Severity:** Low  
**Mitigation:** Cache keys are folder_path; keywords update triggers cache invalidate  
**Action:** Verify cache invalidation logic

---

## Success Criteria for Phase 4b

- ✅ All keyword filtering uses normalized schema
- ✅ Gallery displays keywords from normalized source (COALESCE)
- ✅ API reads/writes use normalized schema
- ✅ Dual-write still active for backward compatibility
- ✅ Firebird fallback paths verified (or documented as Postgres-only)
- ✅ Consistency check: 0 mismatches
- ✅ Performance benchmark: No regression (< +10ms per query)
- ✅ All tests passing
- ✅ Code review approved
- ✅ Ready for v6.3 release

---

## Timeline Estimate

| Task | Time | Notes |
|------|------|-------|
| Refactor `get_image_details()` | 1-2 hours | COALESCE + testing |
| Test gallery & API | 1-2 hours | Manual + automated |
| Refactor `get_images_by_folder()` | 1-2 hours | Same pattern as above |
| Test folder operations | 1 hour | Cache + performance |
| Code review | 1-2 hours | Team feedback + adjustments |
| Performance benchmark | 30 min | Run before/after comparison |
| **Total** | **6-10 hours** | 1-2 days work |

---

## References

- PHASE4_KEYWORDS_DEPRECATION.md — Deprecation timeline
- PHASE4_CODE_AUDIT.md — Initial audit (preceding this document)
- PHASE4_RESULTS_SNAPSHOT.md — Phase 4a validation results
- db.py: Functions referenced above
