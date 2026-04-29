import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { EmbeddingPoint } from '@/types/api'

export type ColorBy = 'label' | 'rating' | 'score_general'

export interface ScatterCanvasProps {
  points: EmbeddingPoint[]
  colorBy: ColorBy
  selectedId: number | null
  focusId: number | null
  highlightIds?: Set<number>
  onHover: (data: { point: EmbeddingPoint; screenX: number; screenY: number } | null) => void
  onSelect: (point: EmbeddingPoint) => void
}

interface ViewTransform {
  k: number
  tx: number
  ty: number
}

const DEFAULT_VIEW: ViewTransform = { k: 1, tx: 0, ty: 0 }

function colorForPoint(p: EmbeddingPoint, mode: ColorBy): string {
  if (mode === 'label') {
    const l = (p.label ?? '').toLowerCase()
    if (l === 'pick' || l === 'kept' || l === 'keep') return '#6a9955'
    if (l === 'reject' || l === 'discard' || l === 'discarded') return '#f44747'
    if (l === 'flag' || l === 'flagged') return '#d7ba7d'
    if (l === 'normal') return '#4fc1ff'
    return '#808080'
  }
  if (mode === 'rating') {
    const r = p.rating ?? 0
    const palette = ['#3a3a3a', '#5a5a5a', '#a89060', '#d7ba7d', '#dcdcaa', '#6a9955']
    return palette[Math.max(0, Math.min(5, Math.round(r)))]
  }
  // score_general — perceptual-ish ramp from dark blue → teal → yellow.
  const s = Math.max(0, Math.min(1, p.score_general ?? 0))
  const stops = [
    [68, 1, 84],
    [59, 82, 139],
    [33, 144, 141],
    [94, 201, 98],
    [253, 231, 37],
  ] as const
  const idx = s * (stops.length - 1)
  const i = Math.floor(idx)
  const t = idx - i
  const a = stops[i]
  const b = stops[Math.min(stops.length - 1, i + 1)]
  const r = Math.round(a[0] + (b[0] - a[0]) * t)
  const g = Math.round(a[1] + (b[1] - a[1]) * t)
  const bl = Math.round(a[2] + (b[2] - a[2]) * t)
  return `rgb(${r},${g},${bl})`
}

