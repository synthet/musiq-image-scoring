-- Stack size distribution (library-wide). PostgreSQL.
WITH stack_sizes AS (
    SELECT stack_id, COUNT(*)::int AS cnt
    FROM images
    WHERE stack_id IS NOT NULL
    GROUP BY stack_id
)
SELECT
    COUNT(*)::int AS total_stacks,
    COALESCE(SUM(cnt), 0)::int AS total_stacked_images,
    MIN(cnt) AS min_size,
    MAX(cnt) AS max_size,
    AVG(cnt)::float AS avg_size,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY cnt) AS median_size,
    COUNT(*) FILTER (WHERE cnt = 1)::int AS singleton_stacks
FROM stack_sizes;

SELECT COUNT(*)::int AS unstacked_images FROM images WHERE stack_id IS NULL;
