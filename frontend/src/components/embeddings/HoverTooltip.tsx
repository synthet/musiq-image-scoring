import type { EmbeddingPoint } from '@/types/api'

export interface HoverTooltipProps {
  point: EmbeddingPoint
  x: number
  y: number
  containerWidth: number
  containerHeight: number
}

function thumbSrc(p: EmbeddingPoint): string | null {
  const path = p.thumbnail_path || p.file_path
  if (!path) return null
  return `/source-image?path=${encodeURIComponent(path)}&thumb=1`
}

export function HoverTooltip({ point, x, y, containerWidth, containerHeight }: HoverTooltipProps) {
  const W = 168
  const H = 200
  const pad = 8
  const left = x + pad + W > containerWidth ? Math.max(pad, x - W - pad) : x + pad
  const top = y + pad + H > containerHeight ? Math.max(pad, y - H - pad) : y + pad
  const src = thumbSrc(point)

  return (
    <div
      className="pointer-events-none absolute z-20 rounded border border-[#474747] bg-[#252526] shadow-xl"
      style={{ left, top, width: W }}
    >
      <div className="h-32 w-full bg-[#141414] flex items-center justify-center overflow-hidden">
        {src ? (
          <img
            src={src}
            alt=""
            className="max-h-full max-w-full object-contain"
            draggable={false}
          />
        ) : (
          <span className="text-xs text-[#6d6d6d]">no thumb</span>
        )}
      </div>
      <div className="px-2 py-1.5 text-[10px] text-[#cccccc] space-y-0.5">
        <div className="font-mono text-[#4fc1ff]">id {point.image_id}</div>
        <div className="text-[#9d9d9d] flex items-center gap-2">
          {point.label && <span>{point.label}</span>}
          {point.rating != null && <span>★ {point.rating}</span>}
          {point.score_general != null && (
            <span className="ml-auto font-mono">
              {point.score_general.toFixed(2)}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}
