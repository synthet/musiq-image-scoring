import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { ImageDetail } from '@/types/api';
import { useEmbeddingAtlasStore } from '../stores/embeddingAtlasStore';
import { X } from 'lucide-react';

export function ImageInspectorSheet() {
  const { selectedPointId, sidePanelOpen, setSidePanelOpen, setSelectedPointId } =
    useEmbeddingAtlasStore();

  const { data: image, isLoading } = useQuery({
    queryKey: ['imageDetail', selectedPointId],
    queryFn: () => api.get<ImageDetail>(`/images/${selectedPointId}`),
    enabled: !!selectedPointId && sidePanelOpen,
  });

  if (!sidePanelOpen || !selectedPointId) return null;

  return (
    <div className="flex h-full w-full flex-col bg-slate-900 border-l border-slate-800">
      <div className="flex items-center justify-between border-b border-slate-800 p-4">
        <h2 className="text-sm font-semibold text-slate-200">Inspector</h2>
        <button
          onClick={() => {
            setSidePanelOpen(false);
            setSelectedPointId(null);
          }}
          className="rounded p-1 hover:bg-slate-800 text-slate-400 hover:text-slate-200"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      
      <div className="flex-1 overflow-y-auto p-4">
        {isLoading ? (
          <div className="animate-pulse text-sm text-slate-400">Loading details...</div>
        ) : !image ? (
          <div className="text-sm text-slate-400">Failed to load image details.</div>
        ) : (
          <div className="space-y-6">
            <div className="overflow-hidden rounded-lg bg-slate-950">
              <img 
                src={`/api/images/${image.id}/thumbnail`} 
                alt={image.file_name} 
                className="w-full object-contain max-h-64"
              />
            </div>
            
            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
                Metadata
              </h3>
              <div className="space-y-2 text-sm text-slate-300">
                <div className="flex justify-between">
                  <span className="text-slate-500">File</span>
                  <span className="truncate ml-4">{image.file_name}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Rating</span>
                  <span>{image.rating != null ? image.rating : '-'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Label</span>
                  <span>{image.label || '-'}</span>
                </div>
              </div>
            </div>

            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
                Scores
              </h3>
              <div className="space-y-2 text-sm text-slate-300">
                <div className="flex justify-between">
                  <span className="text-slate-500">General</span>
                  <span>{image.score_general?.toFixed(3) || '-'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Aesthetic</span>
                  <span>{image.score_aesthetic?.toFixed(3) || '-'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Technical</span>
                  <span>{image.score_technical?.toFixed(3) || '-'}</span>
                </div>
              </div>
            </div>

          </div>
        )}
      </div>
    </div>
  );
}
