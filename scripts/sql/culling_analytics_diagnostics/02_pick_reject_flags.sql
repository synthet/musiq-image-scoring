-- Pick/reject distribution (images.pick_status). PostgreSQL.
SELECT pick_status, COUNT(*)::int AS cnt
FROM images
GROUP BY pick_status
ORDER BY pick_status;

-- Stacks with multiple picks
SELECT stack_id, COUNT(*) FILTER (WHERE pick_status = 1)::int AS picks
FROM images
WHERE stack_id IS NOT NULL
GROUP BY stack_id
HAVING COUNT(*) FILTER (WHERE pick_status = 1) > 1;
