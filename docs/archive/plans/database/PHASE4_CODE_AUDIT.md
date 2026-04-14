---
name: Phase 4 Code Audit — Keyword Readers & Writers
description: Complete audit of all code paths reading/writing IMAGES.KEYWORDS
status: draft
---

# Phase 4 Code Audit — Keyword Readers & Writers

**Date:** 2026-04-02  
**Scope:** All keyword data access in modules/  
**Goal:** Identify what needs to change for Phase 4b (primary source cutover)

---

## Summary

| Path | Type | Current | Phase 4b Goal | Risk |
|------|------|---------|---------------|------|
| **API: PATCH /api/images/{id}** | Read+Write | Legacy column | Normalized schema | Low (goes through db.update_image_metadata) |
| **API: GET /api/images?keyword=X** | Read (filter) | Normalized | ✅ Already using | None |
| **Gallery: keyword filter** | Read (filter) | Normalized | ✅ Already using | None |
| **Tagging: run_single_image()** | Write | Legacy + dual-write | ✅ Dual-write active | Low |
| **Tag propagation** | Read+Write | Normalized | ✅ Already using | None |
| **MCP: query_images** | Read (filter) | Normalized | ✅ Already using | None |
| **db._backfill_keywords()** | Maintenance | Hybrid | Refactor for Phase 4b | Low |
| **db.list_folder_paths_with_missing_keywords()** | Read | Normalized | ✅ Already using | None |
| **db.repair_dual_write()** | Maintenance | Both | Update for Phase 4b | Low |

---

## Detailed Code Paths

### 1. WRITERS (who updates IMAGES.KEYWORDS)

#### 1.1 `db.update_image_metadata(file_path, keywords, ...)`
**Location:** `modules/db.py:5291`  
**Current behavior:**
```python
def update_image_metadata(file_path, keywords, title, description, rating, label):
    get_connector().execute(
        "UPDATE images SET keywords = ?, title = ?, description = ?, rating = ?, label = ? WHERE file_path = ?",
        (keywords, title, description, rating, label, file_path),
    )
    row = get_connector().query_one("SELECT id FROM images WHERE file_path = ?", (file_path,))
    if row:
        _sync_image_keywords(row["id"], keywords)  # ← Dual-write to IMAGE_KEYWORDS
```

**Status:** ✅ Dual-write working  
**Phase 4b action:** Keep as-is (primary write path for keywords)

---

#### 1.2 `modules/tagging.py:run_single_image()`
**Location:** `modules/tagging.py:730`  
**Current behavior:**
```python
c.execute("UPDATE images SET keywords = ?, title = ?, description = ? WHERE id = ?", 
          (tags_str, title, description, image_id))
c.execute("UPDATE images SET keywords = ? WHERE id = ?", (tags_str, image_id))
```

**Status:** ⚠️ Direct legacy write (no dual-write)  
**Phase 4b action:** Call `_sync_image_keywords()` after write, OR refactor to use `update_image_metadata()`

---

#### 1.3 `db._sync_image_keywords(image_id, keywords_str, source, confidence)`
**Location:** `modules/db.py:8114`  
**Current behavior:**
- Normalizes keywords string into individual keywords
- Creates/updates entries in `keywords_dim` and `image_keywords`
- Called by `update_image_metadata()` (dual-write)

**Status:** ✅ Normalized write working  
**Phase 4b action:** Keep as-is

---

#### 1.4 `db._backfill_keywords()` (Phase 2 initialization)
**Location:** `modules/db.py:8130+`  
**Current behavior:**
- Runs at startup to backfill `IMAGE_KEYWORDS` from `IMAGES.KEYWORDS`
- Handles both Firebird and Postgres

**Status:** ✅ Works for initialization  
**Phase 4b action:** Document as initialization-only; no changes needed

---

### 2. READERS (who reads IMAGES.KEYWORDS)

