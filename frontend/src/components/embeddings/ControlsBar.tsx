import type { EmbeddingSpace } from '@/types/api'
import type { ColorBy } from './ScatterCanvas'

export interface MapControlsValue {
  spaceCode: string
  method: 'umap' | 'tsne'
  sampleLimit: number | null
  nNeighbors: number
  minDist: number
  pcaDim: 'auto' | 'off' | number
  colorBy: ColorBy
}

export interface ControlsBarProps {
  spaces: EmbeddingSpace[]
  defaultSpaceCode: string
  value: MapControlsValue
  onChange: (next: MapControlsValue) => void
  onRefresh: () => void
  mapLoading: boolean
  cacheKey: string | null
  lastComputed: string | null
}

const PCA_OPTIONS: { id: 'auto' | 'off' | '50' | '100'; label: string }[] = [
  { id: 'auto', label: 'Auto' },
  { id: 'off', label: 'Off' },
  { id: '50', label: '50' },
  { id: '100', label: '100' },
]

function pcaToValue(id: (typeof PCA_OPTIONS)[number]['id']): 'auto' | 'off' | number {
  if (id === 'auto' || id === 'off') return id
  return id === '50' ? 50 : 100
}

function valueToPcaId(v: MapControlsValue['pcaDim']): (typeof PCA_OPTIONS)[number]['id'] {
  if (v === 'auto') return 'auto'
  if (v === 'off') return 'off'
  if (v === 50) return '50'
  if (v === 100) return '100'
  return 'auto'
}

export function ControlsBar({
  spaces,
  defaultSpaceCode,
  value,
  onChange,
  onRefresh,
  mapLoading,
  cacheKey,
  lastComputed,
}: ControlsBarProps) {
  const set = (patch: Partial<MapControlsValue>) => onChange({ ...value, ...patch })

  return (
    <div className="flex flex-wrap items-end gap-3 border-b border-[#3c3c3c] bg-[#252526] px-3 py-2 shrink-0">
      <label className="flex flex-col gap-0.5 min-w-[10rem]">
        <span className="text-[10px] uppercase tracking-wide text-[#6d6d6d]">Embedding space</span>
        <select
          className="rounded border border-[#474747] bg-[#1e1e1e] px-2 py-1.5 text-xs text-[#cccccc]"
          value={value.spaceCode}
          onChange={(e) => set({ spaceCode: e.target.value || defaultSpaceCode })}
        >
          {spaces.length === 0 && (
            <option value={defaultSpaceCode}>Loading…</option>
          )}
          {spaces.map((s) => (
            <option key={s.code} value={s.code}>
              {s.code} ({s.dim}d)
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-0.5">
        <span className="text-[10px] uppercase tracking-wide text-[#6d6d6d]">Method</span>
        <select
          className="rounded border border-[#474747] bg-[#1e1e1e] px-2 py-1.5 text-xs text-[#cccccc]"
          value={value.method}
          onChange={(e) => set({ method: e.target.value as 'umap' | 'tsne' })}
        >
          <option value="umap">UMAP</option>
          <option value="tsne">t-SNE</option>
        </select>
      </label>

      <label className="flex flex-col gap-0.5 w-[7rem]">
        <span className="text-[10px] uppercase tracking-wide text-[#6d6d6d]">Max points</span>
        <input
          type="number"
          min={3}
          max={50000}
          className="rounded border border-[#474747] bg-[#1e1e1e] px-2 py-1.5 text-xs text-[#cccccc]"
          placeholder="default"
          value={value.sampleLimit ?? ''}
          onChange={(e) => {
            const v = e.target.value
            if (v === '') set({ sampleLimit: null })
            else {
              const n = parseInt(v, 10)
              if (Number.isFinite(n)) set({ sampleLimit: n })
            }
          }}
        />
      </label>

      <label className="flex flex-col gap-0.5 w-[6rem]">
        <span className="text-[10px] uppercase tracking-wide text-[#6d6d6d]">N neighbors</span>
        <input
          type="number"
          min={2}
          max={200}
          className="rounded border border-[#474747] bg-[#1e1e1e] px-2 py-1.5 text-xs text-[#cccccc]"
          value={value.nNeighbors}
          onChange={(e) => {
            const n = parseInt(e.target.value, 10)
            if (Number.isFinite(n)) set({ nNeighbors: n })
          }}
        />
      </label>

      <label className="flex flex-col gap-0.5 w-[5rem]">
        <span className="text-[10px] uppercase tracking-wide text-[#6d6d6d]">Min dist</span>
        <input
          type="number"
          min={0}
          max={1}
          step={0.05}
          className="rounded border border-[#474747] bg-[#1e1e1e] px-2 py-1.5 text-xs text-[#cccccc]"
          value={value.minDist}
          onChange={(e) => {
            const n = parseFloat(e.target.value)
            if (Number.isFinite(n)) set({ minDist: n })
          }}
        />
      </label>

      <label className="flex flex-col gap-0.5">
        <span className="text-[10px] uppercase tracking-wide text-[#6d6d6d]">PCA (pre UMAP)</span>
        <select
          className="rounded border border-[#474747] bg-[#1e1e1e] px-2 py-1.5 text-xs text-[#cccccc]"
          value={valueToPcaId(value.pcaDim)}
          onChange={(e) => set({ pcaDim: pcaToValue(e.target.value as 'auto' | 'off' | '50' | '100') })}
        >
          {PCA_OPTIONS.map((o) => (
            <option key={o.id} value={o.id}>
              {o.label}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-0.5">
        <span className="text-[10px] uppercase tracking-wide text-[#6d6d6d]">Color by</span>
        <select
          className="rounded border border-[#474747] bg-[#1e1e1e] px-2 py-1.5 text-xs text-[#cccccc]"
          value={value.colorBy}
          onChange={(e) => set({ colorBy: e.target.value as ColorBy })}
        >
          <option value="label">Label</option>
          <option value="rating">Rating</option>
          <option value="score_general">Score (general)</option>
        </select>
      </label>

      <div className="ml-auto flex items-center gap-2">
        {cacheKey && (
          <span className="text-[10px] text-[#6d6d6d] font-mono max-w-[9rem] truncate" title={cacheKey}>
            cache {cacheKey.slice(0, 8)}…
          </span>
        )}
        {lastComputed && (
          <span className="text-[10px] text-[#6d6d6d] hidden sm:inline" title={lastComputed}>
            {new Date(lastComputed).toLocaleString()}
          </span>
        )}
        <button
          type="button"
          onClick={onRefresh}
          disabled={mapLoading}
          className="rounded border border-[#4fc1ff] bg-[#1e1e1e] px-3 py-1.5 text-xs font-medium text-[#4fc1ff] hover:bg-[#3c3c3c] disabled:opacity-50"
        >
          {mapLoading ? 'Loading…' : 'Refresh map'}
        </button>
      </div>
    </div>
  )
}
