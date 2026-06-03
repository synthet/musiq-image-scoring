-- Embedding coverage for default MobileNet space. PostgreSQL.
SELECT es.code, es.dim,
       COUNT(DISTINCT e.image_id)::int AS images_with_embedding,
       (SELECT COUNT(*)::int FROM images) AS total_images
FROM embedding_spaces es
LEFT JOIN image_embeddings e ON e.embedding_space_id = es.id
WHERE es.code = 'mobilenet_v2_imagenet_gap'
GROUP BY es.code, es.dim;

-- Intra-stack avg cosine similarity (example stack_id = 1)
SELECT AVG(1 - (a.embedding <=> b.embedding))::float AS avg_cosine_sim
FROM image_embeddings a
JOIN image_embeddings b
  ON a.embedding_space_id = b.embedding_space_id AND a.image_id < b.image_id
JOIN images i ON i.id = a.image_id
WHERE i.stack_id = 1
  AND a.embedding_space_id = (SELECT id FROM embedding_spaces WHERE code = 'mobilenet_v2_imagenet_gap' LIMIT 1);
