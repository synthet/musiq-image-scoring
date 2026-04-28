# DB Schema Refactor: Hybrid 3NF + Performance Hardening — Implementation Guide

**Status:** Implementation plan approved, ready for phased rollout
**Last updated:** 2026-03-08
**Reference:** `DB_SCHEMA_REFACTOR_PLAN.md` (strategic phase definitions)

---

## Context & Motivation

The live Firebird database (`SCORING_HISTORY.FDB`) has accumulated performance and integrity debt:

- **Performance:** `IMAGES.FILE_PATH` point lookups avg ~136ms (no unique index); `IMAGE_UUID` ~142ms despite index (stale stats)
- **Performance:** `getKeywords()` does full-table BLOB scan taking ~3.5s
- **Integrity:** `STACKS.BEST_IMAGE_ID` has 57 orphan references (no FK enforced)
- **Integrity:** Several FK relationships are unenforced (`IMAGES.JOB_ID`, `IMAGES.STACK_ID`, `IMAGE_PHASE_STATUS.JOB_ID`, `STACK_CACHE.*`)
- **Redundancy:** Duplicate indexes on `IMAGES.FOLDER_ID` and `IMAGES.STACK_ID`; duplicate FK artifacts on `CULLING_PICKS`
- **Normalization:** `IMAGES.KEYWORDS` is a comma-separated BLOB (violates 1NF); `IMAGE_XMP` table exists but is empty

This guide implements the phased refactor described in `DB_SCHEMA_REFACTOR_PLAN.md`, prioritizing:
1. **No breaking IPC/API contract changes**
2. **Backward-compatible dual-write** during transition
3. **Performance targets:** File path/UUID lookups <25ms, keyword discovery <150ms warm

---

## Architecture & Approach

