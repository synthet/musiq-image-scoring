import { api } from './client'
import type { ScopePreviewResult, FolderNode, ValidationRepairPreview } from '@/types/api'

export const scopeApi = {
  preview: (paths: string[], recursive: boolean) =>
    api.post<ScopePreviewResult>('/scope/preview', { paths, recursive }),
  validationRepairPreview: (
    scope_paths: string[],
    stages?: string[],
    options?: { alignAutoDrive?: boolean; includeStaleExecutor?: boolean },
  ) =>
    api.post<ValidationRepairPreview>('/runs/validation-repair/preview', {
      scope_paths,
      stages,
      ...(options?.alignAutoDrive ? { align_auto_drive: true } : {}),
      ...(options?.includeStaleExecutor !== undefined
        ? { include_stale_executor: options.includeStaleExecutor }
        : {}),
    }),

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