#### 2.1 `modules/api.py:4351` — PATCH endpoint read
**Location:** `modules/api.py:4351` (in image metadata update endpoint)  
**Current behavior:**
```python
c.execute(
    "SELECT file_path, keywords, title, description, rating, label FROM images WHERE id = ?",
    (image_id,)
)
row = c.fetchone()
current_keywords = row[1] or ""  # ← Reads from legacy column
# ... calls db.update_image_metadata() which dual-writes
```

**Status:** ⚠️ Reads legacy column unnecessarily  
**Phase 4b action:** Could optimize to read from `IMAGE_KEYWORDS` instead, but low priority (only during update)

---

#### 2.2 Gallery filters — `db._add_keyword_filter()`
**Location:** `modules/db.py:587`  
**Current behavior:**
```python
def _add_keyword_filter(conditions, params, keyword_filter, table_ref="images"):
    """Append a keyword EXISTS filter using normalized keyword tables."""
    conditions.append(
        f"EXISTS (SELECT 1 FROM image_keywords ik "
        f"JOIN keywords_dim kd ON ik.keyword_id = kd.keyword_id "
        f"WHERE ik.image_id = {table_ref}.id "
        f"AND kd.keyword_norm LIKE ?)"
    )
```

**Status:** ✅ Already using normalized schema  
**Callers:**
- `get_image_count()` — filter only
- `get_images_paginated()` — filter only
- `get_images_paginated_with_count()` — filter only
- `get_filtered_paths()` — filter only
- `mcp_server.query_images()` — filter only

**Phase 4b action:** No changes needed

---

#### 2.3 Tag propagation — `modules/tagging.py:propagate_tags()`
**Location:** `modules/tagging.py:30+`  
**Current behavior:**
```python
# Get tagged images
c.execute("""
    SELECT i.id, ik.image_id, STRING_AGG(kd.keyword_display, ', ') AS keywords
    FROM images i
    JOIN image_keywords ik ON i.id = ik.image_id
    ...
""")
tagged = c.fetchall()
# Uses IMAGE_KEYWORDS for propagation source
```

**Status:** ✅ Already using normalized schema  
**Phase 4b action:** No changes needed

---

#### 2.4 `db.list_folder_paths_with_missing_keywords(require_embedding: bool)`
**Location:** `modules/db.py:7244`  
**Current behavior:**
```sql
SELECT path FROM folders f
WHERE NOT EXISTS (SELECT 1 FROM image_keywords ik WHERE ik.image_id = i.id)
AND (EXISTS (SELECT 1 FROM image_keywords ik ...) OR (i.keywords IS NOT NULL ...))
```

**Status:** ✅ Uses `COALESCE`-like logic; Postgres branch uses normalized schema  
**Phase 4b action:** Verify Firebird path; may need to add fallback for legacy column

---

#### 2.5 XMP metadata backfill — `db._backfill_image_xmp()`
**Location:** `modules/db.py:8184+`  
**Current behavior:**
```python
c.execute("""
    SELECT i.id, i.rating, i.label, i.keywords, i.title, i.description
    FROM images i
    WHERE ... OR i.keywords IS NOT NULL OR i.title IS NOT NULL ...
""")
```

**Status:** ⚠️ Reads legacy column (for initialization only)  
**Phase 4b action:** No changes needed (init-time only); consider adding normalized schema fallback

---

### 3. KEYWORD DISCOVERY / CLOUD (potential optimization)

#### 3.1 No dedicated "keyword cloud" query found
**Finding:** Searched for `keyword.*cloud`, `cloud.*keyword` — not found in code.  
**Implication:** Gallery probably constructs keyword cloud client-side or no cloud feature yet.

**Phase 4b action:** Use new `modules/keyword_discovery.py` helpers for any future cloud features.

---

## Keyword Filtering Summary

All **filtering** operations already use normalized `IMAGE_KEYWORDS` schema via `_add_keyword_filter()`:

