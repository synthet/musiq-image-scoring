import { api } from './client'
import type { ScopePreviewResult, FolderNode, ValidationRepairPreview } from '@/types/api'

export const scopeApi = {
  preview: (paths: string[], recursive: boolean) =>
    api.post<ScopePreviewResult>('/scope/preview', { paths, recursive }),
  validationRepairPreview: (scope_paths: string[], stages?: string[]) =>
    api.post<ValidationRepairPreview>('/runs/validation-repair/preview', { scope_paths, stages }),

  tree: () => api.get<FolderNode[]>('/scope/tree'),

  /** Remove subtree from folders cache only when rollup image count is zero (validated server-side). */
  deleteEmptyFolderCache: (path: string) =>
    api.delete<{ success: boolean; message?: string; deleted_folders?: number }>('/folders/cache', {
      path,
    }),

  // Fallback: /folders/tree returns { tree, count }, normalize to FolderNode[]
  foldersTree: () =>
    api
      .get<{ tree?: FolderNode[]; count?: number }>('/folders/tree')
      .then((r) => (Array.isArray(r?.tree) ? r.tree : [])),
}