### Schema Authority
- **Python backend:** [db.py](https://github.com/synthet/image-scoring-backend/blob/main/modules/db.py)
  - `_init_db_impl()` (line 1009) owns all DDL via try/except migration blocks
  - New migration blocks inserted **before** `conn.close()` at line 1564
  - Uses `_table_exists()`, `_column_exists()`, `_index_exists()`, `_constraint_exists()` helpers (lines ~980-1007)
  - All DDL is idempotent; wrapped in try/except; commits after each step

### Query Layer
- **Electron frontend:** [db.ts](https://github.com/synthet/image-scoring-gallery/blob/main/electron/db.ts)
  - Owns all Electron-side queries + connection pooling
  - Calls `query<T>()` which serializes operations via `queryChain` promise queue
  - `ensureStackCacheTable()` creates `STACK_CACHE` on first use (to be handed off to Python in Phase 1)

### Pattern
All DDL changes use this pattern:
```python
if not _index_exists(c, 'MY_INDEX_NAME'):
    try:
        c.execute("CREATE INDEX ...")
        conn.commit()
        c = conn.cursor()
    except Exception as e:
        logger.warning("CREATE INDEX failed: %s", e)
        try: conn.rollback()
        except Exception: pass
        c = conn.cursor()
```

---

## Phase 0: Baseline + Safety

**Goal:** Establish a safe point before any schema changes. No code changes required.

### Step 0.1 — Pre-migration Integrity Audit

Run these SQL queries via MCP or gbak to document current state:

```sql
-- Orphan FK counts
SELECT COUNT(*) FROM stacks
WHERE best_image_id IS NOT NULL
  AND best_image_id NOT IN (SELECT id FROM images);
-- Expected: ~57

SELECT COUNT(*) FROM images
WHERE job_id IS NOT NULL AND job_id NOT IN (SELECT id FROM jobs);

SELECT COUNT(*) FROM images
WHERE stack_id IS NOT NULL AND stack_id NOT IN (SELECT id FROM stacks);

SELECT COUNT(*) FROM image_phase_status
WHERE job_id IS NOT NULL AND job_id NOT IN (SELECT id FROM jobs);

-- Duplicate file_path rows (must be 0 to add UQ_IMAGES_FILE_PATH)
SELECT file_path, COUNT(*) as cnt FROM images
GROUP BY file_path HAVING COUNT(*) > 1;

-- Duplicate image_uuid rows
SELECT image_uuid, COUNT(*) as cnt FROM images
WHERE image_uuid IS NOT NULL
GROUP BY image_uuid HAVING COUNT(*) > 1;

-- Duplicate folder paths
SELECT path, COUNT(*) as cnt FROM folders
GROUP BY path HAVING COUNT(*) > 1;

-- Index inventory (document before/after)
SELECT rdb$index_name, rdb$relation_name, rdb$unique_flag
FROM rdb$indices
WHERE rdb$relation_name IN ('IMAGES', 'CULLING_PICKS', 'FOLDERS')
ORDER BY rdb$relation_name, rdb$index_name;

-- Row count baseline
SELECT 'images' as tbl, COUNT(*) as cnt FROM images UNION ALL
SELECT 'stacks', COUNT(*) FROM stacks UNION ALL
SELECT 'folders', COUNT(*) FROM folders UNION ALL
SELECT 'image_phase_status', COUNT(*) FROM image_phase_status UNION ALL
SELECT 'stack_cache', COUNT(*) FROM stack_cache UNION ALL
SELECT 'keywords_dim', COUNT(*) FROM keywords_dim UNION ALL
SELECT 'image_keywords', COUNT(*) FROM image_keywords;
```

### Step 0.2 — Full Database Backup

Before any migration:

```bash
# Using Firebird gbak (preferred — doesn't require shutdown)
gbak -b -user sysdba -password masterkey localhost:SCORING_HISTORY.FDB \
     backups/SCORING_HISTORY_pre_refactor_phase1_$(date +%Y%m%d_%H%M%S).fbk

# Or add this to db.py for application-level backup
def _backup_db_gbak(suffix=""):
    import subprocess
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"/path/to/your/repo/backups/SCORING_HISTORY_backup_{suffix}_{ts}.fbk"
    cmd = [
        "gbak",
        "-b", "-user", "sysdba", "-password", "masterkey",
        f"localhost:{get_db_path()}",
        backup_path
    ]
    subprocess.run(cmd, check=True)
    return backup_path
```

---

## Phase 1: Integrity + Index Hardening

**Goal:** Fix orphan data, add missing indexes, enforce FKs, remove duplicates. No IPC contract changes.

**File:** [db.py](https://github.com/synthet/image-scoring-backend/blob/main/modules/db.py)
**Insert location:** Before `conn.close()` at line 1564 (just before `# Seed phases` comment)

### Implementation Steps

#### 1.1 — Repair Orphan STACKS.BEST_IMAGE_ID

```python
# --- Phase 1: Integrity + Index Hardening ---
try:
    c = conn.cursor()

    # 1.1: Repair orphan STACKS.BEST_IMAGE_ID rows (57 total)
    c.execute("""
        UPDATE stacks SET best_image_id = NULL
        WHERE best_image_id IS NOT NULL
          AND best_image_id NOT IN (SELECT id FROM images)
    """)
    conn.commit()
    c = conn.cursor()
```

#### 1.2 — Add UQ_IMAGES_FILE_PATH (highest-impact)

This is critical: enables indexed `UPDATE OR INSERT ... MATCHING (file_path)` in `upsert_image()`.

```python
    # 1.2: Unique index on IMAGES.FILE_PATH
    if not _index_exists(c, 'UQ_IMAGES_FILE_PATH'):
        try:
            # First: delete exact duplicate file_path rows (keep highest id)
            c.execute("""
                DELETE FROM images
                WHERE id NOT IN (
                    SELECT MAX(id) FROM images
                    WHERE file_path IS NOT NULL
                    GROUP BY file_path
                )
                AND file_path IN (
                    SELECT file_path FROM images
                    WHERE file_path IS NOT NULL
                    GROUP BY file_path HAVING COUNT(*) > 1
                )
            """)
            conn.commit()
            c = conn.cursor()

            # Create unique constraint
            c.execute("CREATE UNIQUE INDEX uq_images_file_path ON images(file_path)")
            conn.commit()
            c = conn.cursor()
        except Exception as e:
            logger.warning("Could not create UQ_IMAGES_FILE_PATH: %s", e)
            try: conn.rollback()
            except Exception: pass
            c = conn.cursor()
```

#### 1.3 — Add Composite Indexes for Hot Paths

```python
    # 1.3: Composite indexes for query optimization
    if not _index_exists(c, 'IDX_IMAGES_FOLDER_SCORE'):
        try:
            c.execute("CREATE INDEX idx_images_folder_score ON images(folder_id, score_general DESC)")
            conn.commit()
            c = conn.cursor()
        except Exception as e:
            logger.warning("IDX_IMAGES_FOLDER_SCORE: %s", e)
            try: conn.rollback()
            except Exception: pass
            c = conn.cursor()

    if not _index_exists(c, 'IDX_IMAGES_STACK_SCORE'):
        try:
            c.execute("CREATE INDEX idx_images_stack_score ON images(stack_id, score_general DESC)")
            conn.commit()
            c = conn.cursor()
        except Exception as e:
            logger.warning("IDX_IMAGES_STACK_SCORE: %s", e)
            try: conn.rollback()
            except Exception: pass
            c = conn.cursor()
```

#### 1.4 — Drop Redundant Duplicate Indexes

```python
    # 1.4: Remove redundant single-column indexes (superseded by composites above)
    for old_idx in ('IDX_IMAGES_FOLDER_ID', 'IDX_IMAGES_STACK_ID'):
        if _index_exists(c, old_idx):
            try:
                c.execute(f"DROP INDEX {old_idx}")
                conn.commit()
                c = conn.cursor()
            except Exception as e:
                logger.warning("DROP INDEX %s: %s", old_idx, e)
                try: conn.rollback()
                except Exception: pass
                c = conn.cursor()
    # Keep IDX_FOLDER_ID and IDX_STACK_ID (canonical legacy names)

    # 1.4b: Drop auto-named orphan FK artifacts on CULLING_PICKS
    # These are RDB$FOREIGN9/10 style names; drop if canonical FK already exists
    c.execute("""
        SELECT rdb$constraint_name FROM rdb$relation_constraints
        WHERE rdb$relation_name = 'CULLING_PICKS'
          AND rdb$constraint_type = 'FOREIGN KEY'
          AND rdb$constraint_name NOT STARTING WITH 'FK_'
    """)
    orphan_constraints = [row[0].strip() for row in c.fetchall()]
    for cn in orphan_constraints:
        try:
            c.execute(f'ALTER TABLE culling_picks DROP CONSTRAINT "{cn}"')
            conn.commit()
            c = conn.cursor()
        except Exception as e:
            logger.warning("DROP orphan constraint %s: %s", cn, e)
            try: conn.rollback()
            except Exception: pass
            c = conn.cursor()
```

#### 1.5 — Add Missing FK Constraints

Null out orphans first, then enforce the constraint:

```python
    # 1.5a: FK_STACKS_BEST_IMAGE (after orphan repair in 1.1)
    if not _constraint_exists(c, 'FK_STACKS_BEST_IMAGE'):
        try:
            c.execute("""
                ALTER TABLE stacks ADD CONSTRAINT fk_stacks_best_image
                FOREIGN KEY (best_image_id) REFERENCES images(id) ON DELETE SET NULL
            """)
            conn.commit()
            c = conn.cursor()
        except Exception as e:
            logger.warning("FK_STACKS_BEST_IMAGE: %s", e)
            try: conn.rollback()
            except Exception: pass
            c = conn.cursor()

    # 1.5b: FK_IMAGES_JOB
    if not _constraint_exists(c, 'FK_IMAGES_JOB'):
        try:
            # Null out orphans
            c.execute("UPDATE images SET job_id = NULL WHERE job_id NOT IN (SELECT id FROM jobs)")
            conn.commit()
            c = conn.cursor()
            # Add FK
            c.execute("""
                ALTER TABLE images ADD CONSTRAINT fk_images_job
                FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE SET NULL
            """)
            conn.commit()
            c = conn.cursor()
        except Exception as e:
            logger.warning("FK_IMAGES_JOB: %s", e)
            try: conn.rollback()
            except Exception: pass
            c = conn.cursor()

    # 1.5c: FK_IMAGES_STACK
    if not _constraint_exists(c, 'FK_IMAGES_STACK'):
        try:
            c.execute("UPDATE images SET stack_id = NULL WHERE stack_id NOT IN (SELECT id FROM stacks)")
            conn.commit()
            c = conn.cursor()
            c.execute("""
                ALTER TABLE images ADD CONSTRAINT fk_images_stack
                FOREIGN KEY (stack_id) REFERENCES stacks(id) ON DELETE SET NULL
            """)
            conn.commit()
            c = conn.cursor()
        except Exception as e:
            logger.warning("FK_IMAGES_STACK: %s", e)
            try: conn.rollback()
            except Exception: pass
            c = conn.cursor()

    # 1.5d: FK_IPS_JOB (IMAGE_PHASE_STATUS.JOB_ID)
    if _table_exists(c, 'IMAGE_PHASE_STATUS') and not _constraint_exists(c, 'FK_IPS_JOB'):
        try:
            c.execute("UPDATE image_phase_status SET job_id = NULL WHERE job_id NOT IN (SELECT id FROM jobs)")
            conn.commit()
            c = conn.cursor()
            c.execute("""
                ALTER TABLE image_phase_status ADD CONSTRAINT fk_ips_job
                FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE SET NULL
            """)
            conn.commit()
            c = conn.cursor()
        except Exception as e:
            logger.warning("FK_IPS_JOB: %s", e)
            try: conn.rollback()
            except Exception: pass
            c = conn.cursor()

    # 1.5e: STACK_CACHE FKs (table may be created by Electron before Python migration)
    if _table_exists(c, 'STACK_CACHE'):
        if not _constraint_exists(c, 'FK_STACK_CACHE_STACK'):
            try:
                c.execute("DELETE FROM stack_cache WHERE stack_id NOT IN (SELECT id FROM stacks)")
                conn.commit()
                c = conn.cursor()
                c.execute("""
                    ALTER TABLE stack_cache ADD CONSTRAINT fk_stack_cache_stack
                    FOREIGN KEY (stack_id) REFERENCES stacks(id) ON DELETE CASCADE
                """)
                conn.commit()
                c = conn.cursor()
            except Exception as e:
                logger.warning("FK_STACK_CACHE_STACK: %s", e)
                try: conn.rollback()
                except Exception: pass
                c = conn.cursor()

        if not _constraint_exists(c, 'FK_STACK_CACHE_REP_IMAGE'):
            try:
                c.execute("UPDATE stack_cache SET rep_image_id = NULL WHERE rep_image_id NOT IN (SELECT id FROM images)")
                conn.commit()
                c = conn.cursor()
                c.execute("""
                    ALTER TABLE stack_cache ADD CONSTRAINT fk_stack_cache_rep_image
                    FOREIGN KEY (rep_image_id) REFERENCES images(id) ON DELETE SET NULL
                """)
                conn.commit()
                c = conn.cursor()
            except Exception as e:
                logger.warning("FK_STACK_CACHE_REP_IMAGE: %s", e)
                try: conn.rollback()
                except Exception: pass
                c = conn.cursor()

        if not _constraint_exists(c, 'FK_STACK_CACHE_FOLDER'):
            try:
                c.execute("UPDATE stack_cache SET folder_id = NULL WHERE folder_id NOT IN (SELECT id FROM folders)")
                conn.commit()
                c = conn.cursor()
                c.execute("""
                    ALTER TABLE stack_cache ADD CONSTRAINT fk_stack_cache_folder
                    FOREIGN KEY (folder_id) REFERENCES folders(id) ON DELETE SET NULL
                """)
                conn.commit()
                c = conn.cursor()
            except Exception as e:
                logger.warning("FK_STACK_CACHE_FOLDER: %s", e)
                try: conn.rollback()
                except Exception: pass
                c = conn.cursor()

    # 1.5f: UQ_FOLDERS_PATH
    if not _index_exists(c, 'UQ_FOLDERS_PATH'):
        try:
            c.execute("""
                DELETE FROM folders WHERE id NOT IN (
                    SELECT MAX(id) FROM folders GROUP BY path
                )
                AND path IN (
                    SELECT path FROM folders GROUP BY path HAVING COUNT(*) > 1
                )
            """)
            conn.commit()
            c = conn.cursor()
            c.execute("CREATE UNIQUE INDEX uq_folders_path ON folders(path)")
            conn.commit()
            c = conn.cursor()
        except Exception as e:
            logger.warning("UQ_FOLDERS_PATH: %s", e)
            try: conn.rollback()
            except Exception: pass
            c = conn.cursor()
```

#### 1.6 — Move STACK_CACHE Creation to Python

Add table creation to `_init_db_impl()` (this code can go earlier, around the other CREATE TABLE blocks):

```python
    # 1.6: STACK_CACHE table (moved from Electron ensureStackCacheTable())
    if not _table_exists(c, 'STACK_CACHE'):
        try:
            c.execute('''CREATE TABLE stack_cache (
                stack_id               INTEGER NOT NULL PRIMARY KEY,
                image_count            INTEGER DEFAULT 0,
                rep_image_id           INTEGER,
                min_score_general      DOUBLE PRECISION,
                max_score_general      DOUBLE PRECISION,
                min_score_technical    DOUBLE PRECISION,
                max_score_technical    DOUBLE PRECISION,
                min_score_aesthetic    DOUBLE PRECISION,
                max_score_aesthetic    DOUBLE PRECISION,
                min_score_spaq         DOUBLE PRECISION,
                max_score_spaq         DOUBLE PRECISION,
                min_score_ava          DOUBLE PRECISION,
                max_score_ava          DOUBLE PRECISION,
                min_score_liqe         DOUBLE PRECISION,
                max_score_liqe         DOUBLE PRECISION,
                min_rating             INTEGER,
                max_rating             INTEGER,
                min_created_at         TIMESTAMP,
                max_created_at         TIMESTAMP,
                folder_id              INTEGER
            )''')
            conn.commit()
            c = conn.cursor()
        except Exception as e:
            logger.warning("CREATE TABLE stack_cache: %s", e)
            try: conn.rollback()
            except Exception: pass
            c = conn.cursor()
```

#### 1.7 — Recompute Index Statistics

After all DDL changes:

```python
    # 1.7: Recompute statistics for Firebird query planner
    for idx_name in ('UQ_IMAGES_FILE_PATH', 'UQ_IMAGES_IMAGE_UUID',
                     'IDX_IMAGES_FOLDER_SCORE', 'IDX_IMAGES_STACK_SCORE',
                     'IDX_FOLDER_ID', 'IDX_STACK_ID', 'UQ_FOLDERS_PATH'):
        if _index_exists(c, idx_name):
            try:
                c.execute(f"SET STATISTICS INDEX {idx_name}")
                conn.commit()
                c = conn.cursor()
            except Exception:
                pass
```

#### 1.8 — CHECK Constraints (Optional but Recommended)

```python
    # 1.8: CHECK constraints for enum validation (non-blocking if data violates)
    if not _constraint_exists(c, 'CHK_IMAGES_LABEL'):
        try:
            c.execute("""
                ALTER TABLE images ADD CONSTRAINT chk_images_label
                CHECK (label IS NULL OR label IN ('Red','Yellow','Green','Blue','Purple','None',''))
            """)
            conn.commit()
            c = conn.cursor()
        except Exception as e:
            logger.warning("CHK_IMAGES_LABEL: %s", e)
            try: conn.rollback()
            except Exception: pass
            c = conn.cursor()

    if not _constraint_exists(c, 'CHK_IMAGES_CULL_DECISION'):
        try:
            c.execute("""
                ALTER TABLE images ADD CONSTRAINT chk_images_cull_decision
                CHECK (cull_decision IS NULL OR cull_decision IN ('pick','reject','skip',''))
            """)
            conn.commit()
            c = conn.cursor()
        except Exception as e:
            logger.warning("CHK_IMAGES_CULL_DECISION: %s", e)
            try: conn.rollback()
            except Exception: pass
            c = conn.cursor()

    if not _constraint_exists(c, 'CHK_IPS_STATUS'):
        try:
            c.execute("""
                ALTER TABLE image_phase_status ADD CONSTRAINT chk_ips_status
                CHECK (status IN ('not_started','pending','running','done','failed','skipped'))
            """)
            conn.commit()
            c = conn.cursor()
        except Exception as e:
            logger.warning("CHK_IPS_STATUS: %s", e)
            try: conn.rollback()
            except Exception: pass
            c = conn.cursor()

except Exception as e:
    logger.error("Phase 1 migration error: %s", e)
    try: conn.rollback()
    except Exception: pass
```

### Phase 1: Electron Changes

**File:** [db.ts](https://github.com/synthet/image-scoring-gallery/blob/main/electron/db.ts)

Simplify `ensureStackCacheTable()` (~line 860) to a probe-only function:

```typescript
export async function ensureStackCacheTable(): Promise<void> {
    if (stackCacheInitPromise) return stackCacheInitPromise;
    stackCacheInitPromise = (async () => {
        // STACK_CACHE is now created by the Python backend on startup.
        // This probe verifies connectivity and table existence.
        await query(`SELECT 1 FROM stack_cache WHERE 1=0`);
    })();
    return stackCacheInitPromise;
}
```

### Phase 1: Verification Tests

After deploying Phase 1, run these SQL queries to validate:

```sql
-- 1. Zero orphans for all newly enforced FKs
SELECT COUNT(*) FROM stacks WHERE best_image_id IS NOT NULL AND best_image_id NOT IN (SELECT id FROM images);  -- expect 0
SELECT COUNT(*) FROM images WHERE stack_id IS NOT NULL AND stack_id NOT IN (SELECT id FROM stacks);  -- expect 0
SELECT COUNT(*) FROM images WHERE job_id IS NOT NULL AND job_id NOT IN (SELECT id FROM jobs);  -- expect 0

-- 2. Unique constraints working (file_path, image_uuid, folder path)
SELECT COUNT(DISTINCT file_path) FROM images;  -- should equal COUNT(*)
SELECT COUNT(DISTINCT path) FROM folders;  -- should equal COUNT(*)

-- 3. Index usage verification (EXPLAIN PLAN)
-- Time: SELECT id FROM images WHERE file_path = ? (should be <25ms)
-- Time: SELECT id FROM images WHERE image_uuid = ? (should be <25ms)

-- 4. Index names/duplicates cleaned up
SELECT rdb$index_name FROM rdb$indices WHERE rdb$relation_name = 'IMAGES' ORDER BY 1;
-- Should NOT contain IDX_IMAGES_FOLDER_ID or IDX_IMAGES_STACK_ID
```

---

## Phase 2: Hybrid 3NF Keyword Normalization + IMAGE_XMP Backfill

**Goal:** Normalize keyword storage and backfill IMAGE_XMP metadata. Enable backward-compatible dual-write so legacy `IMAGES.KEYWORDS` BLOB stays synchronized during transition.

**Files:**
- `modules/db.py` — table creation, backfill functions, dual-write logic
- [db.ts](https://github.com/synthet/image-scoring-gallery/blob/main/electron/db.ts) — `updateImageDetails()` dual-write

### Step 2.1 — Create KEYWORDS_DIM and IMAGE_KEYWORDS Tables (Python)

Add to `_init_db_impl()` after Phase 1 block, before `conn.close()` at line 1564:

```python
    # --- Phase 2: Keyword Normalization + IMAGE_XMP Backfill ---
    try:
        c = conn.cursor()

        # 2.1a: KEYWORDS_DIM table (dimension table for all possible keywords)
        if not _table_exists(c, 'KEYWORDS_DIM'):
            try:
                c.execute('''CREATE TABLE keywords_dim (
                    keyword_id      INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    keyword_norm    VARCHAR(200) NOT NULL,
                    keyword_display VARCHAR(200),
                    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')
                conn.commit()
                c = conn.cursor()

                # Unique index on normalized keyword (for efficient upserts)
                c.execute("CREATE UNIQUE INDEX uq_keywords_dim_norm ON keywords_dim(keyword_norm)")
                conn.commit()
                c = conn.cursor()
            except Exception as e:
                logger.warning("KEYWORDS_DIM table creation: %s", e)
                try: conn.rollback()
                except Exception: pass
                c = conn.cursor()

        # 2.1b: IMAGE_KEYWORDS junction table
        if not _table_exists(c, 'IMAGE_KEYWORDS'):
            try:
                c.execute('''CREATE TABLE image_keywords (
                    image_id    INTEGER NOT NULL,
                    keyword_id  INTEGER NOT NULL,
                    source      VARCHAR(20) DEFAULT 'auto',
                    confidence  DOUBLE PRECISION,
                    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (image_id, keyword_id)
                )''')
                conn.commit()
                c = conn.cursor()

                # Foreign keys
                c.execute("""
                    ALTER TABLE image_keywords ADD CONSTRAINT fk_imgkw_image
                    FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE
                """)
                conn.commit()
                c = conn.cursor()

                c.execute("""
                    ALTER TABLE image_keywords ADD CONSTRAINT fk_imgkw_keyword
                    FOREIGN KEY (keyword_id) REFERENCES keywords_dim(keyword_id) ON DELETE CASCADE
                """)
                conn.commit()
                c = conn.cursor()

                # Performance indexes
                c.execute("CREATE INDEX idx_imgkw_image_id ON image_keywords(image_id)")
                conn.commit()
                c = conn.cursor()

                c.execute("CREATE INDEX idx_imgkw_keyword_id ON image_keywords(keyword_id)")
                conn.commit()
                c = conn.cursor()
            except Exception as e:
                logger.warning("IMAGE_KEYWORDS table creation: %s", e)
                try: conn.rollback()
                except Exception: pass
                c = conn.cursor()

    except Exception as e:
        logger.error("Phase 2 table creation error: %s", e)
        try: conn.rollback()
        except Exception: pass
```

### Step 2.2 — Add Backfill Function (Python)

Add this new function to `db.py` (can go after `_init_db_impl()`):

```python
def _backfill_keywords():
    """
    One-time backfill: parse IMAGES.KEYWORDS BLOB and populate normalized
    KEYWORDS_DIM + IMAGE_KEYWORDS junction table.

    Idempotent: skips if IMAGE_KEYWORDS already has rows with source='auto_backfill'.
    Called from _init_db_impl() after both tables are created.
    """
    conn = get_db()
    c = conn.cursor()
    try:
        # Check if backfill already done
        c.execute("SELECT COUNT(*) FROM image_keywords WHERE source = 'auto_backfill'")
        row = c.fetchone()
        if row and row[0] > 0:
            logger.info("Keyword backfill already done (%d rows), skipping.", row[0])
            conn.close()
            return

        logger.info("Starting keyword backfill from IMAGES.KEYWORDS...")

        # Fetch all images with non-empty keywords
        c.execute("""
            SELECT id, CAST(keywords AS VARCHAR(8191))
            FROM images
            WHERE keywords IS NOT NULL AND keywords <> ''
        """)
        rows = c.fetchall()
        logger.info("Backfill: found %d images with keywords.", len(rows))

        batch_size = 500
        total_links = 0

        for image_id, kw_blob in rows:
            if not kw_blob:
                continue

            # Parse comma-separated keywords
            raw_keywords = [k.strip() for k in kw_blob.split(',') if k.strip()]

            for kw_raw in raw_keywords:
                kw_norm = kw_raw.lower()  # normalize: lowercase

                # Upsert into KEYWORDS_DIM
                c.execute("""
                    UPDATE OR INSERT INTO keywords_dim (keyword_norm, keyword_display)
                    VALUES (?, ?)
                    MATCHING (keyword_norm)
                    RETURNING keyword_id
                """, (kw_norm, kw_raw))
                kw_row = c.fetchone()
                keyword_id = kw_row[0] if kw_row else None

                if keyword_id:
                    # Insert into IMAGE_KEYWORDS if not already linked
                    try:
                        c.execute("""
                            INSERT INTO image_keywords (image_id, keyword_id, source)
                            VALUES (?, ?, 'auto_backfill')
                        """, (image_id, keyword_id))
                        total_links += 1
                    except Exception:
                        pass  # PK violation = already linked, skip

            # Batch commit every N image rows
            if (image_id % batch_size) == 0:
                conn.commit()
                c = conn.cursor()

        conn.commit()
        logger.info("Keyword backfill complete: %d image-keyword links created.", total_links)

    except Exception as e:
        logger.error("Keyword backfill failed: %s", e)
        try: conn.rollback()
        except Exception: pass
    finally:
        conn.close()
```

Call this from `_init_db_impl()` after the Phase 2 table creation block:

```python
        # After 2.1b table creation block completes, call backfill once
        if _table_exists(c, 'KEYWORDS_DIM') and _table_exists(c, 'IMAGE_KEYWORDS'):
            conn.close()  # release connection before starting backfill
            _backfill_keywords()
            conn = get_db()  # reconnect
            c = conn.cursor()
```

### Step 2.3 — Add Dual-Write Helper (Python)

Add this helper function to `db.py`:

```python
def _sync_image_keywords(image_id: int, keywords_str: str):
    """
    Parse a comma-separated keywords string and sync into KEYWORDS_DIM + IMAGE_KEYWORDS.

    Called from upsert_image() and update_image_field() to keep IMAGES.KEYWORDS BLOB
    synchronized with normalized keyword tables (Phase 2 dual-write).

    Deletes any IMAGE_KEYWORDS rows for this image not in the new keyword set.
    """
    if not keywords_str or not image_id:
        return

    conn = get_db()
    c = conn.cursor()
    try:
        # Parse and normalize
        raw_keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
        new_keyword_ids = set()

        for kw_raw in raw_keywords:
            kw_norm = kw_raw.lower()

            # Upsert into keywords_dim
            c.execute("""
                UPDATE OR INSERT INTO keywords_dim (keyword_norm, keyword_display)
                VALUES (?, ?)
                MATCHING (keyword_norm)
                RETURNING keyword_id
            """, (kw_norm, kw_raw))
            row = c.fetchone()
            if row:
                keyword_id = row[0]
                new_keyword_ids.add(keyword_id)

                # Insert link if not present
                try:
                    c.execute("""
                        INSERT INTO image_keywords (image_id, keyword_id, source)
                        VALUES (?, ?, 'auto')
                    """, (image_id, keyword_id))
                except Exception:
                    pass  # PK conflict = already linked

        # Remove links for keywords no longer in the set
        if new_keyword_ids:
            placeholders = ','.join(['?'] * len(new_keyword_ids))
            c.execute(f"""
                DELETE FROM image_keywords
                WHERE image_id = ? AND keyword_id NOT IN ({placeholders})
            """, (image_id, *new_keyword_ids))
        else:
            c.execute("DELETE FROM image_keywords WHERE image_id = ?", (image_id,))

        conn.commit()
    except Exception as e:
        logger.warning("_sync_image_keywords for image_id %s: %s", image_id, e)
        try: conn.rollback()
        except Exception: pass
    finally:
        conn.close()
```

### Step 2.4 — Modify upsert_image() for Dual-Write (Python)

In `upsert_image()` (line 2653), after the main INSERT/UPDATE commits successfully:

```python
def upsert_image(job_id, result):
    # ... existing code ...
    # After successful commit of the image insert/update (around line 2910):

    # Phase 2 dual-write: sync keywords BLOB -> normalized KEYWORDS_DIM + IMAGE_KEYWORDS
    if image_id and keywords:
        try:
            _sync_image_keywords(image_id, keywords)
        except Exception as e:
            logger.warning("Keyword sync after upsert_image for image_id %s: %s", image_id, e)
```

### Step 2.5 — Modify update_image_field() for Dual-Write (Python)

In `update_image_field()` (line 1596), after the UPDATE commits when `field_name == 'keywords'`:

```python
def update_image_field(image_id: int, field_name: str, value) -> bool:
    # ... existing code ...
    # After successful commit:
    if field_name == 'keywords' and value:
        try:
            _sync_image_keywords(image_id, str(value))
        except Exception as e:
            logger.warning("Keyword sync after update_image_field: %s", e)
    return True
```

### Step 2.6 — Add IMAGE_XMP Backfill Function (Python)

Add to `db.py`:

```python
def _backfill_image_xmp():
    """
    One-time backfill: copy editable metadata from IMAGES into IMAGE_XMP.

    Inserts rows for images that don't yet have IMAGE_XMP rows.
    Called from _init_db_impl() after KEYWORDS_DIM/IMAGE_KEYWORDS backfill.
    """
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO image_xmp
              (image_id, rating, label, keywords, title, description, extracted_at)
            SELECT i.id,
                   i.rating,
                   i.label,
                   CAST(i.keywords AS VARCHAR(8191)),
                   i.title,
                   CAST(i.description AS VARCHAR(8191)),
                   CURRENT_TIMESTAMP
            FROM images i
            WHERE i.id NOT IN (SELECT image_id FROM image_xmp)
              AND (i.rating IS NOT NULL
                   OR i.label IS NOT NULL
                   OR i.keywords IS NOT NULL
                   OR i.title IS NOT NULL
                   OR i.description IS NOT NULL)
        """)
        conn.commit()

        c2 = conn.cursor()
        c2.execute("SELECT COUNT(*) FROM image_xmp")
        count = c2.fetchone()[0]
        logger.info("IMAGE_XMP backfill complete: %d rows in image_xmp.", count)

    except Exception as e:
        logger.error("IMAGE_XMP backfill failed: %s", e)
        try: conn.rollback()
        except Exception: pass
    finally:
        conn.close()
```

Call from `_init_db_impl()` after `_backfill_keywords()` completes:

```python
        # After keyword backfill
        _backfill_image_xmp()
```

### Step 2.7 — Electron Dual-Write in updateImageDetails() (Electron)

**File:** [db.ts](https://github.com/synthet/image-scoring-gallery/blob/main/electron/db.ts)

Add new helper function:

```typescript
async function syncImageKeywords(imageId: number, keywordsStr: string): Promise<void> {
    if (!keywordsStr) {
        await query('DELETE FROM image_keywords WHERE image_id = ?', [imageId]);
        invalidateKeywordsCache();
        return;
    }

    const rawKeywords = keywordsStr.split(',')
        .map(k => k.trim())
        .filter(k => k.length > 0);

    const newKeywordIds: number[] = [];

    for (const kw of rawKeywords) {
        const kwNorm = kw.toLowerCase();

        // Upsert into keywords_dim
        try {
            const rows = await query<{ keyword_id: number }>(
                `UPDATE OR INSERT INTO keywords_dim (keyword_norm, keyword_display)
                 VALUES (?, ?) MATCHING (keyword_norm) RETURNING keyword_id`,
                [kwNorm, kw]
            );
            if (rows.length > 0) {
                const kwId = rows[0].keyword_id;
                newKeywordIds.push(kwId);

                // Insert into image_keywords (ignore PK conflicts)
                try {
                    await query(
                        'INSERT INTO image_keywords (image_id, keyword_id, source) VALUES (?, ?, ?)',
                        [imageId, kwId, 'user']
                    );
                } catch {
                    // PK conflict = already linked, skip
                }
            }
        } catch (e) {
            console.warn(`[DB] Failed to sync keyword "${kw}":`, e);
        }
    }

    // Remove stale keyword links
    if (newKeywordIds.length > 0) {
        const placeholders = newKeywordIds.map(() => '?').join(',');
        await query(
            `DELETE FROM image_keywords WHERE image_id = ? AND keyword_id NOT IN (${placeholders})`,
            [imageId, ...newKeywordIds]
        );
    } else {
        await query('DELETE FROM image_keywords WHERE image_id = ?', [imageId]);
    }

    invalidateKeywordsCache();
}
```

Modify `updateImageDetails()` (~line 812) to call `syncImageKeywords()` when keywords are updated:

```typescript
export async function updateImageDetails(id: number, updates: Record<string, any>): Promise<unknown> {
    // ... existing code ...

    // Execute UPDATE query
    const result = await query(sql, params);

    // Phase 2 dual-write: sync keywords to normalized tables
    if (updates.keywords !== undefined && typeof updates.keywords === 'string') {
        try {
            await syncImageKeywords(id, updates.keywords);
        } catch (e) {
            console.error(`[DB] syncImageKeywords for image ${id} failed:`, e);
        }
    }

    return result;
}
```

### Phase 2: Verification Tests

After deploying Phase 2, verify:

```sql
-- 1. Keyword backfill coverage
SELECT COUNT(*) FROM images i
WHERE i.keywords IS NOT NULL AND i.keywords <> ''
  AND i.id NOT IN (SELECT image_id FROM image_keywords);
-- expect 0

-- 2. KEYWORDS_DIM has all keywords
SELECT COUNT(*) FROM keywords_dim;
SELECT COUNT(DISTINCT keyword_id) FROM image_keywords;
-- These should be approximately equal

-- 3. IMAGE_XMP has editable metadata
SELECT COUNT(*) FROM images WHERE rating IS NOT NULL
  AND id NOT IN (SELECT image_id FROM image_xmp);
-- expect 0

-- 4. Dual-write consistency spot-check
SELECT i.id,
       CAST(i.keywords AS VARCHAR(8191)) as img_keywords,
       STRING_AGG(kd.keyword_display, ', ' ORDER BY kd.keyword_display) as norm_keywords
FROM images i
LEFT JOIN image_keywords ik ON ik.image_id = i.id
LEFT JOIN keywords_dim kd ON kd.keyword_id = ik.keyword_id
WHERE i.keywords IS NOT NULL
GROUP BY i.id, i.keywords
ROWS 20;
-- Visually verify keyword strings match (within reasonable parsing differences)
```

---

## Phase 3: Electron Query Refactor

**Goal:** Replace slow BLOB queries with indexed alternatives. No IPC/API contract shape changes.

**File:** [db.ts](https://github.com/synthet/image-scoring-gallery/blob/main/electron/db.ts)

### Step 3.1 — Refactor getKeywords() (line 456)

Replace full-table BLOB scan with direct `KEYWORDS_DIM` read:

```typescript
export async function getKeywords(): Promise<string[]> {
    // Return cached result if fresh
    if (keywordsCache && (Date.now() - keywordsCache.timestamp) < KEYWORDS_CACHE_TTL) {
        console.log(`[DB] getKeywords returning cached result (${keywordsCache.result.length} keywords)`);
        return keywordsCache.result;
    }

    try {
        // Phase 3: Primary path — read from indexed KEYWORDS_DIM
        console.log('[DB] Executing getKeywords from KEYWORDS_DIM...');
        const rows = await query<{ keyword_display: string; keyword_norm: string }>(
            `SELECT keyword_display, keyword_norm FROM keywords_dim ORDER BY keyword_norm ASC`
        );

        const result = rows
            .map(r => r.keyword_display || r.keyword_norm)
            .filter(k => k && k.length > 0)
            .sort();

        console.log(`[DB] getKeywords returned ${result.length} keywords from KEYWORDS_DIM`);
        keywordsCache = { result, timestamp: Date.now() };
        return result;

    } catch (e) {
        console.warn('[DB] getKeywords from KEYWORDS_DIM failed, falling back to IMAGES BLOB scan:', e);

        // Fallback: legacy query if KEYWORDS_DIM not yet populated (during Phase 2→3 transition)
        try {
            const sql = `SELECT DISTINCT CAST(keywords AS VARCHAR(8191)) as keywords
                         FROM images WHERE keywords IS NOT NULL AND keywords <> ''`;
            const rows = await query<{ keywords: string | Buffer; KEYWORDS?: string | Buffer; KEYWORDS_1?: string | Buffer }>(sql);

            const uniqueKeywords = new Set<string>();
            for (const row of rows) {
                const val = row.keywords || row.KEYWORDS || row.KEYWORDS_1;
                let kwStr = '';
                if (val) {
                    if (Buffer.isBuffer(val)) {
                        kwStr = val.toString('utf8');
                    } else if (typeof val === 'string') {
                        kwStr = val;
                    }
                }
                if (kwStr) {
                    kwStr.split(',')
                        .map(s => s.trim())
                        .filter(s => s.length > 0)
                        .forEach(p => uniqueKeywords.add(p));
                }
            }

            const result = Array.from(uniqueKeywords).sort();
            console.log(`[DB] Fallback: Found ${result.length} unique keywords`);
            keywordsCache = { result, timestamp: Date.now() };
            return result;

        } catch (e2) {
            console.error('[DB] getKeywords fallback also failed:', e2);
            return [];
        }
    }
}
```

### Step 3.2 — Refactor Keyword Filters in Query Functions (Electron)

Replace all `keywords LIKE ?` queries with indexed EXISTS subquery pattern.

**In getImages()** (around line 399):

```typescript
// Old:
// if (options.keyword) {
//     whereParts.push(`keywords LIKE ?`);
//     params.push(`%${options.keyword}%`);
// }

// New (Phase 3):
if (options.keyword) {
    const kwNorm = options.keyword.toLowerCase().trim();
    whereParts.push(`EXISTS (
        SELECT 1 FROM image_keywords ik
        JOIN keywords_dim kd ON ik.keyword_id = kd.keyword_id
        WHERE ik.image_id = i.id
          AND kd.keyword_norm LIKE ?
    )`);
    params.push(`%${kwNorm}%`);
}
```

Apply the same replacement to:
- **getStacks()** (keyword filter for non-stack branch around line 1046-1050)
- **getImagesByStack()** (around line 1140-1143)
- **getStackCount()** (around line 1200-1203)

For getStacks, maintain the existing behavior where keyword filtering applies only to non-stack images (the fallback union branch).

### Step 3.3 — Refactor getFolders() Correlated Subquery (line 662)

Replace the N+1 correlated subquery with a single aggregate join:

```typescript
export async function getFolders(): Promise<unknown[]> {
    // Phase 3: Replace correlated subquery with aggregate join
    const rows = await query(`
        SELECT f.id, f.path, f.parent_id, f.is_fully_scored,
               COALESCE(cnt.image_count, 0) as image_count
        FROM folders f
        LEFT JOIN (
            SELECT folder_id, COUNT(1) as image_count
            FROM images
            WHERE folder_id IS NOT NULL
            GROUP BY folder_id
        ) cnt ON cnt.folder_id = f.id
        ORDER BY f.path ASC
    `);
    return rows;
}
```

### Step 3.4 — Simplify ensureStackCacheTable() (Already Done in Phase 1)

Verify `ensureStackCacheTable()` is now a probe-only function (from Phase 1):

```typescript
export async function ensureStackCacheTable(): Promise<void> {
    if (stackCacheInitPromise) return stackCacheInitPromise;
    stackCacheInitPromise = (async () => {
        await query(`SELECT 1 FROM stack_cache WHERE 1=0`);
    })();
    return stackCacheInitPromise;
}
```

### Phase 3: Verification Tests

After deploying Phase 3:

```sql
-- 1. getKeywords() performance (warm cache)
-- Time: getKeywords() call — target < 150ms
-- Log should show: "getKeywords returned X keywords from KEYWORDS_DIM"

-- 2. Keyword filter regression test
-- Before/after comparison: getImages({ keyword: 'portrait' })
-- Result set should be identical (same image IDs, same order)

-- 3. getFolders() image_count verification
-- Spot-check: SELECT folder_id, COUNT(*) FROM images GROUP BY folder_id
-- Compare against getFolders() results — counts should match

-- 4. No IPC contract changes
-- Verify that db:get-keywords, db:get-images handlers in main.ts are unchanged
-- Return types and field names must stay the same
```

Functional regression checklist:
- [ ] `getImages()` with no filters returns same count
- [ ] `getImages({ keyword: 'X' })` returns same result set
- [ ] `getStacks()` returns same stacks
- [ ] `getKeywords()` includes all previous keywords
- [ ] `getFolders()` lists same folders with matching image_counts
- [ ] IPC handlers unchanged (no client-side code changes required)

---

## Phase 4: Cutover + Deprecation (Future Major Version)

**Status:** Deferred until Phase 3 gates pass across one full release cycle.

Do not implement Phase 4 until:
1. Phase 1, 2, 3 are live in production
2. All Phase 2 & 3 verification tests pass
3. One full release cycle has passed with no sync inconsistencies reported
4. Dual-write performance is acceptable

### Phase 4 Steps (planned, not yet executable)

#### 4.1 — Final Consistency Validation

```sql
-- All keyword links consistent
SELECT COUNT(*) FROM images i
WHERE i.keywords IS NOT NULL AND i.keywords <> ''
  AND i.id NOT IN (SELECT image_id FROM image_keywords);
-- must be 0

-- All editable metadata in IMAGE_XMP
SELECT COUNT(*) FROM images WHERE rating IS NOT NULL
  AND id NOT IN (SELECT image_id FROM image_xmp);
-- must be 0
```

#### 4.2 — Create Compatibility View

```sql
CREATE VIEW images_legacy_metadata_v AS
SELECT i.id,
       COALESCE(x.rating, i.rating) as rating,
       COALESCE(x.label, i.label) as label,
       COALESCE(CAST(x.keywords AS VARCHAR(8191)), CAST(i.keywords AS VARCHAR(8191))) as keywords,
       COALESCE(x.title, i.title) as title,
       COALESCE(CAST(x.description AS VARCHAR(8191)), CAST(i.description AS VARCHAR(8191))) as description
FROM images i
LEFT JOIN image_xmp x ON x.image_id = i.id;
```

#### 4.3 — Switch Write Path (IMAGE_XMP becomes canonical)

Update `update_image_field()` and `updateImageDetails()` to write to `IMAGE_XMP` first, then mirror to `IMAGES` for backward compatibility.

#### 4.4 — Drop Legacy Columns (after final validation + maintenance window)

```sql
-- Note: Firebird requires separate ALTER for each column
ALTER TABLE images DROP keywords;
ALTER TABLE images DROP title;
ALTER TABLE images DROP description;
ALTER TABLE images DROP rating;
ALTER TABLE images DROP label;
```

---

## Summary: File-by-File Changes

| Phase | File | Changes |
|---|---|---|
| 0 | N/A | Run SQL audit queries, take backup |
| 1 | `db.py` | Add Phase 1 migration block before line 1564 (1.1-1.8) |
| 1 | `db.ts` | Simplify `ensureStackCacheTable()` (~line 860) |
| 2 | `db.py` | Add Phase 2 migration block (2.1-2.2), add `_sync_image_keywords()` helper, add `_backfill_image_xmp()` helper; modify `upsert_image()` (line 2653) and `update_image_field()` (line 1596) |
| 2 | `db.ts` | Add `syncImageKeywords()` helper; modify `updateImageDetails()` (~line 812) |
| 3 | `db.ts` | Refactor `getKeywords()` (line 456), `getImages()` keyword filter (~line 399), `getStacks()` (~line 1046), `getImagesByStack()` (~line 1140), `getStackCount()` (~line 1200), `getFolders()` (line 662) |
| 4 | Both | Switch write paths, drop columns (future) |

---

## Rollback Plan

| Phase | Rollback Method |
|---|---|
| Phase 1 | Restore pre-Phase1 gbak backup (`SCORING_HISTORY.FDB`) |
| Phase 2 | Drop `KEYWORDS_DIM` + `IMAGE_KEYWORDS`; revert Python dual-write calls (IMAGES.KEYWORDS BLOB unchanged) |
| Phase 3 | Git revert `electron/db.ts` query changes |
| Phase 4 | Restore pre-Phase4 backup (column drops are irreversible) |

---

## Appendix: Performance Targets

### Phase 1 Expected Improvements
- `findImageByFilePath()`: 136ms → <25ms (index on `FILE_PATH`)
- `findImageByUuid()`: 142ms → <25ms (recomputed statistics on `IMAGE_UUID` index)

### Phase 3 Expected Improvements
- `getKeywords()`: ~3.5s → <150ms warm (indexed table read instead of BLOB scan)
- `getImages({ keyword: 'X' })`: O(n rows) → O(n keywords) (EXISTS subquery instead of LIKE scan)
- `getFolders()`: O(n folders) → O(1) hash join (aggregate instead of correlated subquery)

### Phase 2 Consistency
- Zero keyword sync mismatches between `IMAGES.KEYWORDS` and `IMAGE_KEYWORDS` (dual-write validation)
- Zero missing `IMAGE_XMP` rows for images with editable metadata

