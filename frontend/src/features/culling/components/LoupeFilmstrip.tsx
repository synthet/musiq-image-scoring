import { clsx } from 'clsx'
import { previewSrc, type CullingStackImage } from '../api/culling'
import { pickStatusOf } from '../utils/pickStatus'
import { PickBadge } from './PickBadge'

interface LoupeFilmstripProps {
  images: CullingStackImage[]
  activeImageId: number | null
  onSelect: (id: number) => void
}

export function LoupeFilmstrip({ images, activeImageId, onSelect }: LoupeFilmstripProps) {
  if (images.length === 0) return null
  return (
    <div className="flex shrink-0 items-center gap-2 overflow-x-auto border-t border-border-muted bg-bg-secondary px-3 py-2">
      {images.map((img, idx) => {
        const pick = pickStatusOf(img)
        const active = img.id === activeImageId
        return (
          <button
            key={img.id}
            type="button"
            onClick={() => onSelect(img.id)}
            className={clsx(
              'group relative h-16 w-20 shrink-0 overflow-hidden rounded border transition-colors',
              active
                ? 'border-accent ring-1 ring-accent/50'
                : 'border-border-muted hover:border-border',
              pick === -1 && 'opacity-60 grayscale',
            )}
            title={img.file_name ?? `Image ${img.id}`}
          >
            <img
              src={previewSrc(img.file_path)}
              alt=""
              loading="lazy"
              className="h-full w-full object-cover"
            />
            <span className="absolute left-1 top-1 rounded bg-bg-primary/80 px-1 text-[9px] tabular-nums text-text-muted">
              {idx + 1}
            </span>
            {pick !== 0 && (
              <span className="absolute right-1 top-1 rounded-full bg-bg-primary/85 p-0.5">
                <PickBadge status={pick} size={11} />
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}
