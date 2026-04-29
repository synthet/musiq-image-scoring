import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ExternalLink, Image as ImageIcon } from 'lucide-react'
import { embeddingsApi } from '@/api/embeddings'
import { imageInspectorPath, embeddingsPathFor } from '@/utils/routes'
import type { EmbeddingPoint, SimilarImage } from '@/types/api'

export interface SidePanelProps {
  selected: EmbeddingPoint | null
  embeddingSpace: string
  folderPath: string | null
  onClearSelection: () => void
}

function thumbFor(sim: SimilarImage): string {
  return `/source-image?path=${encodeURIComponent(sim.file_path)}&thumb=1`
}

function selectThumb(p: EmbeddingPoint): string | null {
  const path = p.thumbnail_path || p.file_path
  if (!path) return null
  return `/source-image?path=${encodeURIComponent(path)}&thumb=1`
}

export function SidePanel({ selected, embeddingSpace, folderPath, onClearSelection }: SidePanelProps) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: [
      'embeddings',
      'similar',
      selected?.image_id,
      embeddingSpace,
      folderPath,
    ] as const,
    queryFn: () =>
      embeddingsApi.similar(selected!.image_id, {
        limit: 24,
        min_similarity: 0.5,
        embedding_space: embeddingSpace,
        folder_path: folderPath ?? undefined,
      }),
    enabled: selected != null,
  })

  if (!selected) {
    return (
      <div className="h-full w-[min(100%,20rem)] shrink-0 border-l border-[#3c3c3c] bg-[#1e1e1e] p-4">
        <div className="text-sm font-medium text-[#9d9d9d]">No selection</div>
        <p className="mt-2 text-xs text-[#6d6d6d] leading-relaxed">
          Click a point on the map to see the image, nearest neighbors, and quick links to the
          image inspector and back to the map.
        </p>
      </div>
    )
  }

  const results = data?.results ?? []
  const src = selectThumb(selected)

  return (
    <div className="h-full w-[min(100%,20rem)] shrink-0 border-l border-[#3c3c3c] bg-[#1e1e1e] flex flex-col min-h-0">
      <div className="shrink-0 p-3 border-b border-[#3c3c3c] space-y-2">
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-medium text-[#cccccc]">Image {selected.image_id}</span>
          <button
            type="button"
            onClick={onClearSelection}
            className="text-[10px] text-[#9d9d9d] hover:text-[#cccccc]"
          >
            Clear
          </button>
        </div>
        <div className="flex gap-2 flex-wrap text-[11px]">
          <Link
            to={imageInspectorPath(selected.image_id)}
            className="inline-flex items-center gap-1 rounded border border-[#474747] px-2 py-1 text-[#4fc1ff] hover:bg-[#3c3c3c]"
          >
            <ImageIcon size={12} />
            Open in inspector
          </Link>
          <Link
            to={embeddingsPathFor(selected.image_id)}
            className="inline-flex items-center gap-1 text-[#9d9d9d] hover:text-[#4fc1ff]"
          >
            <ExternalLink size={12} />
            Map link
          </Link>
        </div>
        <div className="relative rounded border border-[#3c3c3c] bg-[#141414] h-40 flex items-center justify-center">
          {src ? (
            <img src={src} alt="" className="max-h-full max-w-full object-contain" />
          ) : (
            <span className="text-xs text-[#6d6d6d]">no preview</span>
          )}
        </div>
        <div className="text-[10px] text-[#9d9d9d] space-y-0.5 font-mono break-all line-clamp-2" title={selected.file_path}>
          {selected.file_path}
        </div>
        {selected.label && (
          <div className="text-xs text-[#cccccc]">
            {selected.label} · {selected.rating != null && `★${selected.rating} · `}
            {selected.score_general != null && <span>gen {selected.score_general.toFixed(2)}</span>}
          </div>
        )}
      </div>

      <div className="flex-1 min-h-0 flex flex-col p-3">
        <div className="text-xs font-medium text-[#9d9d9d] mb-2">Nearest neighbors (cosine)</div>
        {isLoading && <div className="text-xs text-[#6d6d6d]">Loading…</div>}
        {isError && (
          <div className="text-xs text-[#f44747]">{(error as Error)?.message ?? 'Request failed'}</div>
        )}
        {!isLoading && !isError && results.length === 0 && (
          <div className="text-xs text-[#6d6d6d]">No neighbors (raise limit or lower threshold).</div>
        )}
        <div className="grid grid-cols-3 gap-1.5 overflow-y-auto pr-1">
          {results.map((s) => (
            <Link
              key={s.image_id}
              to={imageInspectorPath(s.image_id)}
              className="block rounded border border-[#2d2d2d] overflow-hidden bg-[#141414] hover:border-[#4fc1ff] transition-colors"
              title={`${s.image_id} · ${s.similarity.toFixed(3)}`}
            >
              <div className="aspect-square flex items-center justify-center">
                <img
                  src={thumbFor(s)}
                  alt=""
                  className="w-full h-full object-cover"
                />
              </div>
              <div className="text-[9px] text-center text-[#9d9d9d] font-mono py-0.5 truncate">
                {s.similarity.toFixed(2)}
              </div>
            </Link>
          ))}
        </div>
        <div className="mt-2 text-[10px] text-[#5a5a5a]">Space: {data?.embedding_space ?? embeddingSpace}</div>
      </div>
    </div>
  )
}
