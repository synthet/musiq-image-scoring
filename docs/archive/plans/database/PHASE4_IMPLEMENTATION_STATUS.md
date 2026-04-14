---
name: Phase 4 Implementation Status & Next Steps
description: Current status and what's ready to execute
status: in-progress
---

# Phase 4: Implementation Status & Next Steps

**Last updated:** 2026-04-02  
**Status:** Phase 4a tooling complete; Phase 4b implementation in progress

---

## What's Complete ✅

### Tooling & Documentation

| Item | File | Status |
|------|------|--------|
| Consistency check script | `scripts/db/phase4_consistency_check.py` | ✅ Ready |
| Performance benchmark | `scripts/db/phase4_performance_benchmark.py` | ✅ Ready |
| Keyword discovery module | `modules/keyword_discovery.py` | ✅ Ready |
| Deprecation roadmap | `docs/plans/database/PHASE4_KEYWORDS_DEPRECATION.md` | ✅ Ready |
| Code audit | `docs/plans/database/PHASE4_CODE_AUDIT.md` | ✅ Ready |
| Implementation summary | `docs/plans/database/PHASE4_SUMMARY.md` | ✅ Ready |
| CLAUDE.md guidelines | `CLAUDE.md` (section added) | ✅ Ready |

### Code Fixes Implemented

| Issue | File | Fix | Status |
|-------|------|-----|--------|
| Tagging writer bypasses dual-write | `modules/tagging.py:730` | Added `_sync_image_keywords()` call | ✅ Done |

---

## Phase 4a: Validation & Benchmarking (Ready to Execute)

### To run immediately:

```bash
# 1. Run consistency check
python scripts/db/phase4_consistency_check.py

# 2. Run performance benchmark
python scripts/db/phase4_performance_benchmark.py

# 3. Document results
# Create PHASE4_RESULTS_SNAPSHOT.md with findings
```

### Success criteria:

- ✅ No mismatches between legacy and normalized keyword data
- ✅ Normalized path <150ms for keyword searches
- ✅ No data loss during backfill

---

## Phase 4b: Primary Source Cutover (In Progress)

**Target:** v6.3 release (May 2026)

### ✅ Completed

- [x] Code audit of all keyword readers/writers
- [x] Fixed tagging writer dual-write issue
- [x] Updated CLAUDE.md with keyword guidelines
- [x] Identified all critical paths

### ⏳ In Progress / Next

- [ ] Verify Firebird fallback paths work correctly
- [ ] Run consistency + performance tests
- [ ] Test keyword operations end-to-end:
  - [ ] Tagging via API
  - [ ] Keyword filtering in gallery
  - [ ] Tag propagation between images
  - [ ] Keyword cloud / discovery features
- [ ] Code review with team
- [ ] Merge and tag as v6.3

### Testing Checklist

```bash
# Keyword write operations
- [ ] PATCH /api/images/{id} with keywords
- [ ] POST /api/jobs/tag with custom_keywords
- [ ] propagate_tags() with dry_run=true/false

# Keyword read operations
- [ ] GET /api/images?keyword=birds (filter)
- [ ] Gallery keyword filter UI
- [ ] Keyword autocomplete (if feature exists)

# Dual-write consistency
- [ ] Run: python scripts/db/phase4_consistency_check.py
- [ ] Verify 0 mismatches
```

---

## Phase 4c: Soft Deprecation (Planned for v6.4 / June 2026)

**What will change:**
- Add deprecation logging to any remaining legacy keyword reads
- Announce EOL in changelog ("IMAGES.KEYWORDS will be removed in v7.0")
- Update release notes with migration guide

**Exit criteria:**
- All readers tested with normalized schema
- Deprecation warnings logged and documented
- Team aware of Phase 4d removal date

---

## Phase 4d: Hard Deprecation (Planned for v7.0 / July 2026)

**What will change:**
- Alembic migration: `ALTER TABLE images DROP COLUMN keywords;`
- Remove all Firebird keyword compatibility code
- Remove `_backfill_keywords()` and related legacy helpers

