-- Score coverage and spread per stack (stack_cache). PostgreSQL.
SELECT
    stack_id,
    image_count,
    min_score_general,
    max_score_general,
    (max_score_general - min_score_general) AS spread
FROM stack_cache
WHERE image_count > 1
ORDER BY image_count DESC
LIMIT 20;
