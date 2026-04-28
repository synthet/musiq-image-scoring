# DB Schema Refactor Plan: Refined (Hybrid 3NF + Performance Hardening)

## Context
The current Firebird schema has: slow point lookups (~136–142 ms) due to missing indexes, a 3.5 s keyword-discovery scan, missing referential integrity FKs, redundant/duplicate index objects, and 1NF violations (`IMAGES.KEYWORDS` as BLOB). The goal is hybrid 3NF with expand-contract migration and no breaking IPC/API changes.

This plan **corrects several inaccuracies** from the draft based on live schema inspection.

---

## Corrections vs. Draft (live schema findings)

| Draft claim | Reality |
|---|---|
| Add `UQ_IMAGES_IMAGE_UUID` | **Already exists** — skip |
| Add `IMAGES(STACK_ID, SCORE_GENERAL DESC)` index | `IDX_STACK_SCORE_GENERAL` **(STACK_ID, SCORE_GENERAL) already exists** — skip |
| CULLING_PICKS has 2 duplicate FK artifacts | **4 redundant objects**: INTEG_13+14 (legacy FKs) + FK_CULLING_PICKS_IMAGES/SESSIONS (named FKs) + IDX_CULLING_PICKS_IMAGE/SESSION (extra standalone indexes) |
| IMAGES.FOLDER_ID has 2 duplicate indexes | **3 total**: FK_IMAGES_FOLDERS + IDX_FOLDER_ID + IDX_IMAGES_FOLDER_ID |
| IMAGES.STACK_ID has 2 duplicate indexes | **2 standalone** (IDX_STACK_ID + IDX_IMAGES_STACK_ID) both redundant given the composite |
| 57 orphan STACKS.BEST_IMAGE_ID references | DB health check reports **0 integrity issues** — orphan count must be re-verified before acting |
| IMAGE_XMP is empty / needs schema | **IMAGE_XMP already has** RATING, LABEL, KEYWORDS, TITLE, DESCRIPTION, PICK_STATUS, BURST_UUID, STACK_ID — only backfill needed |
| IMAGES.FILE_PATH — no mention of nullability | FILE_PATH is **nullable** — must clean NULLs before adding unique constraint |
| IMAGE_XMP.STACK_ID as FK to STACKS | IMAGE_XMP.STACK_ID is **VARCHAR(64)** but STACKS.ID is **INTEGER** — type mismatch, cannot add FK without column change |

---

## Phases

### Phase 0 — Baseline & Safety
- Take full FDB backup.
- Capture row counts, latency baselines (`FILE_PATH` lookup, `IMAGE_UUID` lookup, keyword scan).
- Run pre-migration integrity audit:
  - Re-verify `STACKS.BEST_IMAGE_ID` orphan count (health check showed 0 — confirm).
  - Verify `IMAGES.FILE_PATH` NULL count (needed before UQ constraint).
  - Document all duplicate index names for safe removal list.

### Phase 1 — Integrity + Index Hardening (no contract break)

**Data cleanup (before constraint work):**
- Count and handle `IMAGES.FILE_PATH IS NULL` rows — either populate or confirm they are safe to exclude from unique constraint (Firebird allows nullable unique: NULLs not counted toward uniqueness, so this is safe to skip if count is low).
- If orphan STACKS.BEST_IMAGE_ID rows confirmed > 0: `UPDATE STACKS SET BEST_IMAGE_ID = NULL WHERE BEST_IMAGE_ID NOT IN (SELECT ID FROM IMAGES)`.

**Add missing unique constraint:**
- `CREATE UNIQUE INDEX UQ_IMAGES_FILE_PATH ON IMAGES (FILE_PATH);`
  - `UQ_IMAGES_IMAGE_UUID` already exists — skip.

