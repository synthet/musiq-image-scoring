import { useEmbeddingAtlasStore } from '../stores/embeddingAtlasStore';
import type { EmbeddingPoint } from '../hooks/useEmbeddingMap';
// Radix Popover could be used here for more complex positioning, 
// but we are using a fixed overlay for simplicity.

interface ImageHoverCardProps {
  points: EmbeddingPoint[];
}

export function ImageHoverCard({ points }: ImageHoverCardProps) {
  const hoveredPointId = useEmbeddingAtlasStore((s) => s.hoveredPointId);
  const hoveredPoint = points.find((p) => p.image_id === hoveredPointId);

  // Position it fixed based on mouse coords would be better, but we can simulate a simple fixed overlay
  // or rely on Cosmograph's coordinate to screen space mapping if we had the ref.
  // For a simple implementation, we'll just show it in a fixed corner when a point is hovered.

  if (!hoveredPointId || !hoveredPoint) return null;

  return (
    <div className="pointer-events-none fixed bottom-4 left-4 z-50 overflow-hidden rounded-xl border border-slate-700 bg-slate-900/90 shadow-xl backdrop-blur">
      <div className="flex w-64 flex-col">
        {hoveredPoint.thumbnail_path ? (
          <img
            src={`/api/images/${hoveredPoint.image_id}/thumbnail`}
            alt={hoveredPoint.file_path}
            className="h-40 w-full object-cover"
          />
        ) : (
          <div className="flex h-40 w-full items-center justify-center bg-slate-800 text-slate-500">
            No Preview
          </div>
        )}
        <div className="p-3 text-sm">
          <div className="truncate font-medium text-slate-200" title={hoveredPoint.file_path}>
            {hoveredPoint.file_path.split(/[/\\]/).pop()}
          </div>
          <div className="mt-1 flex gap-2 text-xs text-slate-400">
            {hoveredPoint.score_general != null && (
              <span className="rounded bg-slate-800 px-1.5 py-0.5">
                ★ {hoveredPoint.score_general.toFixed(1)}
              </span>
            )}
            {hoveredPoint.label && (
              <span className="rounded bg-slate-800 px-1.5 py-0.5">{hoveredPoint.label}</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
