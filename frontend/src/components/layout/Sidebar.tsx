import { useState, useEffect, useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useLocation, useNavigate } from 'react-router-dom'
import { clsx } from 'clsx'
import { ChevronRight, ChevronDown, Folder, FolderOpen, Plus } from 'lucide-react'
import { scopeApi } from '@/api/scope'
import { useUiStore } from '@/stores/uiStore'
import { useWsStore } from '@/stores/wsStore'
import { Button } from '@/components/ui/button'
import { normalizeTreePath, pathTargetsRevealFolder } from '@/utils/treePaths'
import type { FolderNode } from '@/types/api'

const STATUS_DOT: Record<string, string> = {
  done: 'bg-[#89d185]',
  partial: 'bg-[#cca700]',
  failed: 'bg-[#f44747]',
  running: 'bg-[#4fc1ff] animate-pulse',
}

export function Sidebar() {
  const qc = useQueryClient()
  const location = useLocation()
  const navigate = useNavigate()
  const { openNewRun, setSelectedScopePath, selectedScopePath, pendingTreeRevealPaths, setPendingTreeRevealPaths } =
    useUiStore()
  const runsVersion = useWsStore((s) => s.runsVersion)

  const isRunsMode = location.pathname.startsWith('/runs')

  const { data: tree, isLoading } = useQuery({
    queryKey: ['folders-tree'],
    queryFn: () =>
      scopeApi.tree().catch(() => scopeApi.foldersTree()),
    refetchInterval: 30000,
  })

  const prevRunsVersion = useRef<number | null>(null)
  useEffect(() => {
    if (prevRunsVersion.current === runsVersion) return
    prevRunsVersion.current = runsVersion
    if (runsVersion > 0) qc.invalidateQueries({ queryKey: ['folders-tree'] })
  }, [runsVersion, qc])

  useEffect(() => {
    if (!pendingTreeRevealPaths?.length || !Array.isArray(tree) || tree.length === 0) return
    const primary = pendingTreeRevealPaths[0]
    const key = encodeURIComponent(normalizeTreePath(primary))
    const scrollT = window.setTimeout(() => {
      const el = document.querySelector(`[data-folder-key="${CSS.escape(key)}"]`)
      el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    }, 150)
    const clear = window.setTimeout(() => setPendingTreeRevealPaths(null), 1200)
    return () => {
      clearTimeout(scrollT)
      clearTimeout(clear)
    }
  }, [pendingTreeRevealPaths, tree, setPendingTreeRevealPaths])

  return (
    <aside className="w-56 shrink-0 border-r border-[#3c3c3c] bg-[#252526] flex flex-col overflow-hidden">
      {isRunsMode && (
        <div className="p-3 border-b border-[#3c3c3c] shrink-0">
          <Button
            variant="primary"
            size="sm"
            className="w-full"
            onClick={() => openNewRun(selectedScopePath ?? undefined)}
          >
            <Plus size={12} />
            New Run
          </Button>
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-2">
        <div className="text-[10px] font-semibold uppercase tracking-wider text-[#6d6d6d] px-1 mb-2">
          Scope Navigator
        </div>
        {isLoading && (
          <div className="text-xs text-[#6d6d6d] px-2">Loading folders…</div>
        )}
        {Array.isArray(tree) && tree.map((node) => (
          <FolderTreeNode
            key={node.path}
            node={node}
            depth={0}
            selected={selectedScopePath}
            onSelect={setSelectedScopePath}
            onNewRun={openNewRun}
            revealPaths={pendingTreeRevealPaths}
            isRunsMode={isRunsMode}
            navigate={navigate}
          />
        ))}
        {!isLoading && (!Array.isArray(tree) || tree.length === 0) && (
          <div className="text-xs text-[#6d6d6d] px-2">No indexed folders yet</div>
        )}
      </div>
    </aside>
  )
}

interface FolderTreeNodeProps {
  node: FolderNode
  depth: number
  selected: string | null
  onSelect: (path: string) => void
  onNewRun: (path: string) => void
  revealPaths: string[] | null
  isRunsMode: boolean
  navigate: (path: string) => void
}

function FolderTreeNode({
  node,
  depth,
  selected,
  onSelect,
  onNewRun,
  revealPaths,
  isRunsMode,
  navigate,
}: FolderTreeNodeProps) {
  const hasChildren = node.children && node.children.length > 0
  const isSelected = selected === node.path
  const folderKey = encodeURIComponent(normalizeTreePath(node.path))

  const [expanded, setExpanded] = useState(() => {
    if (depth === 0) return true
    return pathTargetsRevealFolder(node.path, revealPaths)
  })

  useEffect(() => {
    if (hasChildren && pathTargetsRevealFolder(node.path, revealPaths)) {
      setExpanded(true)
    }
  }, [hasChildren, node.path, revealPaths])

  const dominantStatus = getDominantStatus(node.phase_statuses)

  const handleDoubleClick = () => {
    if (isRunsMode) {
      onNewRun(node.path)
    } else {
      onSelect(node.path)
      navigate('/images')
    }
  }

  const title = isRunsMode
    ? `${node.path}\nDouble-click to start new run`
    : `${node.path}\nDouble-click to view images`

  return (
    <div>
      <div
        data-folder-key={folderKey}
        className={clsx(
          'group flex items-center gap-1 rounded px-1 py-0.5 cursor-pointer text-xs',
          'hover:bg-[#3c3c3c] transition-colors',
          isSelected && 'bg-[#2d2d30] text-[#4fc1ff]',
          !isSelected && 'text-[#9d9d9d]',
        )}
        style={{ paddingLeft: `${4 + depth * 12}px` }}
        onClick={() => {
          onSelect(node.path)
          if (hasChildren) setExpanded((e) => !e)
        }}
        onDoubleClick={handleDoubleClick}
        title={title}
      >
        {hasChildren ? (
          <span className="text-[#6d6d6d]">
            {expanded ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
          </span>
        ) : (
          <span className="w-[10px]" />
        )}

        <span className="text-[#6d6d6d]">
          {expanded ? <FolderOpen size={11} /> : <Folder size={11} />}
        </span>

        <span className="flex-1 truncate">{node.name}</span>

        {dominantStatus && (
          <span
            className={clsx('w-1.5 h-1.5 rounded-full shrink-0', STATUS_DOT[dominantStatus])}
            title={dominantStatus}
          />
        )}
      </div>

      {expanded && hasChildren && (
        <div>
          {node.children.map((child) => (
            <FolderTreeNode
              key={child.path}
              node={child}
              depth={depth + 1}
              selected={selected}
              onSelect={onSelect}
              onNewRun={onNewRun}
              revealPaths={revealPaths}
              isRunsMode={isRunsMode}
              navigate={navigate}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function getDominantStatus(statuses?: Record<string, string>): string | null {
  if (!statuses) return null
  const vals = Object.values(statuses) as string[]
  if (vals.includes('running')) return 'running'
  if (vals.includes('failed')) return 'failed'
  if (vals.some((v) => v === 'partial')) return 'partial'
  if (vals.every((v) => v === 'done')) return 'done'
  return null
}