export function ScatterCanvas({
  points,
  colorBy,
  selectedId,
  focusId,
  highlightIds,
  onHover,
  onSelect,
}: ScatterCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const viewRef = useRef<ViewTransform>(DEFAULT_VIEW)
  const [size, setSize] = useState({ w: 0, h: 0 })
  const [, setTick] = useState(0)
  const dragRef = useRef<{ x: number; y: number; tx: number; ty: number; moved: boolean } | null>(null)
  const lastFocusRef = useRef<number | null>(null)

  // Pre-compute color for each point so the draw loop is just blitting.
  const colors = useMemo(() => points.map((p) => colorForPoint(p, colorBy)), [points, colorBy])
  const idIndex = useMemo(() => {
    const m = new Map<number, number>()
    points.forEach((p, i) => m.set(p.image_id, i))
    return m
  }, [points])

  // Resize observer
  useLayoutEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver((entries) => {
      const cr = entries[0].contentRect
      setSize({ w: Math.max(1, Math.floor(cr.width)), h: Math.max(1, Math.floor(cr.height)) })
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // Reset view to fit when point set changes substantially.
  useEffect(() => {
    viewRef.current = { ...DEFAULT_VIEW }
    setTick((n) => n + 1)
  }, [points])

  // Center on focusId once when it changes and points include it.
  useEffect(() => {
    if (focusId == null || focusId === lastFocusRef.current) return
    const idx = idIndex.get(focusId)
    if (idx == null) return
    if (size.w === 0 || size.h === 0) return
    const p = points[idx]
    const k = 4
    // map data [0,1] → plot pixel coords with 8px margin
    const margin = 8
    const px = margin + p.x * (size.w - 2 * margin)
    const py = margin + (1 - p.y) * (size.h - 2 * margin)
    viewRef.current = {
      k,
      tx: size.w / 2 - px * k,
      ty: size.h / 2 - py * k,
    }
    lastFocusRef.current = focusId
    setTick((n) => n + 1)
  }, [focusId, idIndex, points, size])

  // Draw
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || size.w === 0 || size.h === 0) return
    const dpr = window.devicePixelRatio || 1
    canvas.width = size.w * dpr
    canvas.height = size.h * dpr
    canvas.style.width = `${size.w}px`
    canvas.style.height = `${size.h}px`
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

    ctx.fillStyle = '#141414'
    ctx.fillRect(0, 0, size.w, size.h)

    const { k, tx, ty } = viewRef.current
    const margin = 8
    const W = size.w
    const H = size.h
    const innerW = W - 2 * margin
    const innerH = H - 2 * margin
    const radius = 2.5
    const hasHL = !!highlightIds && highlightIds.size > 0

    // Base layer: dim if a highlight set is active.
    ctx.globalAlpha = hasHL ? 0.18 : 0.85
    for (let i = 0; i < points.length; i++) {
      const p = points[i]
      if (hasHL && highlightIds!.has(p.image_id)) continue
      const px = (margin + p.x * innerW) * k + tx
      const py = (margin + (1 - p.y) * innerH) * k + ty
      if (px < -4 || py < -4 || px > W + 4 || py > H + 4) continue
      ctx.fillStyle = colors[i]
      ctx.beginPath()
      ctx.arc(px, py, radius, 0, Math.PI * 2)
      ctx.fill()
    }

    // Highlight layer (k-NN)
    if (hasHL) {
      ctx.globalAlpha = 1
      for (let i = 0; i < points.length; i++) {
        const p = points[i]
        if (!highlightIds!.has(p.image_id)) continue
        const px = (margin + p.x * innerW) * k + tx
        const py = (margin + (1 - p.y) * innerH) * k + ty
        if (px < -4 || py < -4 || px > W + 4 || py > H + 4) continue
        ctx.fillStyle = colors[i]
        ctx.beginPath()
        ctx.arc(px, py, radius + 1.5, 0, Math.PI * 2)
        ctx.fill()
      }
    }

    // Selected ring
    ctx.globalAlpha = 1
    const drawRing = (id: number | null, color: string, ringRadius: number) => {
      if (id == null) return
      const idx = idIndex.get(id)
      if (idx == null) return
      const p = points[idx]
      const px = (margin + p.x * innerW) * k + tx
      const py = (margin + (1 - p.y) * innerH) * k + ty
      ctx.strokeStyle = color
      ctx.lineWidth = 2
      ctx.beginPath()
      ctx.arc(px, py, ringRadius, 0, Math.PI * 2)
      ctx.stroke()
    }
    drawRing(focusId, '#d7ba7d', 9)
    drawRing(selectedId, '#4fc1ff', 7)
  }, [points, colors, size, idIndex, selectedId, focusId, highlightIds])

  // Pan
  const onMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button !== 0) return
    const v = viewRef.current
    dragRef.current = { x: e.clientX, y: e.clientY, tx: v.tx, ty: v.ty, moved: false }
  }, [])

  const findHit = useCallback(
    (px: number, py: number): EmbeddingPoint | null => {
      const { k, tx, ty } = viewRef.current
      const margin = 8
      const innerW = size.w - 2 * margin
      const innerH = size.h - 2 * margin
      const r = 6
      let best: EmbeddingPoint | null = null
      let bestDist = r * r
      for (let i = 0; i < points.length; i++) {
        const p = points[i]
        const sx = (margin + p.x * innerW) * k + tx
        const sy = (margin + (1 - p.y) * innerH) * k + ty
        const dx = sx - px
        const dy = sy - py
        const d = dx * dx + dy * dy
        if (d < bestDist) {
          bestDist = d
          best = p
        }
      }
      return best
    },
    [points, size],
  )

  const onMouseMove = useCallback(
    (e: React.MouseEvent) => {
      const rect = containerRef.current?.getBoundingClientRect()
      if (!rect) return
      const px = e.clientX - rect.left
      const py = e.clientY - rect.top

      if (dragRef.current) {
        const dx = e.clientX - dragRef.current.x
        const dy = e.clientY - dragRef.current.y
        if (Math.abs(dx) + Math.abs(dy) > 2) dragRef.current.moved = true
        viewRef.current = {
          ...viewRef.current,
          tx: dragRef.current.tx + dx,
          ty: dragRef.current.ty + dy,
        }
        setTick((n) => n + 1)
        onHover(null)
        return
      }

      const hit = findHit(px, py)
      if (hit) onHover({ point: hit, screenX: px, screenY: py })
      else onHover(null)
    },
    [findHit, onHover],
  )

  const onMouseUp = useCallback(
    (e: React.MouseEvent) => {
      const drag = dragRef.current
      dragRef.current = null
      if (!drag || drag.moved) return
      const rect = containerRef.current?.getBoundingClientRect()
      if (!rect) return
      const px = e.clientX - rect.left
      const py = e.clientY - rect.top
      const hit = findHit(px, py)
      if (hit) onSelect(hit)
    },
    [findHit, onSelect],
  )

  const onMouseLeave = useCallback(() => {
    dragRef.current = null
    onHover(null)
  }, [onHover])

  const onWheel = useCallback(
    (e: React.WheelEvent) => {
      const rect = containerRef.current?.getBoundingClientRect()
      if (!rect) return
      const px = e.clientX - rect.left
      const py = e.clientY - rect.top
      const v = viewRef.current
      const factor = Math.exp(-e.deltaY * 0.0015)
      const newK = Math.max(0.5, Math.min(40, v.k * factor))
      // Zoom around the cursor: keep the world point under the cursor fixed.
      const wx = (px - v.tx) / v.k
      const wy = (py - v.ty) / v.k
      viewRef.current = {
        k: newK,
        tx: px - wx * newK,
        ty: py - wy * newK,
      }
      setTick((n) => n + 1)
    },
    [],
  )

  const resetView = useCallback(() => {
    viewRef.current = { ...DEFAULT_VIEW }
    setTick((n) => n + 1)
  }, [])

  return (
    <div
      ref={containerRef}
      className="relative h-full w-full overflow-hidden bg-[#141414] select-none"
      onMouseDown={onMouseDown}
      onMouseMove={onMouseMove}
      onMouseUp={onMouseUp}
      onMouseLeave={onMouseLeave}
      onWheel={onWheel}
    >
      <canvas
        ref={canvasRef}
        className="absolute inset-0 cursor-grab active:cursor-grabbing"
      />
      <button
        type="button"
        onClick={resetView}
        className="absolute right-2 top-2 rounded border border-[#474747] bg-[#252526]/90 px-2 py-1 text-[11px] text-[#cccccc] hover:bg-[#3c3c3c]"
      >
        Reset view
      </button>
      <div className="pointer-events-none absolute left-2 bottom-2 text-[10px] text-[#6d6d6d]">
        {points.length.toLocaleString()} points · drag to pan · wheel to zoom
      </div>
    </div>
  )
}
