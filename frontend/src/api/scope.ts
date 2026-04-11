import { api } from './client'
import type { ScopePreviewResult, FolderNode, ValidationRepairPreview } from '@/types/api'

export const scopeApi = {
  preview: (paths: string[], recursive: boolean) =>
    api.post<ScopePreviewResult>('/scope/preview', { paths, recursive }),
  validationRepairPreview: (scope_paths: string[], stages?: string[]) =>
    api.post<ValidationRepairPreview>('/runs/validation-repair/preview', { scope_paths, stages }),

  tree: () => api.get<FolderNode[]>('/scope/tree'),

  // Fallback: /folders/tree returns { tree, count }, normalize to FolderNode[]
  foldersTree: () =>
    api
      .get<{ tree?: FolderNode[]; count?: number }>('/folders/tree')
      .then((r) => (Array.isArray(r?.tree) ? r.tree : [])),
}
