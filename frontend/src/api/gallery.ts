import { api } from './client'
import type { Image, ImageAuditlogResponse, ImageDetail } from '@/types/api'

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
const HEX_HASH_RE = /^[0-9a-f]{32,128}$/i

// Query params matching the legacy /images endpoint
export interface ImageFilters {
  folder_path?: string
  stack_id?: number
  rating?: string         // comma-separated ratings e.g. "3,4,5"
  label?: string          // comma-separated labels e.g. "Pick,Normal"
  keyword?: string
  /** When true, match keyword exactly instead of substring (tag-cloud clicks). */
  keyword_exact?: boolean
  min_score_general?: number
  min_score_aesthetic?: number
  min_score_technical?: number
  sort_by?: string        // "score" | "score_general" | "date" | "name" | "rating"
  order?: 'asc' | 'desc'
  page?: number
  page_size?: number
  /** phase_code:status e.g. keywords:not_started */
  phase_status?: string
  unscored_only?: boolean
  /** Phase done/skipped but stored data missing (e.g. keywords) */
  data_gap?: string
}

export interface ImageListResponse {
  images: Image[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface ImageUpdateRequest {
  rating?: number | null
  label?: string | null
  keywords?: string
  title?: string
  description?: string
  write_sidecar?: boolean
}

export interface NeighborResponse {
  prev_id: number | null
  next_id: number | null
}

export const galleryApi = {
  list: (filters: ImageFilters = {}) => {
    const q = new URLSearchParams()
    Object.entries(filters).forEach(([k, v]) => {
      if (v != null) q.set(k, String(v))
    })
    return api.get<ImageListResponse>(`/images?${q.toString()}`)
  },
  getNeighbors: (id: number, filters: ImageFilters = {}) => {
    const q = new URLSearchParams()
    Object.entries(filters).forEach(([k, v]) => {
      if (v != null) q.set(k, String(v))
    })
    return api.get<NeighborResponse>(`/images/${id}/neighbors?${q.toString()}`)
  },
  get: (id: number) => api.get<ImageDetail>(`/images/${id}`),
  getAuditlog: (id: number, limit = 50) =>
    api.get<ImageAuditlogResponse>(`/images/${id}/auditlog?limit=${limit}`),
  getByUuid: (uuid: string) =>
    api.get<ImageDetail>(`/images/by-uuid/${encodeURIComponent(uuid.trim())}`),
  getByHash: (hash: string, hashVersion?: number | null) => {
    const q =
      hashVersion == null
        ? ''
        : `?hash_version=${encodeURIComponent(String(hashVersion))}`
    return api.get<ImageDetail>(
      `/images/by-hash/${encodeURIComponent(hash.trim())}${q}`
    )
  },
  getByKey: (key: string): Promise<ImageDetail> => {
    const k = key.trim()
    if (!k) {
      return Promise.reject(new Error('Empty image key'))
    }
    if (/^\d+$/.test(k)) {
      return galleryApi.get(parseInt(k, 10))
    }
    if (UUID_RE.test(k)) {
      return galleryApi.getByUuid(k)
    }
    if (HEX_HASH_RE.test(k)) {
      return galleryApi.getByHash(k)
    }
    return Promise.reject(new Error(`Unrecognized image key: ${k}`))
  },
  update: (id: number, data: ImageUpdateRequest) => api.patch<Image>(`/images/${id}`, data),
  delete: (id: number) => api.delete<void>(`/images/${id}`),
  similar: (id: number, limit = 12) => api.get<Image[]>(`/similar?image_id=${id}&limit=${limit}`),

  /** Cached EXIF row (`image_exif`); empty object if not present. */
  getExif: (id: number) => api.get<Record<string, unknown>>(`/images/${id}/exif`),
  /** Cached XMP row (`image_xmp`); empty object if not present. */
  getXmp: (id: number) => api.get<Record<string, unknown>>(`/images/${id}/xmp`),
}