**Add missing foreign keys:**
- `IMAGES.JOB_ID → JOBS.ID` (DEFERRABLE if ingestion is live)
- `IMAGES.STACK_ID → STACKS.ID`
- `STACKS.BEST_IMAGE_ID → IMAGES.ID`
- `IMAGE_PHASE_STATUS.JOB_ID → JOBS.ID`
- `STACK_CACHE.STACK_ID → STACKS.ID`
- `STACK_CACHE.REP_IMAGE_ID → IMAGES.ID`
- `STACK_CACHE.FOLDER_ID → FOLDERS.ID`
- Do NOT add FK on `IMAGE_XMP.STACK_ID` (type mismatch, VARCHAR vs INTEGER).

**Add missing compound indexes for hot paths:**
- `CREATE INDEX IDX_FOLDER_SCORE ON IMAGES (FOLDER_ID, SCORE_GENERAL);`
  - `IDX_STACK_SCORE_GENERAL (STACK_ID, SCORE_GENERAL)` already exists — skip.

**Remove redundant index/constraint objects** (after FKs above are confirmed working):
- `CULLING_PICKS`: drop `INTEG_13`, `INTEG_14` (legacy system-named FKs), `IDX_CULLING_PICKS_IMAGE`, `IDX_CULLING_PICKS_SESSION` — keep `FK_CULLING_PICKS_IMAGES` and `FK_CULLING_PICKS_SESSIONS`.
- `IMAGES.FOLDER_ID`: drop `IDX_FOLDER_ID` and `IDX_IMAGES_FOLDER_ID` — `FK_IMAGES_FOLDERS` index + new compound `IDX_FOLDER_SCORE` covers all access patterns.
- `IMAGES.STACK_ID`: drop `IDX_STACK_ID` — keep `IDX_IMAGES_STACK_ID` + existing `IDX_STACK_SCORE_GENERAL`.

**Finalize:**
- `SET STATISTICS INDEX` on all modified indexes.

### Phase 2 — Hybrid 3NF Normalization (dual-write, backward-compatible)

**Normalize keywords:**
```sql
CREATE TABLE KEYWORDS_DIM (
  KEYWORD_ID INTEGER NOT NULL PRIMARY KEY,
  KEYWORD_NORM VARCHAR(200) NOT NULL,
  KEYWORD_DISPLAY VARCHAR(200),
  CONSTRAINT UQ_KEYWORD_NORM UNIQUE (KEYWORD_NORM)
);

CREATE TABLE IMAGE_KEYWORDS (
  IMAGE_ID INTEGER NOT NULL,
  KEYWORD_ID INTEGER NOT NULL,
  SOURCE VARCHAR(50),         -- 'auto', 'manual', 'xmp'
  CONFIDENCE DOUBLE PRECISION,
  CREATED_AT TIMESTAMP,
  CONSTRAINT PK_IMAGE_KEYWORDS PRIMARY KEY (IMAGE_ID, KEYWORD_ID),
  CONSTRAINT FK_IK_IMAGE FOREIGN KEY (IMAGE_ID) REFERENCES IMAGES(ID),
  CONSTRAINT FK_IK_KEYWORD FOREIGN KEY (KEYWORD_ID) REFERENCES KEYWORDS_DIM(KEYWORD_ID)
);
```
- Backfill by splitting `IMAGES.KEYWORDS` BLOB on comma delimiter.
- Add `AFTER UPDATE OR INSERT` trigger on `IMAGE_KEYWORDS` to keep `IMAGES.KEYWORDS` in sync (compatibility window).

**Normalize editable metadata (IMAGE_XMP backfill):**
- IMAGE_XMP already has target columns: RATING, LABEL, KEYWORDS, TITLE, DESCRIPTION, PICK_STATUS, BURST_UUID.
- Run backfill: `INSERT OR UPDATE INTO IMAGE_XMP (IMAGE_ID, RATING, LABEL, TITLE, DESCRIPTION, KEYWORDS) SELECT ID, RATING, LABEL, TITLE, DESCRIPTION, KEYWORDS FROM IMAGES WHERE ID NOT IN (SELECT IMAGE_ID FROM IMAGE_XMP)`.
- Add dual-write triggers on `IMAGES` for RATING, LABEL, TITLE, DESCRIPTION, KEYWORDS → mirror to IMAGE_XMP.
- Note: `IMAGE_XMP.STACK_ID` is VARCHAR(64) — do **not** add FK; leave as denormalized reference until a separate column type migration is planned.

