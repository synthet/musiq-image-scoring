-- Stack / sub-stack hierarchy audit (pick/reject/neutral, degenerate tiers, RCA hints).
-- PostgreSQL only. Run sections independently or as a batch in psql.
--
-- Degenerate tiers:
--   singleton_root_stacks     — root stack with exactly 1 image (clustering never creates these)
--   single_leaf_stacks        — n >= 2 but exactly 1 sub-stack leaf (redundant 1:1 hierarchy)
-- Populated tier:
--   multi_leaf_stacks         — leaf_count >= 2
-- Expected (not degenerate):
--   singleton_leaves          — size-1 sub-stacks inside multi-leaf stacks (~35% at threshold 0.06)

-- ---------------------------------------------------------------------------
-- 1) Library totals — cull_decision and pick_status
-- ---------------------------------------------------------------------------
SELECT
    COALESCE(cull_policy_version, 'unset') AS policy,
    COALESCE(NULLIF(TRIM(cull_decision), ''), 'unset') AS cull_decision,
    COUNT(*)::int AS cnt
FROM images
WHERE cull_decision IS NOT NULL AND TRIM(cull_decision) <> ''
GROUP BY 1, 2
ORDER BY 1, 2;

SELECT
    CASE pick_status WHEN 1 THEN 'pick' WHEN -1 THEN 'reject' ELSE 'neutral' END AS pick_status,
    COUNT(*)::int AS cnt
FROM images
GROUP BY 1
ORDER BY 1;

-- ---------------------------------------------------------------------------
-- 2) Per root stack — size, leaf count, decisions
-- ---------------------------------------------------------------------------
WITH per_stack AS (
    SELECT
        i.stack_id,
        COUNT(*)::int AS n,
        COUNT(DISTINCT i.sub_stack_id) FILTER (WHERE i.sub_stack_id IS NOT NULL)::int AS leaf_count,
        COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'pick')::int AS picks,
        COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'reject')::int AS rejects,
        COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'neutral')::int AS neutrals,
        MODE() WITHIN GROUP (ORDER BY i.cull_policy_version) AS policy_version
    FROM images i
    WHERE i.stack_id IS NOT NULL
    GROUP BY i.stack_id
)
SELECT
    stack_id,
    n,
    leaf_count,
    picks,
    rejects,
    neutrals,
    policy_version
FROM per_stack
ORDER BY n DESC, stack_id
LIMIT 50;

-- ---------------------------------------------------------------------------
-- 3) Per sub-stack — size and decisions
-- ---------------------------------------------------------------------------
WITH per_sub AS (
    SELECT
        ss.id AS sub_stack_id,
        ss.stack_id,
        COUNT(i.id)::int AS n,
        COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'pick')::int AS picks,
        COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'reject')::int AS rejects,
        COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'neutral')::int AS neutrals
    FROM sub_stacks ss
    JOIN images i ON i.sub_stack_id = ss.id
    GROUP BY ss.id, ss.stack_id
)
SELECT
    sub_stack_id,
    stack_id,
    n,
    picks,
    rejects,
    neutrals
FROM per_sub
ORDER BY n DESC, sub_stack_id
LIMIT 50;

-- ---------------------------------------------------------------------------
-- 4) Degenerate tier summary
-- ---------------------------------------------------------------------------
WITH per_stack AS (
    SELECT
        i.stack_id,
        COUNT(*)::int AS n,
        COUNT(DISTINCT i.sub_stack_id) FILTER (WHERE i.sub_stack_id IS NOT NULL)::int AS leaf_count,
        COUNT(*) FILTER (WHERE i.sub_stack_id IS NOT NULL)::int AS images_with_substack
    FROM images i
    WHERE i.stack_id IS NOT NULL
    GROUP BY i.stack_id
),
classified AS (
    SELECT
        stack_id,
        n,
        leaf_count,
        CASE
            WHEN n = 1 THEN 'singleton_root'
            WHEN n >= 2 AND leaf_count = 1 AND images_with_substack = n THEN 'single_leaf'
            WHEN n >= 2 AND leaf_count = 0 THEN 'flat'
            WHEN leaf_count >= 2 THEN 'populated_multi_leaf'
            ELSE 'other'
        END AS tier
    FROM per_stack
)
SELECT
    tier,
    COUNT(*)::int AS stacks,
    COALESCE(SUM(n), 0)::int AS total_images
FROM classified
GROUP BY tier
ORDER BY stacks DESC;

-- Singleton root stacks (sample)
WITH per_stack AS (
    SELECT i.stack_id, COUNT(*)::int AS n
    FROM images i
    WHERE i.stack_id IS NOT NULL
    GROUP BY i.stack_id
    HAVING COUNT(*) = 1
)
SELECT ps.stack_id, ps.n,
       COUNT(*) FILTER (WHERE i.sub_stack_id IS NOT NULL)::int AS has_sub_stack_id
FROM per_stack ps
JOIN images i ON i.stack_id = ps.stack_id
GROUP BY ps.stack_id, ps.n
ORDER BY ps.stack_id
LIMIT 25;

