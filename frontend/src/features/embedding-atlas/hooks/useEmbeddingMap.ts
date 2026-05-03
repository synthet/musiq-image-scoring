import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';

export interface EmbeddingPoint {
  image_id: number;
  x: number;
  y: number;
  file_path: string;
  thumbnail_path: string | null;
  label: string | null;
  rating: number | null;
  score_general: number | null;
  score_technical?: number | null;
  score_aesthetic?: number | null;
  score_spaq?: number | null;
  score_ava?: number | null;
  score_koniq?: number | null;
  score_paq2piq?: number | null;
  score_liqe?: number | null;
}

export interface EmbeddingMapResponse {
  points: EmbeddingPoint[];
  meta: {
    count: number;
    method: string;
    computed_at?: string;
    cache_key?: string;
    embedding_space: string;
    pca_dim: number;
    /** Present when method is umap; may be lower than requested when N is small. */
    n_neighbors_effective?: number;
    error?: string;
  };
}

export interface FetchEmbeddingMapParams {
  folder_path?: string;
  method?: 'umap' | 'tsne';
  refresh?: boolean;
  sample_limit?: number;
  n_neighbors?: number;
  min_dist?: number;
  space_code?: string;
  pca_dim?: number;
}

export async function fetchEmbeddingMap(params: FetchEmbeddingMapParams): Promise<EmbeddingMapResponse> {
  const query = new URLSearchParams();
  if (params.folder_path) query.set('folder_path', params.folder_path);
  if (params.method) query.set('method', params.method);
  if (params.refresh) query.set('refresh', 'true');
  if (params.sample_limit) query.set('sample_limit', params.sample_limit.toString());
  if (params.n_neighbors) query.set('n_neighbors', params.n_neighbors.toString());
  if (params.min_dist) query.set('min_dist', params.min_dist.toString());
  if (params.space_code) query.set('space_code', params.space_code);
  if (params.pca_dim !== undefined) query.set('pca_dim', params.pca_dim.toString());

  const res = await api.get<any>(`/embedding_map?${query.toString()}`);
  return res.data ? res.data : res;
}

export function useEmbeddingMap(params: FetchEmbeddingMapParams) {
  return useQuery({
    queryKey: ['embeddingMap', params],
    queryFn: () => fetchEmbeddingMap(params),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}
