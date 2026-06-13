-- Pick/reject distribution. PostgreSQL.
-- Manual/gallery layer: images.pick_status (-1 reject, 0 neutral, 1 pick).
-- Auto-cull layer: images.cull_decision (pick/reject/neutral) — see 05_cull_decision_distribution.sql.

SELECT pick_status, COUNT(*)::int AS cnt
FROM images
GROUP BY pick_status
ORDER BY pick_status;

SELECT
    COALESCE(cull_policy_version, 'unset') AS policy,
    COALESCE(NULLIF(TRIM(cull_decision), ''), 'unset') AS cull_decision,
    COUNT(*)::int AS cnt
FROM images
WHERE cull_decision IS NOT NULL AND TRIM(cull_decision) <> ''
GROUP BY 1, 2
ORDER BY 1, 2;

-- Stacks with multiple picks (pick_status)
SELECT stack_id, COUNT(*) FILTER (WHERE pick_status = 1)::int AS picks
FROM images
WHERE stack_id IS NOT NULL
GROUP BY stack_id
HAVING COUNT(*) FILTER (WHERE pick_status = 1) > 1;

-- Stacks with multiple auto-cull picks (cull_decision)
SELECT stack_id, COUNT(*) FILTER (WHERE LOWER(TRIM(cull_decision)) = 'pick')::int AS picks
FROM images
WHERE stack_id IS NOT NULL
GROUP BY stack_id
HAVING COUNT(*) FILTER (WHERE LOWER(TRIM(cull_decision)) = 'pick') > 20;
