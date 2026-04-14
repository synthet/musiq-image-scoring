---
name: Phase 4b Implementation Steps & Checklist
description: Detailed executable guide for Phase 4b COALESCE refactoring
status: draft
---

# Phase 4b: Detailed Implementation Steps & Checklist

**Date:** 2026-04-02  
**Purpose:** Step-by-step guide to execute Phase 4b refactoring  
**Status:** Ready for implementation

---

## Overview

This guide provides:
- ✅ Code templates for both Postgres and Firebird
- ✅ SQL snippets (copy-paste ready)
- ✅ Testing checklist per function
- ✅ Validation & performance verification
- ✅ Code review checklist
- ✅ Release steps
- ✅ Rollback procedure

**Total effort:** 4-7 hours / 1 day  
**Risk level:** Low (Firebird-verified, backward compatible)

---

## Part 1: Refactor `get_image_details(file_path)`

**File:** `modules/db.py:5021`  
**Impact:** Gallery detail panel + API reads + MCP tools  
**Effort:** 1-2 hours (incl. testing)

### Step 1.1: Understand Current Code

```python
# Current implementation (line 5021-5030)
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

**Current behavior:**
- Returns all columns from `images` table
- `data['keywords']` contains legacy `IMAGES.KEYWORDS` column value
- Gallery displays this legacy value to user

**Goal:** Replace with normalized keywords from `IMAGE_KEYWORDS`

### Step 1.2: Create New Implementation

**Option:** Replace legacy with COALESCE (normalized preferred, fallback legacy)

#### New Code (Postgres Path)

```python
def get_image_details(file_path):
    """
    Returns image details with keywords from normalized schema (Postgres)
    or legacy column (Firebird). Fallback chain: normalized → legacy → empty
    """
    if _get_db_engine() == "postgres":
        # Postgres: fetch all columns, replace keywords with COALESCE
        sql = f"""
            SELECT 
                i.id, i.file_path, i.file_name, i.folder_id, i.stack_id,
                i.image_embedding, i.rating, i.label, i.title, i.description,
                i.metadata, i.scores_json, i.created_at, i.updated_at,
                COALESCE(
                    (SELECT STRING_AGG(COALESCE(kd.keyword_display, kd.keyword_norm), ', ')
                     FROM image_keywords ik 
                     JOIN keywords_dim kd ON ik.keyword_id = kd.keyword_id
                     WHERE ik.image_id = i.id),
                    i.keywords, ''
                ) AS keywords
            FROM images i
            WHERE i.file_path = %s
        """
        try:
            import psycopg2.extras
            with db_postgres.PGConnectionManager() as pg_conn:
                with pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql, (file_path,))
                    row = cur.fetchone()
        except Exception as e:
            logging.error(f"get_image_details Postgres: {e}")
            row = None
    else:
        # Firebird: same COALESCE logic with LIST()
        sql = """
            SELECT 
                i.id, i.file_path, i.file_name, i.folder_id, i.stack_id,
                i.image_embedding, i.rating, i.label, i.title, i.description,
                i.metadata, i.scores_json, i.created_at, i.updated_at,
                COALESCE(
                    (SELECT LIST(COALESCE(kd.keyword_display, kd.keyword_norm), ', ')
                     FROM image_keywords ik 
                     JOIN keywords_dim kd ON ik.keyword_id = kd.keyword_id
                     WHERE ik.image_id = i.id),
                    i.keywords, ''
                ) AS keywords
            FROM images i
            WHERE i.file_path = ?
        """
        row = get_connector().query_one(sql, (file_path,))
    
    if not row:
        return {}
    
    data = dict(row)
    data['file_paths'] = get_all_paths(data['id'])
    data['resolved_path'] = get_resolved_path(data['id'], verified_only=False)
    return data
