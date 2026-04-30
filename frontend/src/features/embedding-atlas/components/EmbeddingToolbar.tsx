import { useEmbeddingAtlasStore } from '../stores/embeddingAtlasStore';
import type { ColorMode } from '../stores/embeddingAtlasStore';
import { ProjectionSettingsDialog } from './ProjectionSettingsDialog';
import type { FetchEmbeddingMapParams } from '../hooks/useEmbeddingMap';
import { MousePointer2, Lasso } from 'lucide-react';
import { clsx } from 'clsx';

interface EmbeddingToolbarProps {
  params: FetchEmbeddingMapParams;
  setParams: (params: FetchEmbeddingMapParams) => void;
  onRefresh: () => void;
}

export function EmbeddingToolbar({ params, setParams, onRefresh }: EmbeddingToolbarProps) {
  const { activeColorMode, setActiveColorMode, currentTool, setCurrentTool } = useEmbeddingAtlasStore();

  return (
    <div className="absolute top-4 left-4 right-4 z-10 flex items-center justify-between rounded-lg border border-slate-700/50 bg-slate-900/80 px-4 py-2 shadow-lg backdrop-blur">
      <div className="flex items-center gap-6">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-slate-400">Color by:</span>
          <select 
            className="rounded bg-slate-800 px-2 py-1 text-sm text-slate-200 outline-none hover:bg-slate-700"
            value={activeColorMode}
            onChange={(e) => setActiveColorMode(e.target.value as ColorMode)}
          >
            <option value="folder">Folder</option>
            <option value="aesthetic">Aesthetic Score</option>
            <option value="technical">Technical Score</option>
          </select>
        </div>

        <div className="flex items-center gap-1 bg-slate-800 rounded p-0.5">
          <button
            className={clsx(
              "p-1.5 rounded text-slate-400 hover:text-slate-200 transition-colors",
              currentTool === 'pointer' && "bg-slate-700 text-white"
            )}
            onClick={() => setCurrentTool('pointer')}
            title="Pointer Tool"
          >
            <MousePointer2 className="h-4 w-4" />
          </button>
          <button
            className={clsx(
              "p-1.5 rounded text-slate-400 hover:text-slate-200 transition-colors",
              currentTool === 'lasso' && "bg-slate-700 text-white"
            )}
            onClick={() => setCurrentTool('lasso')}
            title="Lasso Selection"
          >
            <Lasso className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div>
        <ProjectionSettingsDialog params={params} setParams={setParams} onRefresh={onRefresh} />
      </div>
    </div>
  );
}
