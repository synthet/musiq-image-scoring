-- Cull decision distribution audit (images.cull_decision + cull_policy_version).
-- PostgreSQL only. Run sections independently or as a batch in psql.
--
-- Policy 1.0: floor(n*0.33) pick/reject bands per stack or sub-group.
-- Policy 2.0: best-M per sub-stack, cap N=20 per root stack (see two-level-culling.md).

-- ---------------------------------------------------------------------------
-- 1) Library totals by policy version and decision
-- ---------------------------------------------------------------------------
SELECT
    COALESCE(cull_policy_version, 'unset') AS policy,
    COALESCE(NULLIF(TRIM(cull_decision), ''), 'unset') AS cull_decision,
    COUNT(*)::int AS cnt
FROM images
WHERE cull_decision IS NOT NULL AND TRIM(cull_decision) <> ''
GROUP BY 1, 2
ORDER BY 1, 2;

-- ---------------------------------------------------------------------------
-- 2) pick_status vs cull_decision drift (batch_update_cull_decisions syncs pick_status since 2026-06)
-- ---------------------------------------------------------------------------
SELECT
    pick_status,
    COALESCE(NULLIF(TRIM(cull_decision), ''), 'unset') AS cull_decision,
    COUNT(*)::int AS cnt
FROM images
WHERE cull_decision IS NOT NULL AND TRIM(cull_decision) <> ''
GROUP BY 1, 2
ORDER BY 1, 2;

SELECT COUNT(*)::int AS pick_status_cull_decision_disagree
FROM images
WHERE (
    (pick_status = 1 AND LOWER(TRIM(COALESCE(cull_decision, ''))) = 'reject')
    OR (pick_status = -1 AND LOWER(TRIM(COALESCE(cull_decision, ''))) = 'pick')
);

-- ---------------------------------------------------------------------------
-- 3) Per root stack — policy 1.0 (33/33 band invariant for n >= 3)
-- ---------------------------------------------------------------------------
WITH per_stack AS (
    SELECT
        i.stack_id,
        COUNT(*)::int AS n,
        COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'pick')::int AS picks,
        COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'reject')::int AS rejects,
        COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'neutral')::int AS neutrals,
        FLOOR(COUNT(*) * 0.33)::int AS expected_k
    FROM images i
    WHERE i.cull_policy_version = '1.0'
      AND i.stack_id IS NOT NULL
    GROUP BY i.stack_id
)
SELECT
    n AS stack_size,
    COUNT(*)::int AS stacks,
    AVG(picks::float) AS avg_picks,
    AVG(rejects::float) AS avg_rejects,
    AVG(neutrals::float) AS avg_neutrals
FROM per_stack
GROUP BY n
ORDER BY n;

-- Policy 1.0 violations: n>=3 but picks/rejects != floor(n*0.33)
WITH per_stack AS (
    SELECT
        i.stack_id,
        COUNT(*)::int AS n,
        COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'pick')::int AS picks,
        COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'reject')::int AS rejects,
        FLOOR(COUNT(*) * 0.33)::int AS expected_k
    FROM images i
    WHERE i.cull_policy_version = '1.0'
      AND i.stack_id IS NOT NULL
    GROUP BY i.stack_id
    HAVING COUNT(*) >= 3
)
SELECT COUNT(*)::int AS policy_10_band_violations
FROM per_stack
WHERE picks <> expected_k OR rejects <> expected_k;

-- ---------------------------------------------------------------------------
-- 4) Per root stack — policy 2.0 (cap N=20 picks per stack)
-- ---------------------------------------------------------------------------
WITH per_stack AS (
    SELECT
        i.stack_id,
        COUNT(*)::int AS n,
        COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'pick')::int AS picks,
        COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'reject')::int AS rejects,
        COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'neutral')::int AS neutrals,
        COUNT(DISTINCT i.sub_stack_id)::int AS leaf_count
    FROM images i
    WHERE i.cull_policy_version = '2.0'
      AND i.stack_id IS NOT NULL
    GROUP BY i.stack_id
)
SELECT
    COUNT(*)::int AS stacks,
    COUNT(*) FILTER (WHERE picks > 20)::int AS over_cap_n20,
    COUNT(*) FILTER (WHERE picks = 20)::int AS at_cap_n20,
    AVG(picks::float) AS avg_picks,
    AVG(rejects::float) AS avg_rejects,
    AVG(neutrals::float) AS avg_neutrals,
    AVG(leaf_count::float) AS avg_leaves
FROM per_stack;

-- Policy 2.0 stack size histogram
WITH per_stack AS (
    SELECT
        COUNT(*)::int AS n,
        COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'pick')::int AS picks,
        COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'reject')::int AS rejects
    FROM images i
    WHERE i.cull_policy_version = '2.0'
      AND i.stack_id IS NOT NULL
    GROUP BY i.stack_id
)
SELECT
    n AS stack_size,
    COUNT(*)::int AS stacks,
    AVG(picks::float) AS avg_picks,
    AVG(rejects::float) AS avg_rejects
