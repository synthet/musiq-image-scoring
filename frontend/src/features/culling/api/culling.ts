import { api } from '@/api/client'
import type { Image, FolderNode } from '@/types/api'

export interface CullingStack {
  id: number
  name: string | null
  image_count: number
  sort_val: number | null
  cover_path: string | null
}

export interface CullingStacksResponse {
  stacks: CullingStack[]
  count: number
}

export interface CullingStackImage extends Image {
  pick_status?: number | null
  /** Tie-breakers from image_exif (added by get_images_in_stack JOIN). */
  exif_iso?: number | null
  exif_exposure_time?: string | null
  exif_image_width?: number | null
  exif_image_height?: number | null
}

export interface CullingStackImagesResponse {
  images: CullingStackImage[]
  count: number
  stack_id: number
}

export interface ImagePickPatch {
  pick_status: -1 | 0 | 1
  write_sidecar?: boolean
}

export const cullingApi = {
  /** Folder tree for the scope dropdown. Falls back to /folders/tree when /scope/tree is empty. */
  foldersTree: () =>
    api
      .get<{ tree?: FolderNode[]; count?: number }>(`/folders/tree`)
      .then((r) => (Array.isArray(r?.tree) ? r.tree : [])),

  listStacks: (params: { folder_path?: string; sort_by?: string; order?: 'asc' | 'desc' } = {}) => {
    const q = new URLSearchParams()
    if (params.folder_path) q.set('folder_path', params.folder_path)
    if (params.sort_by) q.set('sort_by', params.sort_by)
    if (params.order) q.set('order', params.order)
    const qs = q.toString()
    return api.get<CullingStacksResponse>(`/stacks${qs ? `?${qs}` : ''}`)
  },

  stackImages: (stackId: number) =>
    api.get<CullingStackImagesResponse>(`/stacks/${stackId}/images`),

  patchPick: (imageId: number, body: ImagePickPatch) =>
    api.patch<{ success: boolean; data: { pick_status: number; rating: number; label: string } }>(
      `/images/${imageId}`,
      { write_sidecar: true, ...body },
    ),
}

/** Build a thumbnail URL for any image record. */
export function previewSrc(filePath: string, thumb = true): string {
  return `/source-image?path=${encodeURIComponent(filePath)}${thumb ? '&thumb=1' : ''}`
}