-- Single-leaf stacks (redundant 1:1 hierarchy, sample)
WITH per_stack AS (
    SELECT
        i.stack_id,
        COUNT(*)::int AS n,
        COUNT(DISTINCT i.sub_stack_id) FILTER (WHERE i.sub_stack_id IS NOT NULL)::int AS leaf_count,
        COUNT(*) FILTER (WHERE i.sub_stack_id IS NOT NULL)::int AS images_with_substack
    FROM images i
    WHERE i.stack_id IS NOT NULL
    GROUP BY i.stack_id
    HAVING COUNT(*) >= 2
       AND COUNT(DISTINCT i.sub_stack_id) FILTER (WHERE i.sub_stack_id IS NOT NULL) = 1
       AND COUNT(*) FILTER (WHERE i.sub_stack_id IS NOT NULL) = COUNT(*)
)
SELECT stack_id, n, leaf_count
FROM per_stack
ORDER BY n DESC
LIMIT 25;

-- ---------------------------------------------------------------------------
-- 5) Expected singleton leaves (inside multi-leaf stacks — not degenerate)
-- ---------------------------------------------------------------------------
WITH leaf_sizes AS (
    SELECT
        ss.id AS sub_stack_id,
        ss.stack_id,
        COUNT(i.id)::int AS image_count
    FROM sub_stacks ss
    JOIN images i ON i.sub_stack_id = ss.id
    GROUP BY ss.id, ss.stack_id
),
stack_leaves AS (
    SELECT stack_id, COUNT(*)::int AS leaf_count
    FROM leaf_sizes
    GROUP BY stack_id
)
SELECT
    COUNT(*)::int AS expected_singleton_leaves,
    COUNT(DISTINCT ls.stack_id)::int AS stacks_with_singleton_leaves
FROM leaf_sizes ls
JOIN stack_leaves sl ON sl.stack_id = ls.stack_id
WHERE ls.image_count = 1
  AND sl.leaf_count >= 2;

-- ---------------------------------------------------------------------------
-- 6) RCA hints per degenerate stack (level2 embedding coverage)
-- ---------------------------------------------------------------------------
WITH per_stack AS (
    SELECT
        i.stack_id,
        COUNT(*)::int AS n,
        COUNT(DISTINCT i.sub_stack_id) FILTER (WHERE i.sub_stack_id IS NOT NULL)::int AS leaf_count,
        COUNT(*) FILTER (WHERE i.sub_stack_id IS NOT NULL)::int AS images_with_substack,
        COUNT(DISTINCT i.cull_policy_version)::int AS policy_versions
    FROM images i
    WHERE i.stack_id IS NOT NULL
    GROUP BY i.stack_id
),
emb_coverage AS (
    SELECT
        i.stack_id,
        COUNT(DISTINCT i.id)::int AS total_ids,
        COUNT(DISTINCT ie.image_id)::int AS with_embedding
    FROM images i
    LEFT JOIN image_embeddings_768 ie
        ON ie.image_id = i.id
       AND ie.embedding_space_id = (
           SELECT id FROM embedding_spaces WHERE code = 'openclip_l14_laion2b_image' LIMIT 1
       )
    WHERE i.stack_id IS NOT NULL
    GROUP BY i.stack_id
)
SELECT
    ps.stack_id,
    ps.n,
    ps.leaf_count,
    ROUND(100.0 * ec.with_embedding / NULLIF(ec.total_ids, 0), 1) AS embedding_coverage_pct,
    CASE WHEN ps.n = 1 THEN true ELSE false END AS cause_singleton_root,
    CASE WHEN ps.n = 2 AND ps.leaf_count = 1 THEN true ELSE false END AS cause_stack_size_2,
    CASE WHEN ps.leaf_count = 1 AND ps.n >= 2
              AND ec.with_embedding < ec.total_ids THEN true ELSE false END AS cause_embedding_fallback,
    CASE WHEN ps.n = 1 AND ps.images_with_substack > 0 THEN true ELSE false END AS cause_stale_sub_stack_id,
    CASE WHEN ps.policy_versions > 1 THEN true ELSE false END AS cause_mixed_policy
FROM per_stack ps
JOIN emb_coverage ec ON ec.stack_id = ps.stack_id
WHERE ps.n = 1
   OR (ps.n >= 2 AND ps.leaf_count = 1 AND ps.images_with_substack = ps.n)
ORDER BY ps.n DESC, ps.stack_id
LIMIT 50;

-- ---------------------------------------------------------------------------
-- 7) Per-stack decision averages (stacked images only)
-- ---------------------------------------------------------------------------
WITH per_stack AS (
    SELECT
        i.stack_id,
        COUNT(*)::int AS n,
        COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'pick')::int AS picks,
        COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'reject')::int AS rejects,
        COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'neutral')::int AS neutrals
    FROM images i
    WHERE i.stack_id IS NOT NULL
    GROUP BY i.stack_id
)
SELECT
    COUNT(*)::int AS total_stacks,
    AVG(picks::float) AS avg_picks_per_stack,
    AVG(rejects::float) AS avg_rejects_per_stack,
    AVG(neutrals::float) AS avg_neutrals_per_stack
FROM per_stack;

-- Per sub-stack decision averages
WITH per_sub AS (
    SELECT
        ss.id,
        COUNT(i.id)::int AS n,
        COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'pick')::int AS picks,
        COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'reject')::int AS rejects,
        COUNT(*) FILTER (WHERE LOWER(TRIM(i.cull_decision)) = 'neutral')::int AS neutrals
    FROM sub_stacks ss
    JOIN images i ON i.sub_stack_id = ss.id
    GROUP BY ss.id
)
SELECT
    COUNT(*)::int AS total_substacks,
    AVG(picks::float) AS avg_picks_per_substack,
    AVG(rejects::float) AS avg_rejects_per_substack,
    AVG(neutrals::float) AS avg_neutrals_per_substack
FROM per_sub;
