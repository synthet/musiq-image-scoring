import { useMemo } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { keepPreviousData } from '@tanstack/react-query'
import { ArrowLeft, Layers, Loader2 } from 'lucide-react'
import { galleryApi } from '@/api/gallery'
import { stacksApi } from '@/api/stacks'
import { ImageBrowsePanel } from '@/components/images/ImageBrowsePanel'
import { Button } from '@/components/ui/button'
import { folderPath, imageInspectorPath } from '@/utils/routes'

export function StackPage() {
  const { stackId: stackIdParam } = useParams<{ stackId: string }>()
  const stackId = parseInt(stackIdParam ?? '', 10)
  const navigate = useNavigate()

  const { data: analytics, isLoading: analyticsLoading } = useQuery({
    queryKey: ['stack', stackId, 'analytics'],
    queryFn: () => stacksApi.analytics(stackId),
    enabled: Number.isFinite(stackId) && stackId > 0,
    retry: false,
  })

  const { data: probeImages } = useQuery({
    queryKey: ['stack', stackId, 'probe'],
    queryFn: () => galleryApi.list({ stack_id: stackId, page: 1, page_size: 1 }),
    enabled: Number.isFinite(stackId) && stackId > 0,
    placeholderData: keepPreviousData,
  })

  const folderId = probeImages?.images?.[0]?.folder_id ?? null
  const notFound = analytics?.error === 'stack_not_found' && (probeImages?.total ?? 0) === 0

  const title = useMemo(() => {
    if (analytics?.stack_name) return analytics.stack_name
    return `Stack ${stackId}`
  }, [analytics?.stack_name, stackId])

  const memberCount = analytics?.member_count ?? probeImages?.total ?? 0

  if (!Number.isFinite(stackId) || stackId <= 0) {
    return (
      <div className="p-6">
        <p className="text-sm text-[var(--color-danger)]">Invalid stack id</p>
      </div>
    )
  }

  if (analyticsLoading && !analytics && !probeImages) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 size={20} className="text-[var(--color-accent-bright)] animate-spin" />
      </div>
    )
  }

  if (notFound) {
    return (
      <div className="p-6 space-y-3">
        <p className="text-sm text-[var(--color-danger)]">Stack #{stackId} not found</p>
        <Link to="/images" className="text-xs text-[var(--color-accent-bright)] hover:underline">
          Back to images
        </Link>
      </div>
    )
  }

  const backTo = folderId != null ? folderPath(folderId) : '/images'
  const backLabel = folderId != null ? 'Back to folder' : 'Back to images'

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="shrink-0 border-b border-[var(--color-border-muted)] px-4 py-4 bg-[var(--color-bg-secondary)]">
        <div className="flex items-start gap-3">
          <Button variant="ghost" size="sm" onClick={() => navigate(backTo)} className="shrink-0 mt-0.5">
            <ArrowLeft size={14} />
          </Button>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <Layers size={16} className="text-[var(--color-accent-bright)] shrink-0" />
              <h1 className="text-base font-semibold text-[var(--color-text-primary)] truncate">{title}</h1>
              <span className="text-xs text-[var(--color-text-muted)] font-mono shrink-0">#{stackId}</span>
            </div>
            <p className="text-xs text-[var(--color-text-muted)]">
              {memberCount.toLocaleString()} image{memberCount !== 1 ? 's' : ''}
              {analytics?.best_image_id ? (
                <>
                  {' · best '}
                  <Link
                    to={imageInspectorPath(analytics.best_image_id)}
                    className="text-[var(--color-accent-bright)] hover:underline font-mono"
                  >
                    #{analytics.best_image_id}
                  </Link>
                </>
              ) : null}
            </p>
            {folderId != null && (
              <p className="text-xs mt-1">
                <Link to={folderPath(folderId)} className="text-[var(--color-accent-bright)] hover:underline">
                  Folder #{folderId}
                </Link>
              </p>
            )}
            {analytics?.warnings && analytics.warnings.length > 0 && (
              <p className="text-[10px] text-[var(--color-warning)] mt-1">
                {analytics.warnings.join(' · ')}
              </p>
            )}
          </div>
          <Link to={backTo} className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-accent-bright)] shrink-0">
            {backLabel}
          </Link>
        </div>
      </div>

      <div className="flex-1 min-h-0">
        <ImageBrowsePanel
          filters={{ stack_id: stackId }}
          title="Stack images"
          subtitle={`Stack #${stackId}`}
          queryKeyPrefix={`stack-${stackId}`}
          useGlobalSort={false}
          emptyMessage="No images in this stack."
        />
      </div>
    </div>
  )
}
