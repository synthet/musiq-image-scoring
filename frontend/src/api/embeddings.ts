import { api } from './client'
import type {
  EmbeddingMapResponse,
  EmbeddingSpacesResponse,
  SimilarImagesResponse,
} from '@/types/api'

interface ApiEnvelope<T> {
  success: boolean
  message: string
  data: T
}

export interface EmbeddingMapParams {
  folder_path?: string | null
  method?: 'umap' | 'tsne'
  refresh?: boolean
  sample_limit?: number
  n_neighbors?: number
  min_dist?: number
  space_code?: string
  pca_dim?: number
}

function buildQuery(params: Record<string, unknown>): string {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v == null || v === '') continue
    q.set(k, String(v))
  }
  const s = q.toString()
  return s ? `?${s}` : ''
}

export const embeddingsApi = {
  spaces: () =>
    api
      .get<ApiEnvelope<EmbeddingSpacesResponse>>('/embedding_spaces')
      .then((r) => r.data),

  map: (params: EmbeddingMapParams = {}) =>
    api
      .get<ApiEnvelope<EmbeddingMapResponse>>(
        `/embedding_map${buildQuery(params as unknown as Record<string, unknown>)}`,
      )
      .then((r) => r.data),

  similar: (
    imageId: number,
    opts: {
      limit?: number
      folder_path?: string | null
      min_similarity?: number
      embedding_space?: string
    } = {},
  ) =>
    api.get<SimilarImagesResponse>(
      `/images/${imageId}/similar${buildQuery(opts as unknown as Record<string, unknown>)}`,
    ),
}