FROM per_stack
GROUP BY n
ORDER BY n
LIMIT 25;

-- ---------------------------------------------------------------------------
-- 5) Per sub-stack — policy 2.0 (M=3 picks per leaf)
-- ---------------------------------------------------------------------------
WITH per_sub AS (
    SELECT
        ss.id AS sub_stack_id,
        ss.stack_id,
        COUNT(*)::int AS n,
        COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'pick')::int AS picks,
        COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'reject')::int AS rejects,
        COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'neutral')::int AS neutrals
    FROM sub_stacks ss
    JOIN images i ON i.sub_stack_id = ss.id
    WHERE i.cull_policy_version = '2.0'
    GROUP BY ss.id, ss.stack_id
)
SELECT
    n AS substack_size,
    COUNT(*)::int AS substacks,
    AVG(picks::float) AS avg_picks,
    AVG(rejects::float) AS avg_rejects,
    AVG(neutrals::float) AS avg_neutrals,
    MIN(picks) AS min_picks,
    MAX(picks) AS max_picks
FROM per_sub
GROUP BY n
ORDER BY n
LIMIT 30;

-- Sub-stack violations: picks > 3 (M cap) on multi-image leaves
WITH per_sub AS (
    SELECT
        ss.id AS sub_stack_id,
        COUNT(*)::int AS n,
        COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'pick')::int AS picks
    FROM sub_stacks ss
    JOIN images i ON i.sub_stack_id = ss.id
    WHERE i.cull_policy_version = '2.0'
    GROUP BY ss.id
)
SELECT COUNT(*)::int AS substacks_picks_over_m3
FROM per_sub
WHERE picks > 3;

-- Singleton leaf rate (target ~35% at threshold 0.06 per CULLING_EMBEDDING_BACKFILL.md)
WITH leaf_sizes AS (
    SELECT ss.id, COUNT(i.id)::int AS image_count
    FROM sub_stacks ss
    JOIN images i ON i.sub_stack_id = ss.id
    WHERE i.cull_policy_version = '2.0'
    GROUP BY ss.id
)
SELECT
    COUNT(*)::int AS total_substacks,
    COUNT(*) FILTER (WHERE image_count = 1)::int AS singleton_leaves,
    ROUND(100.0 * COUNT(*) FILTER (WHERE image_count = 1) / NULLIF(COUNT(*), 0), 1) AS singleton_pct
FROM leaf_sizes;

-- Giant unsplit leaves (failed sub-split or missing embeddings)
WITH leaf_sizes AS (
    SELECT
        ss.id AS sub_stack_id,
        ss.stack_id,
        COUNT(i.id)::int AS image_count,
        COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'pick')::int AS picks
    FROM sub_stacks ss
    JOIN images i ON i.sub_stack_id = ss.id
    WHERE i.cull_policy_version = '2.0'
    GROUP BY ss.id, ss.stack_id
)
SELECT sub_stack_id, stack_id, image_count, picks
FROM leaf_sizes
WHERE image_count > 50
ORDER BY image_count DESC
LIMIT 20;

-- ---------------------------------------------------------------------------
-- 6) Unstacked bucket (stack_id IS NULL) — 33/33 per folder bucket
-- ---------------------------------------------------------------------------
SELECT
    cull_policy_version,
    COALESCE(NULLIF(TRIM(cull_decision), ''), 'unset') AS cull_decision,
    COUNT(*)::int AS cnt
FROM images
WHERE stack_id IS NULL
  AND cull_decision IS NOT NULL
  AND TRIM(cull_decision) <> ''
GROUP BY 1, 2
ORDER BY 1, 2;

-- Per-folder unstacked distribution (sample folders with most unstacked images)
SELECT
    i.folder_id,
    i.cull_policy_version,
    COUNT(*)::int AS n,
    COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'pick')::int AS picks,
    COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'reject')::int AS rejects,
    COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'neutral')::int AS neutrals,
    FLOOR(COUNT(*) * 0.33)::int AS expected_k
FROM images i
WHERE i.stack_id IS NULL
  AND i.cull_policy_version IN ('1.0', '2.0')
  AND i.cull_decision IS NOT NULL
GROUP BY i.folder_id, i.cull_policy_version
HAVING COUNT(*) >= 10
ORDER BY n DESC
LIMIT 15;

-- ---------------------------------------------------------------------------
-- 7) One-time pick_status backfill (run via scripts/backfill_pick_status_from_cull_decision.py)
-- ---------------------------------------------------------------------------
-- UPDATE images
-- SET pick_status = CASE LOWER(TRIM(cull_decision))
--     WHEN 'pick' THEN 1 WHEN 'reject' THEN -1 WHEN 'neutral' THEN 0 ELSE pick_status END
-- WHERE cull_decision IS NOT NULL AND TRIM(cull_decision) <> ''
--   AND LOWER(TRIM(cull_decision)) IN ('pick', 'reject', 'neutral');
