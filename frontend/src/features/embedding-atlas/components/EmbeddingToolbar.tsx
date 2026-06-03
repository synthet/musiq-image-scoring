import { useEmbeddingAtlasStore } from '../stores/embeddingAtlasStore';
import type { ColorMode } from '../stores/embeddingAtlasStore';
import { ProjectionSettingsDialog } from './ProjectionSettingsDialog';
import { EmbeddingSpaceLegend } from './EmbeddingSpaceSelect';
import type { FetchEmbeddingMapParams } from '../hooks/useEmbeddingMap';
import { MousePointer2, Lasso, PanelRight } from 'lucide-react';
import { clsx } from 'clsx';

interface EmbeddingToolbarProps {
  params: FetchEmbeddingMapParams;
  setParams: (params: FetchEmbeddingMapParams) => void;
  onRefresh: () => void;
}

export function EmbeddingToolbar({ params, setParams, onRefresh }: EmbeddingToolbarProps) {
  const {
    activeColorMode,
    setActiveColorMode,
    currentTool,
    setCurrentTool,
    selectedPointId,
    sidePanelOpen,
    setSidePanelOpen,
  } = useEmbeddingAtlasStore();

  return (
    <div className="absolute top-4 left-4 right-4 z-10 flex items-center justify-between rounded-lg border border-slate-700/50 bg-slate-900/80 px-4 py-2 shadow-lg backdrop-blur">
      <div className="flex items-center gap-6">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-slate-400">Color by:</span>
          <select
            className="max-w-[min(22rem,calc(100vw-12rem))] rounded bg-slate-800 px-2 py-1 text-sm text-slate-200 outline-none hover:bg-slate-700"
            value={activeColorMode}
            onChange={(e) => setActiveColorMode(e.target.value as ColorMode)}
            aria-label="Color points by"
          >
            <option value="folder">Folder</option>
            <optgroup label="Blended">
              <option value="general">General score (blended)</option>
            </optgroup>
            <optgroup label="Head scores">
              <option value="aesthetic">Aesthetic</option>
              <option value="technical">Technical</option>
            </optgroup>
            <optgroup label="IQ models (per metric)">
              <option value="iq_spaq">SPAQ</option>
              <option value="iq_ava">AVA</option>
              <option value="iq_koniq">KonIQ</option>
              <option value="iq_paq2piq">PAQ2PIQ</option>
              <option value="iq_liqe">LIQE</option>
            </optgroup>
          </select>
        </div>

        <div className="flex items-center gap-1 bg-slate-800 rounded p-0.5">
          <button
            type="button"
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
            type="button"
            className="p-1.5 rounded text-slate-600 cursor-not-allowed"
            disabled
            title="Lasso selection is not available yet"
            aria-disabled="true"
          >
            <Lasso className="h-4 w-4" />
          </button>
        </div>

        {params.space_code ? (
          <EmbeddingSpaceLegend code={params.space_code} />
        ) : null}
      </div>

      <div className="flex items-center gap-2">
        {selectedPointId != null && (
          <button
            type="button"
            onClick={() => setSidePanelOpen(!sidePanelOpen)}
            className={clsx(
              'flex items-center gap-1.5 rounded px-2.5 py-1.5 text-sm font-medium transition-colors',
              sidePanelOpen
                ? 'bg-slate-700 text-white'
                : 'bg-slate-800 text-slate-200 hover:bg-slate-700'
            )}
            title={sidePanelOpen ? 'Hide image inspector' : 'Show image inspector'}
          >
            <PanelRight className="h-4 w-4 shrink-0" />
            Inspector
          </button>
        )}
        <ProjectionSettingsDialog params={params} setParams={setParams} onRefresh={onRefresh} />
      </div>
    </div>
  );
}
