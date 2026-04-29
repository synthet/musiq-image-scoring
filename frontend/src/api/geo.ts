import { api } from './client'

export interface GeoImage {
  image_id: number
  file_path: string
  latitude: number
  longitude: number
  date_taken: string | null
  label: string | null
  rating: number | null
  camera: string
  score_general: number | null
}

export interface GeoImagesResponse {
  images: GeoImage[]
  count: number
  bounds: { sw: [number, number]; ne: [number, number] } | null
}

export interface GeoImagesParams {
  folder_path?: string
  keyword?: string
  min_score?: number
  label?: string
  rating?: number
  limit?: number
}

export const geoApi = {
  getImages: (params: GeoImagesParams = {}) => {
    const q = new URLSearchParams()
    if (params.folder_path) q.set('folder_path', params.folder_path)
    if (params.keyword) q.set('keyword', params.keyword)
    if (params.min_score != null) q.set('min_score', String(params.min_score))
    if (params.label) q.set('label', params.label)
    if (params.rating != null) q.set('rating', String(params.rating))
    if (params.limit != null) q.set('limit', String(params.limit))
    const qs = q.toString()
    return api.get<GeoImagesResponse>(`/geo/images${qs ? `?${qs}` : ''}`)
  },
}
