---
name: Phase 4c Soft Deprecation Plan
description: Logging warnings for IMAGES.KEYWORDS legacy column (v6.4)
status: draft
date: 2026-04-03
---

# Phase 4c: Soft Deprecation — Logging Warnings

**Target Release:** v6.4 (2026-05)  
**Duration:** 1-2 hours  
**Complexity:** Low

---

## Overview

Phase 4b successfully migrated all keyword **reads** to the normalized schema via COALESCE fallback. Phase 4c adds **deprecation logging** to signal that the legacy `IMAGES.KEYWORDS` column will be removed in v7.0.

---

## Goals

1. **Log warnings** when IMAGES.KEYWORDS column is actually read (fallback path triggered)
2. **Document deprecation** in CHANGELOG for v6.4 release
3. **Create removal ticket** for v7.0 work
4. **No code breaks** — fully backward compatible

---

## Implementation

### Step 1: Add Deprecation Helper

In `modules/db.py`, add a helper for logging legacy reads:

```python
def _log_legacy_keyword_access(image_id, context=""):
    """Log warning when legacy IMAGES.KEYWORDS column is accessed.
    
    Args:
        image_id: Image that triggered fallback to legacy column
        context: Function/context name (e.g. "get_image_details")
    """
    logging.warning(
        "⚠️  DEPRECATION: Reading IMAGES.KEYWORDS (legacy). "
        "Migrate to IMAGE_KEYWORDS + KEYWORDS_DIM normalized schema. "
        "Legacy column will be removed in v7.0 (2026-07). "
        "Image ID: %s | Context: %s",
        image_id, context or "unknown"
    )
```

### Step 2: Instrument Fallback Paths

Update both `get_image_details()` and `get_images_by_folder()` to log when the COALESCE fallback reaches the legacy column:

#### In `get_image_details()` (around line 5066)

```python
def get_image_details(file_path):
    """..."""
    if _get_db_engine() == "postgres":
        # ... postgres path ...
        try:
            with db_postgres.PGConnectionManager() as pg_conn:
                with pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(sql, (file_path,))
                    row = cur.fetchone()
        except Exception as e:
            logging.error(f"get_image_details Postgres: {e}")
            row = None
    else:
        # ... firebird path ...
        row = get_connector().query_one(sql, (file_path,))

    if not row:
        return {}

    data = dict(row)
    image_id = data.get('id')
    
    # Log if we hit the legacy fallback (keywords came from i.keywords, not normalized)
    if image_id and data.get('keywords'):
        # Check: did the keywords come from legacy column?
        # This is a heuristic: if IMAGE_KEYWORDS query returned nothing, we fell back
        normalized_kw = get_connector().query_one(
            "SELECT COUNT(*) as cnt FROM image_keywords WHERE image_id = ?",
            (image_id,)
        )
        if not normalized_kw or normalized_kw[0] == 0:
            _log_legacy_keyword_access(image_id, "get_image_details")
    
    data['file_paths'] = get_all_paths(image_id)
    data['resolved_path'] = get_resolved_path(image_id, verified_only=False)
    return data
```

#### In `get_images_by_folder()` (around line 3610)

```python
def get_images_by_folder(folder_path):
    """..."""
    # ... cache logic and folder_id lookup ...
    
    result = list(get_connector().query(sql, (folder_id,)))
    
    # Log legacy fallback for any images that returned keywords
    if result:
        for row in result:
            image_id = row.get('id')
            keywords = row.get('keywords', '')
            if image_id and keywords:
                # Check if normalized source exists
                normalized_count = get_connector().query_one(
                    "SELECT COUNT(*) as cnt FROM image_keywords WHERE image_id = ?",
                    (image_id,)
                )
                if not normalized_count or normalized_count[0] == 0:
                    _log_legacy_keyword_access(image_id, "get_images_by_folder")
    
    _folder_images_cache[folder_path] = (now, result)
    return result
```

---

## Testing

### 1. Enable Debug Logging

```bash
# Set log level to see warnings
export LOG_LEVEL=WARNING

# Start app
python webui.py
```

### 2. Trigger Fallback (Manual)

```bash
# Test with image that has keywords in legacy column but not in normalized
# (Would require seeding data intentionally)

# Or simulate in test:
python -c "
from modules import db
# Call function that reads keywords
details = db.get_image_details('/path/to/image.jpg')
# Should see warning in logs if legacy column was accessed
"
```

### 3. Check Logs

```bash
# View webui.log
tail -50 webui.log | grep "DEPRECATION"

# Expected output:
# ⚠️  DEPRECATION: Reading IMAGES.KEYWORDS (legacy). 
#    Migrate to IMAGE_KEYWORDS + KEYWORDS_DIM normalized schema. 
#    Legacy column will be removed in v7.0 (2026-07). 
#    Image ID: 42 | Context: get_image_details
```