```

### Step 1.3: Implementation Checklist

- [ ] **Step 1.3a:** Back up current code
  ```bash
  git diff modules/db.py > /tmp/get_image_details.patch
  ```

- [ ] **Step 1.3b:** Import required modules at top of file (if not present)
  ```python
  import psycopg2.extras  # Add near line 1 if missing
  import logging  # Already present
  from modules import db_postgres  # Already present
  ```

- [ ] **Step 1.3c:** Locate current `get_image_details()` (line 5021)
  ```bash
  grep -n "^def get_image_details" modules/db.py
  ```

- [ ] **Step 1.3d:** Replace function with new implementation
  - Open `modules/db.py`
  - Find line 5021 (def get_image_details)
  - Replace lines 5021-5030 with code from Step 1.2
  - Save file

- [ ] **Step 1.3e:** Verify syntax
  ```bash
  python -m py_compile modules/db.py
  ```

### Step 1.4: Testing `get_image_details()`

#### Test 1.4a: Unit Test (Local)

```python
# In Python REPL or test file
from modules import db

# Get a known image path
test_path = "path/to/image.jpg"

# Call function
result = db.get_image_details(test_path)

# Verify structure
assert isinstance(result, dict), "Result should be dict"
assert 'keywords' in result, "Result should have keywords key"
assert 'id' in result, "Result should have id"
assert 'file_path' in result, "Result should have file_path"

# Verify keywords are string (even if empty)
assert isinstance(result.get('keywords'), str), f"Keywords should be string, got {type(result['keywords'])}"

print(f"✅ Unit test passed")
print(f"   Image: {result['file_path']}")
print(f"   Keywords: {result['keywords']}")
```

#### Test 1.4b: Gallery Display Test (Manual)

```bash
# Start the WebUI
python webui.py

# Navigate to Gallery tab
# Select an image with keywords
# Verify:
#   ✅ Keywords display correctly
#   ✅ Keywords match expected values (from KEYWORDS_DIM)
#   ✅ No database errors in console
#   ✅ Loading time is acceptable (<2 seconds)

# Test with image without keywords
# Verify:
#   ✅ Empty keywords display as blank (not error)
```

#### Test 1.4c: API Test

```bash
# Test PATCH endpoint
curl -X PATCH http://localhost:7860/api/images/1 \
  -H "Content-Type: application/json" \
  -d '{"keywords": "nature,wildlife"}'

# Verify:
#   ✅ Returns 200 OK
#   ✅ Keywords updated in database
#   ✅ Gallery reflects new keywords
```

#### Test 1.4d: Performance Test

```bash
# Compare before/after
python -c "
import time
from modules import db

test_path = 'path/to/image.jpg'

# Warm up
db.get_image_details(test_path)

# Measure
start = time.time()
for _ in range(10):
    result = db.get_image_details(test_path)
elapsed = (time.time() - start) / 10 * 1000

print(f'Average time: {elapsed:.2f}ms')
print(f'Target: <100ms')
print(f'Status: {\"✅ PASS\" if elapsed < 100 else \"❌ FAIL\"}')"
```

#### Test 1.4e: Firebird Compatibility (Optional)

If Firebird available:

```bash
# Set engine to Firebird in config.json
"engine": "firebird"

# Restart webui
python webui.py

# Run gallery display test again
# Verify keywords display correctly on Firebird
```

**Expected results:**
- ✅ All tests pass
- ✅ Keywords from normalized schema displayed
- ✅ Performance acceptable (<100ms)
- ✅ No errors in logs

---

## Part 2: Refactor `get_images_by_folder(folder_path)`

**File:** `modules/db.py:3610`  
**Impact:** Folder tree navigation + batch operations  
**Effort:** 1-2 hours (same pattern as Part 1)

### Step 2.1: Understand Current Code

```python
# Current implementation (line 3610-3635)
def get_images_by_folder(folder_path):
    """
    Returns all images located immediately in the specified folder using folder_id.
    Results are cached for up to _FOLDER_CACHE_TTL seconds to avoid redundant
    DB round-trips (e.g. folder tree selection followed by "Open in..." navigation).
    """
    folder_path = os.path.normpath(folder_path)

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

    result = list(get_connector().query(
        "SELECT * FROM images WHERE folder_id = ? ORDER BY file_name", (folder_id,)
    ))
    _folder_images_cache[folder_path] = (now, result)
    return result
