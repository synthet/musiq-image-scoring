import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FolderTree, ChevronDown } from 'lucide-react'
import { cullingApi } from '../api/culling'
import { useCullingStore } from '../stores/cullingStore'
import type { FolderNode } from '@/types/api'

interface FlatFolder {
  path: string
  depth: number
  imageCount: number
  label: string
}

function flattenTree(nodes: FolderNode[], depth = 0, acc: FlatFolder[] = []): FlatFolder[] {
  for (const n of nodes) {
    acc.push({
      path: n.path,
      depth,
      imageCount: n.image_count ?? 0,
      label: n.name || n.path,
    })
    if (n.children && n.children.length > 0) flattenTree(n.children, depth + 1, acc)
  }
  return acc
}

export function FolderScopeSelector() {
  const scopePath = useCullingStore((s) => s.scopePath)
  const setScopePath = useCullingStore((s) => s.setScopePath)

  const { data: tree, isLoading } = useQuery({
    queryKey: ['culling', 'folder-tree'],
    queryFn: () => cullingApi.foldersTree(),
    staleTime: 30_000,
  })

  const flat = useMemo(() => (tree ? flattenTree(tree) : []), [tree])

  return (
    <label className="flex items-center gap-2 text-xs text-text-secondary">
      <FolderTree size={14} className="text-accent-bright" />
      <span className="text-text-muted">Scope</span>
      <div className="relative">
        <select
          value={scopePath ?? ''}
          onChange={(e) => setScopePath(e.target.value || null)}
          disabled={isLoading || flat.length === 0}
          className="appearance-none rounded border border-border-muted bg-bg-tertiary py-1 pl-2 pr-7 text-xs text-text-primary outline-none transition-colors hover:border-border focus:border-accent disabled:cursor-not-allowed disabled:opacity-60"
        >
          <option value="">{isLoading ? 'Loading folders…' : flat.length === 0 ? 'No folders indexed' : 'Select a folder…'}</option>
          {flat.map((f) => (
            <option key={f.path} value={f.path}>
              {`${'  '.repeat(f.depth)}${f.label}${f.imageCount ? ` (${f.imageCount})` : ''}`}
            </option>
          ))}
        </select>
        <ChevronDown
          size={12}
          className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-text-muted"
        />
      </div>
    </label>
  )
}