---

## Documentation

### Update CHANGELOG.md

Add to v6.4 section:

```markdown
### Deprecated

- **IMAGES.KEYWORDS legacy column**: Deprecated in v6.4; will be removed in v7.0 (2026-07).
  * Logging warnings added when legacy column is accessed
  * Migrate to `IMAGE_KEYWORDS` + `KEYWORDS_DIM` normalized schema
  * Dual-write remains active for backward compatibility
```

### Update CLAUDE.md

Ensure Keyword Storage section includes deprecation timeline:

```markdown
## Keyword Storage — Deprecation Timeline

**Current state (v6.3–v6.4):** Dual-write and dual-read active

- **Primary source (Postgres):** `IMAGE_KEYWORDS` + `KEYWORDS_DIM` (preferred)
- **Legacy (Firebird):** `IMAGES.KEYWORDS` text field
- **Writes:** Always go to both schemas via `db.update_image_metadata()`
- **Reads:** Prefer normalized schema; fallback to legacy with deprecation warning

**Deprecation schedule:**
- **v6.4 (May 2026):** Soft deprecation — warnings logged
- **v7.0 (July 2026):** Hard deprecation — legacy column removed

**For new code:**
- Always use `db.get_image_details()` / `db.get_images_by_folder()` 
- These transparently use normalized schema with legacy fallback
- No direct `IMAGES.KEYWORDS` column access needed
```

---

## GitHub Issue Template

Create GitHub issue for v7.0 removal:

```
Title: Remove IMAGES.KEYWORDS legacy column in v7.0

Description:

Phase 4d work — hard deprecation of legacy keyword storage.

**Context:**
- Phase 4b (v6.3): Normalized IMAGE_KEYWORDS became primary source
- Phase 4c (v6.4): Soft deprecation with logging warnings
- Phase 4d (v7.0): Remove legacy column and code paths

**Tasks:**
- [ ] Remove IMAGES.KEYWORDS column via Alembic migration
- [ ] Remove `_log_legacy_keyword_access()` helper
- [ ] Simplify `get_image_details()` and `get_images_by_folder()` (no COALESCE)
- [ ] Remove Firebird-specific keyword compatibility code
- [ ] Update docs (CLAUDE.md, deprecation timeline)

**Impact:**
- Firebird support officially ends (Postgres-native only)
- Cleaner code, better performance
- v7.0 release notes announce end-of-life for legacy schema

**Acceptance Criteria:**
- Tests pass with simplified code
- No IMAGES.KEYWORDS references in codebase
- Docs updated to reflect Postgres-only support
```

---

## Rollback (if needed)

Phase 4c has no breaking changes:
- Logging is non-intrusive
- Fallback behavior unchanged
- Easy to disable logging: comment out `_log_legacy_keyword_access()` calls

---

## Timing

**Recommended:**
1. Complete Phase 4b testing and validation (when DB available)
2. Prepare Phase 4c implementation (this plan)
3. Tag v6.3 release
4. Merge Phase 4c after a few weeks (gives users time to migrate)
5. Schedule v7.0 removal for July 2026

**Minimum wait:** 2 releases after Phase 4b before v7.0 removal (API contract stability)

---

## Success Criteria

- ✅ `_log_legacy_keyword_access()` helper implemented
- ✅ Fallback paths log warnings in both functions
- ✅ CHANGELOG.md includes deprecation entry
- ✅ CLAUDE.md documents timeline
- ✅ GitHub issue created for v7.0 work
- ✅ Tests verify warning logged (or manually verified)
- ✅ No breaking changes in v6.4 API

---

## Related Docs

- [PHASE4_KEYWORDS_DEPRECATION.md](PHASE4_KEYWORDS_DEPRECATION.md) — Full deprecation timeline
- [PHASE4_KEYWORDS_HUB.md](PHASE4_KEYWORDS_HUB.md) — Index of Phase 4 docs (current vs archived)
- [PHASE4B_KEYWORD_READER_AUDIT.md](../../archive/plans/database/PHASE4B_KEYWORD_READER_AUDIT.md) — Phase 4b audit results (archived)
- [PHASE4B_IMPLEMENTATION_STEPS.md](../../archive/plans/database/PHASE4B_IMPLEMENTATION_STEPS.md) — Phase 4b implementation details (archived)
- [PHASE4B_TEST_CHECKLIST.md](../../archive/plans/database/PHASE4B_TEST_CHECKLIST.md) — Phase 4b test checklist (archived)

---

## Next: Phase 4d (v7.0)

After v6.4 is in production for 1-2 months:

1. Remove IMAGES.KEYWORDS column
2. Simplify code (remove COALESCE, remove Firebird paths)
3. Mark Firebird as unsupported
4. Release v7.0

See `PHASE4_KEYWORDS_DEPRECATION.md` for full timeline.