```mermaid
flowchart TD
    API[/API/REST endpoints/]
    Gallery[/Gradio Gallery/]
    MCP[/MCP Tools/]
    
    API --> Filter["_add_keyword_filter()"]
    Gallery --> Filter
    MCP --> Filter
    
    Filter --> "SELECT ... IMAGE_KEYWORDS JOIN KEYWORDS_DIM"
    
    Filter --> "✅ Already using normalized!"
```

---

## Keyword Writing Summary

| Writer | Path | Current | Dual-write? |
|--------|------|---------|-------------|
| API PATCH | `update_image_metadata()` | ✅ Uses | ✅ Via `_sync_image_keywords()` |
| Tagging | `run_single_image()` | ⚠️ Direct | ❌ No (bug!) |
| Tag propagation | `propagate_tags()` | ✅ Uses | ✅ Via `_sync_image_keywords()` |

---

## Issues Found

### Issue 1: Tagging writer bypasses dual-write ⚠️
**Severity:** Medium  
**File:** `modules/tagging.py:730`  
**Problem:**
```python
c.execute("UPDATE images SET keywords = ? WHERE id = ?", (tags_str, image_id))
# Missing: _sync_image_keywords() call
```

**Fix:** Call `_sync_image_keywords()` after write, or refactor to use `update_image_metadata()`.

**Phase 4b action:** Fix this before Phase 4c (soft deprecation).

---

### Issue 2: API reads unnecessary from legacy column
**Severity:** Low  
**File:** `modules/api.py:4351`  
**Problem:** Could read current keywords from `IMAGE_KEYWORDS` instead of legacy column.

**Fix:** Optional optimization; not blocking.

**Phase 4b action:** Consider for Phase 4c (cleanup phase).

---

## Phase 4b Refactoring Plan

### Must-do

1. **Fix `modules/tagging.py:run_single_image()`**
   - Add `_sync_image_keywords()` call after keyword write
   - Or refactor to use `update_image_metadata()`

2. **Verify Firebird compatibility**
   - Check `list_folder_paths_with_missing_keywords()` fallback logic
   - Ensure dual-write skips Firebird if needed

3. **Update CLAUDE.md**
   - Add keyword best practices section
   - Document: "Always use `update_image_metadata()` for keyword writes"

### Nice-to-have

4. **Optimize API read** — fetch from `IMAGE_KEYWORDS` instead of legacy column

5. **Test coverage** — add tests for keyword dual-write consistency

---

## Migration Readiness Checklist

- [ ] Fix tagging writer dual-write issue
- [ ] Verify Firebird fallback paths
- [ ] Run consistency check (scripts/db/phase4_consistency_check.py)
- [ ] Run performance benchmark
- [ ] Update CLAUDE.md
- [ ] Update code comments to mark legacy column as "deprecated after v6.x"
- [ ] All code review checks passing
- [ ] Plan Phase 4c timeline

---

## Next Steps

1. **Implement Phase 4b fixes** (2-3 days):
   - Fix tagging writer
   - Verify fallback paths
   - Update docs

2. **Release as v6.3**:
   - All writers use normalized schema as primary
   - Dual-write still active for backward compatibility

3. **Monitor v6.3** (1-2 weeks):
   - Run consistency checks in production
   - Collect feedback on keyword functionality

4. **Phase 4c (v6.4)** — Soft deprecation:
   - Add logging warnings to legacy reads
   - Announce EOL timeline

5. **Phase 4d (v7.0)** — Hard deprecation:
   - Remove `IMAGES.KEYWORDS` column
   - Remove Firebird keyword compatibility

---

## References

- [PHASE4_KEYWORDS_DEPRECATION.md](PHASE4_KEYWORDS_DEPRECATION.md) — Deprecation timeline
- [PHASE4_SUMMARY.md](PHASE4_SUMMARY.md) — Implementation overview
- [NEXT_STEPS.md](NEXT_STEPS.md) — Original Phase 4 requirements
