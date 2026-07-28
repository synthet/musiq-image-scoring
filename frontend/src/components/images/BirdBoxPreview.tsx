import { useState } from 'react'
import type { BirdBboxValue } from '@/types/api'
import { isBirdBoundingBox } from '@/types/api'
import { birdBboxBorderCss } from './birdBboxStyle'

/**
 * Preview image with an optional bird detection overlay.
 *
 * The box is positioned as a fraction of the detector's `img_w`/`img_h`, which is the oriented
 * preview size the detector saw (e.g. 3936x2624 for a NEF) rather than whatever size this page
 * renders. Fractions keep the two independent, so no resize handling is needed.
 * Border color/opacity track detection confidence (Color Label red→yellow→green ramp).
 */
export function BirdBoxPreview({
  src,
  alt,
  bbox,
}: {
  src: string
  alt: string
  bbox?: BirdBboxValue | null
}) {
  const [showBbox, setShowBbox] = useState(false)
  const drawable =
    isBirdBoundingBox(bbox) && bbox.img_w > 0 && bbox.img_h > 0 ? bbox : null

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative inline-flex">
        <img src={src} alt={alt} className="max-w-full max-h-[min(50vh,480px)] object-contain" />
        {showBbox && drawable && (
          <div
            data-testid="bird-bbox-overlay"
            className="absolute pointer-events-none"
            style={{
              left: `${(drawable.x1 / drawable.img_w) * 100}%`,
              top: `${(drawable.y1 / drawable.img_h) * 100}%`,
              width: `${((drawable.x2 - drawable.x1) / drawable.img_w) * 100}%`,
              height: `${((drawable.y2 - drawable.y1) / drawable.img_h) * 100}%`,
              border: `2px solid ${birdBboxBorderCss(drawable.conf)}`,
            }}
          />
        )}
      </div>
      <label className="flex items-center gap-1 text-xs text-[var(--color-text-secondary)]">
        <input
          type="checkbox"
          checked={showBbox}
          disabled={!drawable}
          onChange={(e) => setShowBbox(e.target.checked)}
        />
        <span>Bounding box</span>
        {!drawable && <span className="text-[var(--color-text-muted)]">(no detection)</span>}
      </label>
    </div>
  )
}