**Add CHECK constraints for controlled enums:**
- `IMAGES.LABEL`: `CHECK (LABEL IN ('Red','Yellow','Green','Blue','Purple') OR LABEL IS NULL)`
- `IMAGES.CULL_DECISION`: `CHECK (CULL_DECISION IN ('keep','reject','maybe') OR CULL_DECISION IS NULL)`
- `IMAGE_XMP.LABEL`: same as IMAGES.LABEL

### Phase 3 — Query Refactor in App (no IPC break)

Target file: [modules/db.py](../../modules/db.py) — confirmed as the main DB query layer.

- Replace keyword LIKE scan on BLOB (5 locations: lines ~502, 594, 721, 871, 3403) with:
  `EXISTS (SELECT 1 FROM IMAGE_KEYWORDS ik JOIN KEYWORDS_DIM kd ON ik.KEYWORD_ID = kd.KEYWORD_ID WHERE ik.IMAGE_ID = i.ID AND kd.KEYWORD_NORM = ?)`
- Replace keyword discovery full-table scan with: `SELECT KEYWORD_DISPLAY FROM KEYWORDS_DIM ORDER BY KEYWORD_DISPLAY`
- Update folder image count query (~line 2460) from `SELECT * FROM images WHERE folder_id = ?` (loads all rows) to `SELECT COUNT(*) FROM images WHERE folder_id = ?`.

### Phase 4 — Cutover & Deprecation
- After all consistency and performance gates pass (one full release cycle): deprecate `IMAGES.KEYWORDS`, `IMAGES.TITLE`, `IMAGES.DESCRIPTION`, `IMAGES.RATING`, `IMAGES.LABEL` as writable columns.
- Add compatibility VIEWs during deprecation window before column drop.

---

## Public Interfaces / Contracts
- **No breaking IPC/API change** in this cycle.
- New DB objects: `KEYWORDS_DIM`, `IMAGE_KEYWORDS`, new constraints/indexes, compatibility triggers/views.
- Existing read contracts stay intact while storage model improves underneath.

---

## Critical Pre-Conditions
1. Orphan count for `STACKS.BEST_IMAGE_ID` must be re-verified before adding FK (health check shows 0 issues — contradicts the "57 orphan" claim in the draft).
2. `IMAGE_XMP.STACK_ID` type mismatch (VARCHAR vs INTEGER) must be accepted as out-of-scope for this cycle — no FK to STACKS can be added without a column type migration.
3. Keyword LIKE queries are spread across 5 locations in `modules/db.py` — all must be updated in Phase 3.

---

## Verification

**Integrity gates:**
- `SELECT COUNT(*) FROM STACKS WHERE BEST_IMAGE_ID IS NOT NULL AND BEST_IMAGE_ID NOT IN (SELECT ID FROM IMAGES)` → 0
- `SELECT COUNT(*) FROM IMAGES i WHERE IMAGE_UUID IS NOT NULL GROUP BY IMAGE_UUID HAVING COUNT(*) > 1` → 0 rows
- Dual-write spot-check: 100 random images where `IMAGES.KEYWORDS = (SELECT KEYWORDS FROM IMAGE_XMP WHERE IMAGE_ID = i.ID)`

**Performance gates (P95):**
- `SELECT * FROM IMAGES WHERE FILE_PATH = ?` → < 25 ms
- `SELECT * FROM IMAGES WHERE IMAGE_UUID = ?` → < 25 ms
- `SELECT KEYWORD_DISPLAY FROM KEYWORDS_DIM` → < 150 ms warm
- Folder-filtered image queries → no regression from current baseline

**Rollback:**
- Restore backup to staging and validate down-script before production rollout.

---

## Assumptions
- Decisions locked: **Hybrid 3NF**, **Expand-Contract**, **Backward-Compatible**.
- Firebird remains the engine; additive schema evolution is acceptable.
- Migration runs with controlled ingestion windows when performing backfill and constraint enforcement.