```

**Current behavior:**
- Returns all columns via `SELECT *`
- Keywords column contains legacy value
- Results are cached

**Goal:** Replace keywords column with COALESCE (same as Part 1)

### Step 2.2: Create New Implementation

#### New Code (Both Postgres and Firebird)

```python
def get_images_by_folder(folder_path):
    """
    Returns all images located immediately in the specified folder using folder_id.
    Keywords are from normalized schema (IMAGE_KEYWORDS) with fallback to legacy column.
    Results are cached for up to _FOLDER_CACHE_TTL seconds.
    """
    folder_path = os.path.normpath(folder_path)

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
                i.id, i.file_path, i.file_name, i.folder_id, i.stack_id,
                i.image_embedding, i.rating, i.label, i.title, i.description,
                i.metadata, i.scores_json, i.created_at, i.updated_at,
                COALESCE(
                    (SELECT STRING_AGG(COALESCE(kd.keyword_display, kd.keyword_norm), ', ')
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
                i.id, i.file_path, i.file_name, i.folder_id, i.stack_id,
                i.image_embedding, i.rating, i.label, i.title, i.description,
                i.metadata, i.scores_json, i.created_at, i.updated_at,
                COALESCE(
                    (SELECT LIST(COALESCE(kd.keyword_display, kd.keyword_norm), ', ')
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

### Step 2.3: Implementation Checklist

- [ ] **Step 2.3a:** Locate current function (line 3610)
  ```bash
  grep -n "^def get_images_by_folder" modules/db.py
  ```

- [ ] **Step 2.3b:** Replace function with new implementation
  - Open `modules/db.py`
  - Find line 3610 (def get_images_by_folder)
  - Replace lines 3610-3635 with code from Step 2.2
  - Save file

- [ ] **Step 2.3c:** Verify syntax
  ```bash
  python -m py_compile modules/db.py
  ```

### Step 2.4: Testing `get_images_by_folder()`

#### Test 2.4a: Unit Test

```python
# In Python REPL
from modules import db
import os

# Use a test folder path
test_folder = "D:\\Photos\\test"  # or /mnt/d/Photos/test on WSL

# Call function
result = db.get_images_by_folder(test_folder)

# Verify structure
assert isinstance(result, list), "Result should be list"
if len(result) > 0:
    first = result[0]
    assert 'keywords' in first, "Result items should have keywords key"
    assert 'file_path' in first, "Result items should have file_path"
    assert isinstance(first['keywords'], str), "Keywords should be string"
    print(f"✅ Unit test passed ({len(result)} images)")
    print(f"   First image: {first['file_path']}")
    print(f"   Keywords: {first['keywords']}")
else:
    print(f"✅ Unit test passed (0 images in folder)")
```

#### Test 2.4b: Cache Test

```python
# Verify caching works correctly
from modules import db
import time

test_folder = "D:\\Photos\\test"

# First call (cache miss)
start = time.time()
result1 = db.get_images_by_folder(test_folder)
time1 = time.time() - start

# Second call (cache hit)
start = time.time()
result2 = db.get_images_by_folder(test_folder)
time2 = time.time() - start

# Verify
assert result1 == result2, "Results should be identical"
assert time2 < time1, f"Cached call ({time2}ms) should be faster than first call ({time1}ms)"
print(f"✅ Cache test passed")
print(f"   First call: {time1*1000:.2f}ms")
print(f"   Cached call: {time2*1000:.2f}ms (speedup: {time1/time2:.1f}x)")
```

#### Test 2.4c: Folder Navigation Test (Manual)

```bash
# Start WebUI
python webui.py

# In Gallery tab, navigate folder tree:
#   ✅ Click on folder
#   ✅ Images load with keywords
#   ✅ Keywords display correctly
#   ✅ No database errors
#   ✅ Performance is acceptable

# Select folder with many images
#   ✅ First load is normal speed
#   ✅ Clicking again is fast (cached)
```

#### Test 2.4d: Batch Operations Test (Optional)

```python
# If used for batch operations
from modules import db

test_folder = "D:\\Photos\\test"
images = db.get_images_by_folder(test_folder)

# Verify can iterate and access keywords
for img in images[:5]:
    print(f"{img['file_path']}: {img['keywords']}")
```

**Expected results:**
- ✅ All tests pass
- ✅ Keywords from normalized schema
- ✅ Caching works correctly
- ✅ Performance acceptable (<500ms for folders with 100+ images)

---

## Part 3: Validation & Verification

### Step 3.1: Run Phase 4a Tests

After both refactorings complete, run:

```bash
# Consistency check (should still show 0 mismatches)
python scripts/db/phase4_consistency_check.py

# Performance benchmark (verify no regression)
python scripts/db/phase4_performance_benchmark.py

# Expected output:
# ✅ Consistency: 0 mismatches
# ✅ Performance: Normalized path <10ms (no regression)
```

**Acceptance criteria:**
- ✅ 0 consistency mismatches
- ✅ No queries slower than 150ms
- ✅ No performance regression >10% from Phase 4a baseline (7.01ms)

### Step 3.2: Full Integration Test

```bash
# Start fresh WebUI instance
python webui.py

# Test each major feature:
# ✅ Gallery load
# ✅ Select image + view keywords
# ✅ Update keywords via API PATCH
# ✅ Filter by keyword
# ✅ Navigate folders
# ✅ Tag propagation (if available)
# ✅ Check logs for errors

# Monitor performance
# ✅ Gallery page load <2 seconds
# ✅ Image details load <1 second
# ✅ Keyword searches <150ms
```

### Step 3.3: Database Consistency Check

```bash
# After testing, verify database consistency
python -c "
from modules import db_postgres
import psycopg2.extras

# Check for orphaned keywords (keywords_dim rows not in use)
with db_postgres.PGConnectionManager() as conn:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute('''
            SELECT kd.keyword_id, kd.keyword_norm
            FROM keywords_dim kd
            LEFT JOIN image_keywords ik ON kd.keyword_id = ik.keyword_id
            WHERE ik.keyword_id IS NULL
        ''')
        orphaned = cur.fetchall()
        if orphaned:
            print(f'⚠️  Found {len(orphaned)} orphaned keywords')
        else:
            print(f'✅ No orphaned keywords')
        
        # Check for consistency
        cur.execute('''
            SELECT COUNT(*) as c FROM image_keywords ik
            WHERE NOT EXISTS (
                SELECT 1 FROM images i WHERE i.id = ik.image_id
            )
        ''')
        dangling = cur.fetchone()['c']
        if dangling:
            print(f'❌ Found {dangling} dangling image_keywords entries')
        else:
            print(f'✅ No dangling image_keywords entries')
"
```

---

## Part 4: Code Review Checklist

Before merging to main, verify:

### Code Quality

- [ ] SQL syntax is correct (no `%s` in Firebird path, no `?` in Postgres path)
- [ ] COALESCE logic is consistent across functions
- [ ] LIST() used for Firebird, STRING_AGG() for Postgres
- [ ] No hardcoded paths or credentials
- [ ] Error handling in place
- [ ] Logging added for debugging

### Backward Compatibility

- [ ] Callers of `get_image_details()` still work (should be transparent)
- [ ] Callers of `get_images_by_folder()` still work (should be transparent)
- [ ] Cache invalidation logic unchanged
- [ ] API endpoints still return expected JSON structure

### Testing Coverage

- [ ] Unit tests pass
- [ ] Gallery tests pass
- [ ] API tests pass
- [ ] Firebird compatibility (code review at least)
- [ ] Performance baseline verified
- [ ] Consistency check passes (0 mismatches)

### Documentation

- [ ] Code comments explain COALESCE logic
- [ ] CLAUDE.md keywords section still accurate
- [ ] PHASE4B_KEYWORD_READER_AUDIT.md updated with actual results
- [ ] Changelog entry prepared for v6.3

---

## Part 5: Release Steps

### Step 5.1: Pre-Release Validation

```bash
# Run all Phase 4 validation
python scripts/db/phase4_consistency_check.py
python scripts/db/phase4_performance_benchmark.py

# Run test suite
python -m pytest tests/ -m "not gpu and not ml" -v

# Manual smoke test
python webui.py &
# Test gallery load + keyword display
# Test API PATCH
# Check logs
```

### Step 5.2: Create Commit

```bash
git add modules/db.py
git commit -m "feat: Phase 4b keyword primary source cutover

**Primary Source Cutover to Normalized Keywords**

- Refactor get_image_details() to use COALESCE
  * Postgres: STRING_AGG() from IMAGE_KEYWORDS with fallback to legacy
  * Firebird: LIST() from IMAGE_KEYWORDS with fallback to legacy
  * Gallery and API now transparently use normalized keywords

- Refactor get_images_by_folder() with same COALESCE pattern
  * Folder navigation uses normalized keywords
  * Cache invalidation unchanged
  * Performance baseline verified

**Validation Results**

- ✅ Consistency check: 0 mismatches
- ✅ Performance benchmark: No regression (<150ms target)
- ✅ Gallery display: Keywords from KEYWORDS_DIM
- ✅ API endpoints: Updated keywords work correctly
- ✅ Firebird compatibility: Code review verified

**Phase 4b Status**

All Phase 4b must-do refactorings complete:
- ✅ get_image_details() — primary source cutover
- ✅ get_images_by_folder() — primary source cutover
- ✅ All filtering operations — already normalized (unchanged)
- ✅ All tag propagation — already normalized (unchanged)

Normalized IMAGE_KEYWORDS is now primary source for all keyword reads.
Legacy IMAGES.KEYWORDS remains available as fallback through Phase 4c.
Dual-write still active for backward compatibility.

Next: Phase 4c (v6.4) soft deprecation with logging warnings.

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
```

### Step 5.3: Tag Release

```bash
git tag -a v6.3 -m "Phase 4b: Keyword primary source cutover

See PHASE4B_KEYWORD_READER_AUDIT.md (same folder) for details."

git push origin master v6.3
```

### Step 5.4: Update Changelog

Add to CHANGELOG.md or docs/RELEASE_NOTES.md:

```markdown
## v6.3 (2026-04-XX)

### Phase 4b: Keyword Primary Source Cutover

**What Changed:**
- Normalized `IMAGE_KEYWORDS` table is now the primary source for keyword reads
- Gallery displays keywords from normalized schema
- API endpoints transparently use normalized keywords
- Legacy `IMAGES.KEYWORDS` available as fallback for backward compatibility

**Migration Details:**
- `get_image_details()` refactored to use COALESCE(normalized, legacy)
- `get_images_by_folder()` refactored to use COALESCE(normalized, legacy)
- Dual-write remains active (all writes go to both schemas)
- Firebird fallback verified; Postgres is primary

**Performance:**
- Keyword queries: 7-10ms (vs 80+ ms legacy path)
- Gallery load time: <2 seconds (no change)
- Folder navigation: Cache unchanged (fast)

**Testing:**
- Consistency check: 0 mismatches
- Performance benchmark: 12.10x improvement over legacy path
- All manual tests passed

**Next Steps:**
- Phase 4c (v6.4): Soft deprecation with logging warnings
- Phase 4d (v7.0): Hard deprecation (remove legacy column)
```

---

## Part 6: Rollback Procedure

If issues discovered after release:

### Step 6.1: Quick Rollback

```bash
# Revert to previous version
git revert HEAD
git push origin master

# Or reset to tag
git reset --hard v6.2.0
git push origin master -f
```

### Step 6.2: Investigate Issue

```bash
# Check logs for errors
tail -100 .cursor/claude_*

# Run consistency check
python scripts/db/phase4_consistency_check.py

# Check for database corruption
# (run data integrity queries)
```

### Step 6.3: Plan Fix

- Document the issue
- Determine root cause
- Make targeted fix (not full revert)
- Re-test before re-release

---

## Summary Table: What to Execute

| Step | Task | File | Time | Acceptance Criteria |
|------|------|------|------|-------------------|
| 1.1-1.4 | Refactor get_image_details() | modules/db.py:5021 | 1-2h | Gallery displays keywords correctly |
| 2.1-2.4 | Refactor get_images_by_folder() | modules/db.py:3610 | 1-2h | Folder navigation works, cache valid |
| 3.1-3.3 | Validation & verification | scripts/ | 30m | 0 mismatches, no perf regression |
| 4 | Code review | PRs | 1-2h | Team approval |
| 5 | Release as v6.3 | git/tags | 30m | Deployed to production |
| 6 | Rollback (if needed) | git | 15m | Service restored |

**Total estimated time:** 4-7 hours / 1 day work

---

## Before You Start

### Verification Checklist

- [x] Phase 4a validation complete (0 mismatches)
- [x] Firebird compatibility verified
- [x] Code templates reviewed
- [x] SQL snippets copy-paste ready
- [ ] Backup created (optional but recommended)
- [ ] Team notified of planned changes
- [ ] No other DB changes planned simultaneously
- [ ] Test environment ready (WebUI runnable)

---

## During Implementation

### Tip 1: Test Early & Often

Don't wait until all changes complete. Test after each refactoring:
1. Refactor function A → Test function A → Commit
2. Refactor function B → Test function B → Commit
3. Validation suite → Code review → Release

### Tip 2: Keep Fallback Active

Always include Firebird fallback path, even if not testing it. This ensures Phase 4b works for both engines.

### Tip 3: Document Decisions

If you make any deviations from the plan, document them:
- What changed?
- Why?
- What was tested?

### Tip 4: Monitor Performance

Run perf benchmark before & after refactoring:
```bash
python scripts/db/phase4_performance_benchmark.py > /tmp/before.txt
# ... refactor ...
python scripts/db/phase4_performance_benchmark.py > /tmp/after.txt
diff /tmp/before.txt /tmp/after.txt
```

---

## Success Indicators

When Phase 4b is complete:

✅ **Gallery displays keywords correctly**  
✅ **API PATCH works (updates keywords)**  
✅ **Folder navigation works**  
✅ **Consistency check: 0 mismatches**  
✅ **Performance: No regression**  
✅ **All tests passing**  
✅ **Code review approved**  
✅ **Released as v6.3**

---

## References

- PHASE4B_KEYWORD_READER_AUDIT.md — Full audit details
- PHASE4B_FIREBIRD_VERIFICATION.md — Firebird compatibility analysis
- PHASE4_RESULTS_SNAPSHOT.md — Phase 4a results
- PHASE4_KEYWORDS_DEPRECATION.md — Full deprecation timeline
- CLAUDE.md — Keyword storage guidelines (section added)

---

## Next Steps

1. **Review** this checklist
2. **Ask questions** if any steps unclear
3. **Execute** Part 1 (get_image_details refactoring)
4. **Test** Part 1 thoroughly
5. **Execute** Part 2 (get_images_by_folder refactoring)
6. **Test** Part 2 thoroughly
7. **Run** Part 3 (validation suite)
8. **Submit for code review** (Part 4)
9. **Release as v6.3** (Part 5)

Ready to proceed? Let me know if you want to start with Step 1.1!
