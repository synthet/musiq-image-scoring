import { useEffect, useMemo, useRef } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, FolderOpen, Loader2, MapPin, Play } from 'lucide-react'
import { foldersApi, folderPhasesToBucketPhases } from '@/api/folders'
import { cullingApi } from '@/features/culling/api/culling'
import { ImageBrowsePanel } from '@/components/images/ImageBrowsePanel'
import { PipelinePhaseIconsRow } from '@/components/phases/PipelinePhaseIconsRow'
import { Button } from '@/components/ui/button'
import { useUiStore } from '@/stores/uiStore'
import { stackPath } from '@/utils/routes'

function splitPath(path: string) {
  const parts = path.split(/[\\/]/).filter(Boolean)
  return {
    leaf: parts[parts.length - 1] || path,
    parent: parts.slice(0, Math.max(0, parts.length - 1)).join('/'),
  }
}

export function FolderPage() {
  const { folderId: folderIdParam } = useParams<{ folderId: string }>()
  const folderId = parseInt(folderIdParam ?? '', 10)
  const navigate = useNavigate()
  const browseRef = useRef<HTMLDivElement>(null)
  const setSelectedScopePath = useUiStore((s) => s.setSelectedScopePath)
  const openNewRun = useUiStore((s) => s.openNewRun)

  const { data: folder, isLoading, isError } = useQuery({
    queryKey: ['folder', folderId],
    queryFn: () => foldersApi.get(folderId),
    enabled: Number.isFinite(folderId) && folderId > 0,
  })

  const { data: phaseData } = useQuery({
    queryKey: ['folder', folderId, 'phases', folder?.path],
    queryFn: () => foldersApi.phaseStatus(folder!.path),
    enabled: Boolean(folder?.path),
  })

  const { data: stacksResp } = useQuery({
    queryKey: ['folder', folderId, 'stacks', folder?.path],
    queryFn: () => cullingApi.listStacks({ folder_path: folder!.path }),
    enabled: Boolean(folder?.path),
  })

  useEffect(() => {
    if (folder?.path) {
      setSelectedScopePath(folder.path)
    }
  }, [folder?.path, setSelectedScopePath])

  const pathParts = useMemo(
    () => (folder?.path ? splitPath(folder.path) : { leaf: '', parent: '' }),
    [folder?.path],
  )

  const bucketPhases = useMemo(
    () => folderPhasesToBucketPhases(phaseData?.phases ?? []),
    [phaseData?.phases],
  )

  if (!Number.isFinite(folderId) || folderId <= 0) {
    return (
      <div className="p-6">
        <p className="text-sm text-[var(--color-danger)]">Invalid folder id</p>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 size={20} className="text-[var(--color-accent-bright)] animate-spin" />
      </div>
    )
  }

  if (isError || !folder) {
    return (
      <div className="p-6 space-y-3">
        <p className="text-sm text-[var(--color-danger)]">Folder #{folderId} not found</p>
        <Link to="/images" className="text-xs text-[var(--color-accent-bright)] hover:underline">
          Back to images
        </Link>
      </div>
    )
  }

  const stacks = stacksResp?.stacks ?? []

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="shrink-0 border-b border-[var(--color-border-muted)] px-4 py-4 space-y-3 bg-[var(--color-bg-secondary)]">
        <div className="flex items-start gap-3">
          <Button variant="ghost" size="sm" onClick={() => navigate('/images')} className="shrink-0 mt-0.5">
            <ArrowLeft size={14} />
          </Button>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <FolderOpen size={16} className="text-[var(--color-accent-bright)] shrink-0" />
              <h1 className="text-base font-semibold text-[var(--color-text-primary)] truncate">
                {pathParts.leaf}
              </h1>
              <span className="text-xs text-[var(--color-text-muted)] font-mono shrink-0">#{folder.id}</span>
            </div>
            <p className="text-xs font-mono text-[var(--color-text-secondary)] truncate" title={folder.path}>
              {folder.path}
            </p>
            <p className="text-xs text-[var(--color-text-muted)] mt-1">
              {folder.image_count.toLocaleString()} image{folder.image_count !== 1 ? 's' : ''}
              {folder.is_fully_scored ? ' · fully scored' : ''}
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Button
              size="sm"
              variant="secondary"
              onClick={() => browseRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
            >
              Browse
            </Button>
            <Button size="sm" variant="secondary" onClick={() => navigate('/map')}>
              <MapPin size={14} />
              Map
            </Button>
            <Button size="sm" variant="primary" onClick={() => openNewRun(folder.path)}>
              <Play size={14} />
              New Run
            </Button>
          </div>
        </div>

        {bucketPhases.length > 0 && (
          <div className="pl-9">
            <PipelinePhaseIconsRow bucketPhases={bucketPhases} showProgressBars />
          </div>
        )}

        {stacks.length > 0 && (
          <div className="pl-9">
            <div className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-text-muted)] mb-2">
              Stacks ({stacks.length})
            </div>
            <div className="flex flex-wrap gap-2">
              {stacks.slice(0, 24).map((stack) => (
                <Link
                  key={stack.id}
                  to={stackPath(stack.id)}
                  className="text-xs px-2 py-1 rounded border border-[var(--color-border-muted)] bg-[var(--color-bg-primary)] text-[var(--color-text-secondary)] hover:text-[var(--color-accent-bright)] hover:border-[var(--color-accent)] transition-colors"
                >
                  {stack.name ?? `Stack ${stack.id}`}
                  <span className="ml-1 text-[var(--color-text-muted)]">({stack.image_count})</span>
                </Link>
              ))}
              {stacks.length > 24 && (
                <span className="text-xs text-[var(--color-text-muted)] self-center">
                  +{stacks.length - 24} more
                </span>
              )}
            </div>
          </div>
        )}
      </div>

      <div ref={browseRef} className="flex-1 min-h-0">
        <ImageBrowsePanel
          filters={{ folder_path: folder.path }}
          title="Images in folder"
          subtitle={folder.path}
          queryKeyPrefix={`folder-${folder.id}`}
        />
      </div>
    </div>
  )
}
