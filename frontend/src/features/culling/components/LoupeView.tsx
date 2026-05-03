import { Fragment, useEffect, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Loader2, ImageOff } from 'lucide-react'
import { clsx } from 'clsx'
import { cullingApi, previewSrc, type CullingStackImage } from '../api/culling'
import { useCullingStore } from '../stores/cullingStore'
import { sortByQualityDesc } from '../utils/qualityRank'
import { pickStatusOf } from '../utils/pickStatus'
import { LoupeFilmstrip } from './LoupeFilmstrip'
import { MetricsBreakdown } from './MetricsBreakdown'
import { PickBadge } from './PickBadge'

interface LoupeViewProps {
  stackId: number
}

const stackImagesKey = (stackId: number) => ['culling', 'stack-images', stackId] as const

export function LoupeView({ stackId }: LoupeViewProps) {
  const activeImageId = useCullingStore((s) => s.activeImageId)
  const setActiveImageId = useCullingStore((s) => s.setActiveImageId)
  const zoom100 = useCullingStore((s) => s.zoom100)

  const { data, isLoading, isError, error } = useQuery({
    queryKey: stackImagesKey(stackId),
    queryFn: () => cullingApi.stackImages(stackId),
  })

  const images = useMemo<CullingStackImage[]>(
    () => (data?.images ? sortByQualityDesc(data.images) : []),
    [data],
  )

  // Auto-select the top-ranked keeper when the stack changes / loads.
  useEffect(() => {
    if (images.length === 0) return
    if (activeImageId == null || !images.some((i) => i.id === activeImageId)) {
      setActiveImageId(images[0].id)
    }
  }, [images, activeImageId, setActiveImageId])

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center text-text-muted">
        <Loader2 size={20} className="animate-spin" />
      </div>
    )
  }

  if (isError) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-danger">
        <ImageOff size={24} />
        {error instanceof Error ? error.message : 'Failed to load stack images.'}
      </div>
    )
  }

  if (images.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-text-muted">
        No images in this stack.
      </div>
    )
  }

  const active = images.find((i) => i.id === activeImageId) ?? images[0]
  const pick = pickStatusOf(active)
  const idx = images.findIndex((i) => i.id === active.id)

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex min-h-0 flex-1 gap-3 overflow-hidden p-3">
        <div
          className={clsx(
            'relative flex flex-1 items-center justify-center overflow-hidden rounded border border-border-muted bg-bg-primary',
            pick === 1 && 'ring-2 ring-success/60',
            pick === -1 && 'ring-1 ring-danger/40',
          )}
        >
          <img
            key={active.id}
            src={previewSrc(active.file_path, !zoom100)}
            alt={active.file_name ?? ''}
            className={clsx(
              'block max-h-full max-w-full',
              zoom100 ? 'object-none cursor-zoom-out' : 'object-contain cursor-zoom-in',
              pick === -1 && 'opacity-70 grayscale',
            )}
          />
          <div className="absolute left-2 top-2 flex items-center gap-2 rounded bg-bg-primary/80 px-2 py-1 text-[11px] backdrop-blur">
            <PickBadge status={pick} size={14} />
            <span className="text-text-secondary">
              {idx + 1} of {images.length}
            </span>
            <span className="truncate text-text-muted">{active.file_name}</span>
          </div>
          {zoom100 && (
            <span className="absolute right-2 top-2 rounded bg-accent/20 px-2 py-0.5 text-[10px] font-medium text-accent-bright">
              100%
            </span>
          )}
        </div>
        <aside className="hidden w-72 shrink-0 flex-col gap-3 overflow-y-auto md:flex">
          <MetricsBreakdown image={active} />
          <ExifFacts image={active} />
        </aside>
      </div>
      <LoupeFilmstrip images={images} activeImageId={active.id} onSelect={setActiveImageId} />
    </div>
  )
}

function ExifFacts({ image }: { image: CullingStackImage }) {
  const w = image.exif_image_width
  const h = image.exif_image_height
  const dims = w && h ? `${w} × ${h}` : null
  const facts = [
    { label: 'ISO', value: image.exif_iso != null ? String(image.exif_iso) : null },
    { label: 'Exposure', value: image.exif_exposure_time ?? null },
    { label: 'Resolution', value: dims },
  ].filter((f) => f.value)

  if (facts.length === 0) return null

  return (
    <div className="rounded border border-border-muted bg-bg-secondary p-3 text-xs">
      <div className="mb-2 text-[11px] font-medium uppercase tracking-wide text-text-muted">
        Capture
      </div>
      <dl className="grid grid-cols-[5rem_1fr] gap-y-1">
        {facts.map((f) => (
          <Fragment key={f.label}>
            <dt className="text-text-muted">{f.label}</dt>
            <dd className="tabular-nums text-text-secondary">{f.value}</dd>
          </Fragment>
        ))}
      </dl>
    </div>
  )
}
