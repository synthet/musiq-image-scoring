import logging

import numpy as np

logger = logging.getLogger(__name__)

def compute_pairwise_similarities(embeddings_list):
    """
    Compute pairwise cosine similarity matrix for a list of embeddings.
    embeddings_list: list of 1D numpy arrays (or None for missing).
    Returns a 2D numpy array of shape (N, N). Missing embeddings have 0 similarity.
    """
    n = len(embeddings_list)
    sim_matrix = np.zeros((n, n), dtype=np.float32)
    
    valid_idx = []
    valid_vecs = []
    for i, vec in enumerate(embeddings_list):
        if vec is not None and len(vec) > 0:
            valid_idx.append(i)
            valid_vecs.append(vec)
            
    if not valid_vecs:
        return sim_matrix
        
    # Stack valid vectors
    vectors = np.stack(valid_vecs)
    
    # Normalize vectors to unit length for cosine similarity
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    # Avoid division by zero just in case
    norms[norms == 0] = 1.0
    normalized_vectors = vectors / norms
    
    # Compute similarity matrix for valid vectors
    valid_sim = np.dot(normalized_vectors, normalized_vectors.T)
    
    # Map back to full matrix
    for i, idx_i in enumerate(valid_idx):
        for j, idx_j in enumerate(valid_idx):
            sim_matrix[idx_i, idx_j] = valid_sim[i, j]
            
    return sim_matrix

def reorder_with_mmr(sorted_images, k, embeddings_dict, lambda_val=0.7, score_key="score_general"):
    """
    Reorder the first part of sorted_images using Maximal Marginal Relevance (MMR).
    
    Args:
        sorted_images: list of dicts, pre-sorted by score descending.
        k: number of picks to select (will be reordered).
        embeddings_dict: mapping from image ID to raw embedding bytes.
        lambda_val: balance between score (1.0) and diversity (0.0).
        score_key: key to extract score from image objects.
        
    Returns:
        List of reordered images.
    """
    n = len(sorted_images)
    if k <= 0 or n <= 2 or lambda_val >= 1.0:
        return sorted_images.copy()
        
    # Extract IDs and Scores
    image_ids = [img.get("id") for img in sorted_images]
    scores = np.array([img.get(score_key, 0) for img in sorted_images], dtype=np.float32)
    
    # Normalize scores to [0, 1] within this stack context
    min_score = np.min(scores)
    max_score = np.max(scores)
    if max_score > min_score:
        normalized_scores = (scores - min_score) / (max_score - min_score)
    else:
        normalized_scores = np.ones_like(scores)

    # Convert embeddings from bytes to numpy arrays
    embeddings_list = []
    for uid in image_ids:
        raw_bytes = embeddings_dict.get(uid)
        if raw_bytes:
            try:
                # Assuming embeddings are serialized numpy arrays (float32)
                # Depends on how they are stored (e.g., np.frombuffer)
                emb_array = np.frombuffer(raw_bytes, dtype=np.float32)
                embeddings_list.append(emb_array)
            except Exception as e:
                logger.warning(f"Failed to parse embedding for {uid}: {e}")
                embeddings_list.append(None)
        else:
            embeddings_list.append(None)
            
    # Compute similarity matrix
    sim_matrix = compute_pairwise_similarities(embeddings_list)
    
    selected_indices = []
    remaining_indices = list(range(n))
    
    # Select the first item based purely on max normalized score
    # Since they are pre-sorted, it's just index 0 (if multiple, index 0 is fine)
    first_choice = 0
    selected_indices.append(first_choice)
    remaining_indices.remove(first_choice)
    
    # Iteratively select the rest up to k
    for _ in range(1, min(k, n)):
        best_mmr = -float('inf')
        best_idx = -1
        
        for idx in remaining_indices:
            # Max similarity to already selected items
            max_sim = 0.0
            for sel_idx in selected_indices:
                max_sim = max(max_sim, sim_matrix[idx, sel_idx])
                
            mmr_score = lambda_val * normalized_scores[idx] - (1.0 - lambda_val) * max_sim
            
            if mmr_score > best_mmr:
                best_mmr = mmr_score
                best_idx = idx
                
            # Tie breaker: we just take the first we see with max mmr
            # Since remaining_indices are ordered initially by score/tie-breakers,
            # strict greater than maintains stable fallback.
            
        selected_indices.append(best_idx)
        remaining_indices.remove(best_idx)
        
    # Reconstruct final list: selected picks followed by remaining neutral/rejects
    result = []
    for idx in selected_indices:
        result.append(sorted_images[idx])
    for idx in remaining_indices:
        result.append(sorted_images[idx])
        
    return result