---

## Recommended Execution Order

1. **This week (2026-04-02 to 04-05):**
   - Run Phase 4a tests (consistency + performance)
   - Document baseline results
   - Review code audit findings

2. **Next 1-2 weeks (2026-04-05 to 04-15):**
   - Finish Phase 4b testing
   - Code review with team
   - Prepare v6.3 release candidate

3. **v6.3 Release (2026-04-15 to 04-20):**
   - Merge all Phase 4b changes
   - Tag release
   - Monitor production for consistency issues

4. **v6.4 Release (2026-05-20 to 05-27):**
   - Add deprecation logging
   - Update docs

5. **v7.0 Release (2026-07-01):**
   - Remove legacy column
   - Close Phase 4 epic

---

## Key Files to Know

### Tests & Utilities

- `scripts/db/phase4_consistency_check.py` — Run to verify data consistency
- `scripts/db/phase4_performance_benchmark.py` — Run to benchmark keyword queries
- `modules/keyword_discovery.py` — Use for keyword cloud, autocomplete, etc.

### Documentation

- `CLAUDE.md` — Updated with keyword guidelines
- `docs/plans/database/PHASE4_KEYWORDS_DEPRECATION.md` — Full deprecation roadmap
- `docs/plans/database/PHASE4_CODE_AUDIT.md` — Code audit & issues found
- `docs/plans/database/PHASE4_SUMMARY.md` — Implementation summary

### Code Paths

- **Read (filter):** `db._add_keyword_filter()` — Already uses normalized schema ✅
- **Write:** `db.update_image_metadata()` — Dual-write to both schemas ✅
- **Sync:** `db._sync_image_keywords()` — Syncs legacy → normalized ✅

---

## Known Issues & Resolutions

### Issue 1: Tagging writer bypasses dual-write ✅ FIXED
**File:** `modules/tagging.py:730`  
**Status:** Fixed (added `_sync_image_keywords()` call)

### Issue 2: API reads unnecessary from legacy column
**File:** `modules/api.py:4351`  
**Status:** Low priority; works correctly (calls `update_image_metadata()` which dual-writes)

### Issue 3: Repair function may not clean up both sides
**File:** `modules/db.py:7983`  
**Status:** Maintenance code; not critical for Phase 4a/4b

---

## Questions / Blockers

- [ ] **Electron migration timeline:** Is Electron migrating to Postgres in Phase 4 or later?
  - **Impact:** Affects deprecation urgency
  - **Decision:** Defer Phase 4d until Electron migration confirmed

- [ ] **Firebird end-of-life:** When does Firebird support end?
  - **Current:** Kept for Electron compatibility
  - **Decision:** Phase 4d timing depends on Electron migration

---

## Success Metrics

By end of Phase 4d (v7.0):

- ✅ Zero keyword-related bugs reported
- ✅ Normalized keyword schema is primary (no legacy column)
- ✅ All keyword operations run <150ms
- ✅ Electron migration complete (or documented as pending)
- ✅ 100% test coverage for keyword paths

---

## How to Contribute

### For team members:

1. **Phase 4a (now):**
   - Run consistency + perf tests
   - Review audit findings
   - Verify Firebird compatibility

2. **Phase 4b (v6.3):**
   - Test keyword operations
   - Code review changes
   - Sign off on readiness

3. **Phase 4c (v6.4):**
   - Monitor deprecation warnings
   - Gather feedback from users
   - Plan Phase 4d rollout

### For CI/CD:

- Add Phase 4a tests to CI pipeline (optional)
- Tag Phase 4b release as "ready-for-phase-4c"
- Automate Phase 4c deprecation logging

---

## Contact & References

- **Plan authority:** This document
- **Code audit:** `docs/plans/database/PHASE4_CODE_AUDIT.md`
- **Full deprecation plan:** `docs/plans/database/PHASE4_KEYWORDS_DEPRECATION.md`
- **Embedding parallel work:** `docs/plans/database/DB_VECTORS_REFACTOR.md` (already complete)
