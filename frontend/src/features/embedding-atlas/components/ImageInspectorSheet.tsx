import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { ImageDetail } from '@/types/api';
import { useEmbeddingAtlasStore } from '../stores/embeddingAtlasStore';
import { X } from 'lucide-react';

export function ImageInspectorSheet() {
  const { selectedPointId, sidePanelOpen, setSidePanelOpen } = useEmbeddingAtlasStore();

  const { data: image, isLoading } = useQuery({
    queryKey: ['imageDetail', selectedPointId],
    queryFn: () => api.get<ImageDetail>(`/images/${selectedPointId}`),
    enabled: !!selectedPointId && sidePanelOpen,
  });

  if (!sidePanelOpen || !selectedPointId) return null;

  return (
    <div className="flex h-full min-w-64 w-full flex-col bg-slate-900 border-l border-slate-800">
      <div className="flex items-center justify-between border-b border-slate-800 p-4">
        <h2 className="text-sm font-semibold text-slate-200">Inspector</h2>
        <button
          type="button"
          onClick={() => setSidePanelOpen(false)}
          className="rounded p-1 hover:bg-slate-800 text-slate-400 hover:text-slate-200"
          title="Close inspector"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      
      <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden p-4">
        {isLoading ? (
          <div className="animate-pulse text-sm text-slate-400">Loading details...</div>
        ) : !image ? (
          <div className="text-sm text-slate-400">Failed to load image details.</div>
        ) : (
          <div className="space-y-6">
            <div className="overflow-hidden rounded-lg bg-slate-950">
              <img
                src={
                  image.thumbnail_path
                    ? `/source-image?path=${encodeURIComponent(image.thumbnail_path)}&thumb=1`
                    : `/source-image?path=${encodeURIComponent(image.file_path)}&thumb=1`
                }
                alt={image.file_name}
                className="w-full object-contain max-h-64"
              />
            </div>
            
            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
                Metadata
              </h3>
              <div className="space-y-3 text-sm text-slate-300">
                <div className="flex min-w-0 flex-col gap-0.5">
                  <span className="shrink-0 text-slate-500">File</span>
                  <span className="break-all text-slate-200">{image.file_name}</span>
                </div>
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="text-slate-500">Rating</span>
                  <span className="min-w-0">{image.rating != null ? image.rating : '-'}</span>
                </div>
                <div className="flex min-w-0 flex-col gap-0.5">
                  <span className="text-slate-500">Label</span>
                  <span className="break-words text-slate-200">{image.label || '-'}</span>
                </div>
              </div>
            </div>

            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
                Scores
              </h3>
              <div className="space-y-2 text-sm text-slate-300">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="text-slate-500">General</span>
                  <span className="font-mono tabular-nums">{image.score_general?.toFixed(3) ?? '-'}</span>
                </div>
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="text-slate-500">Aesthetic</span>
                  <span className="font-mono tabular-nums">{image.score_aesthetic?.toFixed(3) ?? '-'}</span>
                </div>
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="text-slate-500">Technical</span>
                  <span className="font-mono tabular-nums">{image.score_technical?.toFixed(3) ?? '-'}</span>
                </div>
              </div>
            </div>

          </div>
        )}
      </div>
    </div>
  );
}
