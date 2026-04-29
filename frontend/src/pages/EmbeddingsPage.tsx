import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { embeddingsApi } from '@/api/embeddings'
import { ControlsBar, type MapControlsValue } from '@/components/embeddings/ControlsBar'
import { SidePanel } from '@/components/embeddings/SidePanel'
import { HoverTooltip } from '@/components/embeddings/HoverTooltip'
import { ScatterCanvas } from '@/components/embeddings/ScatterCanvas'
import { useUiStore } from '@/stores/uiStore'
import type { EmbeddingMapResponse, EmbeddingPoint } from '@/types/api'

const DEFAULT_CONTROLS: MapControlsValue = {
  spaceCode: 'mobilenet_v2_imagenet_gap',
  method: 'umap',
  sampleLimit: null,
  nNeighbors: 30,
  minDist: 0.1,
  pcaDim: 'auto',
  colorBy: 'score_general',
}

function pcaToApi(v: MapControlsValue['pcaDim']): number | undefined {
  if (v === 'auto') return undefined
  if (v === 'off') return 0
  return v
}

export function EmbeddingsPage() {
  const selectedScopePath = useUiStore((s) => s.selectedScopePath)
  const [searchParams, setSearchParams] = useSearchParams()
  const focusParam = searchParams.get('focus')
  const focusId =
    focusParam != null && focusParam !== '' && Number.isFinite(Number(focusParam))
      ? parseInt(focusParam, 10)
      : null

  const [ctrl, setCtrl] = useState<MapControlsValue>(DEFAULT_CONTROLS)
  const [selected, setSelected] = useState<EmbeddingPoint | null>(null)
  const [hover, setHover] = useState<{
    point: EmbeddingPoint
    screenX: number
    screenY: number
  } | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [containerSize, setContainerSize] = useState({ w: 0, h: 0 })
  const forceRefreshNext = useRef(false)

  const { data: spacesPayload, isError: spacesErr, error: spacesError } = useQuery({
    queryKey: ['embedding', 'spaces'],
    queryFn: () => embeddingsApi.spaces(),
    staleTime: 60_000,
  })

  const defaultCode = spacesPayload?.meta?.default_code ?? 'mobilenet_v2_imagenet_gap'
  const spaceCodes = useMemo(
    () => new Set((spacesPayload?.spaces ?? []).map((s) => s.code)),
    [spacesPayload?.spaces],
  )

  useEffect(() => {
    if (!spacesPayload?.spaces.length) return
    if (!spaceCodes.has(ctrl.spaceCode)) {
      setCtrl((c) => ({ ...c, spaceCode: defaultCode }))
    }
  }, [spacesPayload, spaceCodes, ctrl.spaceCode, defaultCode])

  const mapKey = useMemo(
    () =>
      [
        'embedding',
        'map',
        selectedScopePath,
        ctrl.spaceCode,
        ctrl.method,
        ctrl.sampleLimit,
        ctrl.nNeighbors,
        ctrl.minDist,
        ctrl.pcaDim,
      ] as const,
    [
      selectedScopePath,
      ctrl.spaceCode,
      ctrl.method,
      ctrl.sampleLimit,
      ctrl.nNeighbors,
      ctrl.minDist,
      ctrl.pcaDim,
    ],
  )

  const {
    data: mapPayload,
    isLoading: mapLoading,
    isError: mapIsErr,
    error: mapError,
    refetch: refetchMap,
    isFetching: mapFetching,
  } = useQuery({
    queryKey: mapKey,
    queryFn: async () => {
      const refresh = forceRefreshNext.current
      forceRefreshNext.current = false
      return embeddingsApi.map({
        folder_path: selectedScopePath ?? undefined,
        method: ctrl.method,
        space_code: ctrl.spaceCode,
        sample_limit: ctrl.sampleLimit ?? undefined,
        n_neighbors: ctrl.nNeighbors,
        min_dist: ctrl.minDist,
        pca_dim: pcaToApi(ctrl.pcaDim),
        refresh,
      })
    },
    enabled: spaceCodes.size === 0 || spaceCodes.has(ctrl.spaceCode),
    staleTime: 30_000,
  })

  const mapData: EmbeddingMapResponse | null =
    mapPayload && typeof mapPayload === 'object' && 'points' in mapPayload
      ? (mapPayload as EmbeddingMapResponse)
      : null

  const points = mapData?.points ?? []
  const meta = mapData?.meta
  const metaError = meta?.error

  useEffect(() => {
    if (points.length === 0) return
    if (focusId == null) return
    const hit = points.find((p) => p.image_id === focusId)
    if (hit) setSelected(hit)
  }, [points, focusId])

  const highlightIds = useQuery({
    queryKey: [
      'embedding',
      'highlight',
      selected?.image_id,
      ctrl.spaceCode,
      selectedScopePath,
    ] as const,
    queryFn: () =>
      embeddingsApi.similar(selected!.image_id, {
        limit: 36,
        min_similarity: 0.4,
        embedding_space: ctrl.spaceCode,
        folder_path: selectedScopePath ?? undefined,
      }),
    enabled: selected != null,
    select: (d) => new Set((d?.results ?? []).map((r) => r.image_id)),
  })

  const onSelectPoint = useCallback(
    (p: EmbeddingPoint) => {
      setSelected(p)
      setSearchParams(
        (prev) => {
          const n = new URLSearchParams(prev)
          n.set('focus', String(p.image_id))
          return n
        },
        { replace: true },
      )
    },
    [setSearchParams],
  )

  const onClearSelection = useCallback(() => {
    setSelected(null)
    setSearchParams(
      (prev) => {
        const n = new URLSearchParams(prev)
        n.delete('focus')
        return n
      },
      { replace: true },
    )
  }, [setSearchParams])

  const onRefreshMap = useCallback(() => {
    forceRefreshNext.current = true
    void refetchMap()
  }, [refetchMap])

  useLayoutSizeObserver(containerRef, setContainerSize)

  if (spacesErr) {
    return (
      <div className="p-4 text-sm text-[#f44747]">
        Could not load embedding spaces:{' '}
        {(spacesError as Error)?.message ?? 'unknown error'}
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 border-b border-[#3c3c3c] bg-[#1e1e1e] px-4 py-2">
        <h1 className="text-sm font-semibold text-[#cccccc]">Vector DB</h1>
        <p className="text-[11px] text-[#6d6d6d] mt-0.5">
          2D projection (UMAP / t-SNE) of stored vectors; scope from the top scope selector when
          set.
        </p>
      </div>

      <ControlsBar
        spaces={spacesPayload?.spaces ?? []}
        defaultSpaceCode={defaultCode}
        value={ctrl}
        onChange={setCtrl}
        onRefresh={onRefreshMap}
        mapLoading={mapLoading || mapFetching}
        cacheKey={meta?.cache_key ?? null}
        lastComputed={meta?.computed_at ?? null}
      />

      {metaError && (
        <div className="shrink-0 px-4 py-2 text-xs text-[#d7ba7d] border-b border-[#3c3c3c] bg-[#2a2a1a]">
          Map unavailable: <span className="font-mono">{metaError}</span>
          {meta?.message && <span className="ml-1 text-[#9d9d9d]">{meta.message}</span>}
        </div>
      )}

      {mapIsErr && (
        <div className="shrink-0 px-4 py-2 text-xs text-[#f44747]">
          {(mapError as Error)?.message ?? 'Map request failed'}
        </div>
      )}

      <div ref={containerRef} className="flex flex-1 min-h-0 min-w-0">
        <div className="relative flex-1 min-w-0 min-h-0">
          {!metaError && points.length === 0 && !mapLoading && !mapIsErr && (
            <div className="absolute inset-0 z-10 flex items-center justify-center text-sm text-[#6d6d6d] pointer-events-none">
              No points (adjust scope or run clustering / embedding jobs).
            </div>
          )}
          <ScatterCanvas
            points={points}
            colorBy={ctrl.colorBy}
            selectedId={selected?.image_id ?? null}
            focusId={focusId}
            highlightIds={highlightIds.data}
            onHover={setHover}
            onSelect={onSelectPoint}
          />
          {hover && containerRef.current && (
            <HoverTooltip
              point={hover.point}
              x={hover.screenX}
              y={hover.screenY}
              containerWidth={containerSize.w || containerRef.current.clientWidth}
              containerHeight={containerSize.h || containerRef.current.clientHeight}
            />
          )}
        </div>
        <SidePanel
          selected={selected}
          embeddingSpace={ctrl.spaceCode}
          folderPath={selectedScopePath}
          onClearSelection={onClearSelection}
        />
      </div>
    </div>
  )
}

function useLayoutSizeObserver(
  ref: RefObject<HTMLDivElement | null>,
  set: (s: { w: number; h: number }) => void,
) {
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver((entries) => {
      const cr = entries[0].contentRect
      set({ w: Math.floor(cr.width), h: Math.floor(cr.height) })
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [ref, set])
}
