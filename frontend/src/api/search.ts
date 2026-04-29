import { api } from './client'

export interface TextSearchResult {
  image_id: number
  file_path: string
  similarity: number
}

export interface TextSearchResponse {
  query: string
  results: TextSearchResult[]
  count: number
  embedding_space: string
}

export interface TextSearchParams {
  query: string
  limit?: number
  folder_path?: string
  min_similarity?: number
}

export const searchApi = {
  textSearch: (params: TextSearchParams) => {
    const q = new URLSearchParams()
    q.set('query', params.query)
    if (params.limit != null) q.set('limit', String(params.limit))
    if (params.folder_path) q.set('folder_path', params.folder_path)
    if (params.min_similarity != null) q.set('min_similarity', String(params.min_similarity))
    return api.get<TextSearchResponse>(`/similarity/text-search?${q.toString()}`)
  },
}
