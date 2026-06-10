import { api } from './client'

export interface KeywordCloudEntry {
  keyword_norm: string
  keyword_display: string | null
  count: number
}

export interface KeywordCloudResponse {
  keywords: KeywordCloudEntry[]
  kind: string
}

export type KeywordCloudKind = 'species' | 'general'

export const keywordsApi = {
  cloud: (
    kind: KeywordCloudKind,
    opts: { limit?: number; folderPath?: string } = {}
  ) => {
    const q = new URLSearchParams({ kind })
    if (opts.limit != null) q.set('limit', String(opts.limit))
    if (opts.folderPath) q.set('folder_path', opts.folderPath)
    return api.get<KeywordCloudResponse>(`/keywords/cloud?${q.toString()}`)
  },
}
