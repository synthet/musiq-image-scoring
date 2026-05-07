import { useCallback, useEffect, useMemo, useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { FolderTree, Grid3x3, Maximize2, Keyboard } from 'lucide-react'
import { clsx } from 'clsx'
import { cullingApi, type CullingStackImagesResponse } from '../api/culling'
import { useCullingStore } from '../stores/cullingStore'
import { useCullingKeyboard } from '../hooks/useCullingKeyboard'
import { usePickMutation } from '../hooks/usePickMutation'
import { sortByQualityDesc } from '../utils/qualityRank'
import { pickStatusOf, type PickStatus } from '../utils/pickStatus'
import { SurveyView } from './SurveyView'
import { LoupeView } from './LoupeView'
import { ToolbarHints } from './ToolbarHints'
import { useUiStore } from '@/stores/uiStore'

export function CullingWorkspace() {
  // Scope is owned by the global Sidebar (Scope Navigator). The Culling page
  // only reads it; clicking a folder in the tree drives this view.
  const scopePath = useUiStore((s) => s.selectedScopePath)
  const setSidebarOpen = useUiStore((s) => s.setSidebarOpen)
  const sidebarOpen = useUiStore((s) => s.sidebarOpen)
  const mode = useCullingStore((s) => s.mode)
  const setMode = useCullingStore((s) => s.setMode)
  const activeStackId = useCullingStore((s) => s.activeStackId)
  const setActiveStackId = useCullingStore((s) => s.setActiveStackId)
  const activeImageId = useCullingStore((s) => s.activeImageId)
  const setActiveImageId = useCullingStore((s) => s.setActiveImageId)
  const toggleZoom = useCullingStore((s) => s.toggleZoom)
  const hintsOpen = useCullingStore((s) => s.hintsOpen)
  const setHintsOpen = useCullingStore((s) => s.setHintsOpen)
  const setScopePath = useCullingStore((s) => s.setScopePath)

  // When the global scope changes, reset our local selection so we don't
  // keep showing stacks/images from the previous folder.
  const lastScopeRef = useRef<string | null | undefined>(undefined)
  useEffect(() => {
    if (lastScopeRef.current !== undefined && lastScopeRef.current !== scopePath) {
      setActiveStackId(null)
      setActiveImageId(null)
      setMode('survey')
    }
    lastScopeRef.current = scopePath
    // Keep the cullingStore.scopePath mirror in sync for any sub-components
    // that still observe it (back-compat).
    setScopePath(scopePath ?? null)
  }, [scopePath, setActiveStackId, setActiveImageId, setMode, setScopePath])

  const qc = useQueryClient()
  const pickMutation = usePickMutation()

  const { data: stacksResp } = useQuery({
    queryKey: ['culling', 'stacks', scopePath ?? ''],
    queryFn: () => cullingApi.listStacks({ folder_path: scopePath ?? undefined }),
    enabled: scopePath != null,
  })

  const stacks = useMemo(() => stacksResp?.stacks ?? [], [stacksResp])

  const navigateStack = useCallback(
    (delta: number) => {
      if (stacks.length === 0) return
      const currentIdx = activeStackId == null ? -1 : stacks.findIndex((s) => s.id === activeStackId)
      const nextIdx = currentIdx === -1 ? 0 : (currentIdx + delta + stacks.length) % stacks.length
      setActiveStackId(stacks[nextIdx].id)
    },
    [stacks, activeStackId, setActiveStackId],
  )

  const navigateImage = useCallback(
    (delta: number) => {
      if (mode !== 'loupe' || activeStackId == null) return
      const cached = qc.getQueryData<CullingStackImagesResponse>([
        'culling',
        'stack-images',
        activeStackId,
      ])
      const sorted = cached?.images ? sortByQualityDesc(cached.images) : []
      if (sorted.length === 0) return
      const currentIdx = activeImageId == null ? 0 : sorted.findIndex((i) => i.id === activeImageId)
      const nextIdx = currentIdx === -1 ? 0 : (currentIdx + delta + sorted.length) % sorted.length
      setActiveImageId(sorted[nextIdx].id)
    },
    [mode, activeStackId, activeImageId, qc, setActiveImageId],
  )

  const setPick = useCallback(
    (pick: PickStatus) => {
      if (activeStackId == null) return
      // In Survey mode, picking applies to the cover (top-ranked). In Loupe, it's the active image.
      let targetId = activeImageId
      if (targetId == null) {
        const cached = qc.getQueryData<CullingStackImagesResponse>([
          'culling',
          'stack-images',
          activeStackId,
        ])
        const sorted = cached?.images ? sortByQualityDesc(cached.images) : []
        targetId = sorted[0]?.id ?? null
      }
      if (targetId == null) return
      pickMutation.mutate({ imageId: targetId, stackId: activeStackId, pickStatus: pick })
    },
    [activeStackId, activeImageId, pickMutation, qc],
  )

  const handlers = useMemo(
    () => ({
      onPick: () => setPick(1),
      onReject: () => setPick(-1),
      onUnflag: () => setPick(0),
      onPrevStack: () => navigateStack(-1),
      onNextStack: () => navigateStack(1),
      onPrevImage: () => navigateImage(-1),
      onNextImage: () => navigateImage(1),
      onToggleMode: () => setMode(mode === 'survey' ? 'loupe' : 'survey'),
      onToggleZoom: () => toggleZoom(),
      onToggleHints: () => setHintsOpen(!hintsOpen),
    }),
    [setPick, navigateStack, navigateImage, mode, setMode, toggleZoom, setHintsOpen, hintsOpen],
  )

  useCullingKeyboard(handlers)

  // Counters: how many picks/rejects across visible stack covers (best-effort).
  const pickCounts = useMemo(() => {
    let picks = 0
    let rejects = 0
    for (const s of stacks) {
      const cached = qc.getQueryData<CullingStackImagesResponse>([
        'culling',
        'stack-images',
        s.id,
      ])
      if (!cached) continue
      for (const img of cached.images) {
        const p = pickStatusOf(img)
        if (p === 1) picks += 1
        else if (p === -1) rejects += 1
      }
    }
    return { picks, rejects }
  }, [stacks, qc])

  const scopeLabel = scopePath ? scopePath.split(/[/\\]/).filter(Boolean).pop() ?? scopePath : null

  return (
    <div className="flex h-full min-h-0 flex-col bg-bg-primary">
      <div className="flex shrink-0 items-center gap-4 border-b border-border-muted bg-bg-secondary px-4 py-2">
        <button
          type="button"
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="inline-flex items-center gap-2 rounded px-2 py-1 text-xs text-text-secondary transition-colors hover:bg-bg-elevated hover:text-text-primary"
          title={sidebarOpen ? 'Hide scope navigator' : 'Show scope navigator'}
        >
          <FolderTree size={14} className="text-accent-bright" />
          <span className="text-text-muted">Scope:</span>
          {scopeLabel ? (
            <span className="max-w-[20rem] truncate text-accent-bright" title={scopePath ?? undefined}>
              {scopeLabel}
            </span>
          ) : (
            <span className="text-text-muted">none — pick a folder ←</span>
          )}
        </button>
        <ModeToggle mode={mode} onChange={setMode} />
        <div className="ml-auto flex items-center gap-3 text-xs">
          <span className="inline-flex items-center gap-1 text-success">
            ✓ {pickCounts.picks}
          </span>
          <span className="inline-flex items-center gap-1 text-danger">
            ✕ {pickCounts.rejects}
          </span>
          <button
            type="button"
            onClick={() => setHintsOpen(true)}
            className="inline-flex items-center gap-1 rounded px-2 py-1 text-text-muted transition-colors hover:bg-bg-elevated hover:text-text-primary"
            title="Keyboard shortcuts (?)"
          >
            <Keyboard size={14} />
            Shortcuts
          </button>
        </div>
      </div>
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        {mode === 'survey' || activeStackId == null ? (
          <div className="min-h-0 flex-1 overflow-y-auto">
            <SurveyView scopePath={scopePath} />
          </div>
        ) : (
          <LoupeView stackId={activeStackId} />
        )}
      </div>
      <ToolbarHints open={hintsOpen} onClose={() => setHintsOpen(false)} />
    </div>
  )
}

interface ModeToggleProps {
  mode: 'survey' | 'loupe'
  onChange: (m: 'survey' | 'loupe') => void
}

function ModeToggle({ mode, onChange }: ModeToggleProps) {
  return (
    <div className="inline-flex overflow-hidden rounded border border-border-muted text-xs">
      <ModeButton active={mode === 'survey'} onClick={() => onChange('survey')} icon={<Grid3x3 size={12} />}>
        Survey
      </ModeButton>
      <ModeButton active={mode === 'loupe'} onClick={() => onChange('loupe')} icon={<Maximize2 size={12} />}>
        Loupe
      </ModeButton>
    </div>
  )
}

function ModeButton({
  active,
  onClick,
  icon,
  children,
}: {
  active: boolean
  onClick: () => void
  icon: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        'inline-flex items-center gap-1 px-2 py-1 transition-colors',
        active ? 'bg-bg-elevated text-text-primary' : 'text-text-muted hover:text-text-primary',
      )}
    >
      {icon}
      {children}
    </button>
  )
}
