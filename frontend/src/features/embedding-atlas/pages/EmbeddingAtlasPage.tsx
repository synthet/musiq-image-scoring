import { useLayoutEffect, useState } from 'react';
import { Group as PanelGroup, Panel, Separator, usePanelRef } from 'react-resizable-panels';
import { useEmbeddingMap } from '../hooks/useEmbeddingMap';
import type { FetchEmbeddingMapParams } from '../hooks/useEmbeddingMap';
import type { EmbeddingPoint } from '../hooks/useEmbeddingMap';
import { EmbeddingCanvas } from '../components/EmbeddingCanvas';
import { EmbeddingToolbar } from '../components/EmbeddingToolbar';
import { ImageHoverCard } from '../components/ImageHoverCard';
import { ImageInspectorSheet } from '../components/ImageInspectorSheet';
import { SimilarImagesFilmstrip } from '../components/SimilarImagesFilmstrip';
import { useEmbeddingAtlasStore } from '../stores/embeddingAtlasStore';

function unwrapEmbeddingPayload(data: unknown): {
  points?: unknown;
  meta?: { error?: string };
} | null {
  if (!data || typeof data !== 'object') return null;
  const o = data as Record<string, unknown>;
  if (Array.isArray(o.points)) return o as { points: unknown[]; meta?: { error?: string } };
  const inner = o.data;
  if (inner && typeof inner === 'object' && Array.isArray((inner as Record<string, unknown>).points)) {
    return inner as { points: unknown[]; meta?: { error?: string } };
  }
  return null;
}

export function EmbeddingAtlasPage() {
  const { sidePanelOpen, selectedPointId } = useEmbeddingAtlasStore();
  const filmstripPanelRef = usePanelRef();
  const inspectorPanelRef = usePanelRef();

  const [params, setParams] = useState<FetchEmbeddingMapParams>({
    method: 'umap',
  });

  const { data, isLoading, error } = useEmbeddingMap(params);

  const payload = unwrapEmbeddingPayload(data);
  const points = (Array.isArray(payload?.points) ? payload.points : []) as EmbeddingPoint[];
  const metaError = payload?.meta?.error ?? null;

  useLayoutEffect(() => {
    if (selectedPointId) filmstripPanelRef.current?.expand();
    else filmstripPanelRef.current?.collapse();
  }, [selectedPointId, filmstripPanelRef]);

  useLayoutEffect(() => {
    if (sidePanelOpen && selectedPointId) inspectorPanelRef.current?.expand();
    else inspectorPanelRef.current?.collapse();
  }, [sidePanelOpen, selectedPointId, inspectorPanelRef]);

  return (
    <div className="flex h-full min-h-0 w-full flex-col overflow-hidden bg-slate-950 text-slate-200">
      <PanelGroup orientation="horizontal" className="h-full min-h-0 w-full">
        <Panel id="atlas-main" minSize={48} defaultSize={72} className="min-h-0 min-w-0">
          <PanelGroup orientation="vertical" className="h-full min-h-0">
            <Panel id="atlas-canvas" minSize={36} defaultSize={78} className="min-h-0 min-w-0">
              <div className="relative flex h-full min-h-0 w-full flex-col">
                <EmbeddingToolbar
                  params={params}
                  setParams={setParams}
                  onRefresh={() => {
                    setParams((p) => ({ ...p, refresh: true }));
                    setTimeout(() => setParams((p) => ({ ...p, refresh: undefined })), 100);
                  }}
                />
                <div className="relative min-h-0 flex-1">
                  <EmbeddingCanvas
                    points={points}
                    isLoading={isLoading}
                    queryError={error instanceof Error ? error.message : error ? String(error) : null}
                    mapErrorCode={metaError ?? null}
                  />
                  <ImageHoverCard points={points} />
                </div>
              </div>
            </Panel>

            <Separator className="flex h-2 shrink-0 items-center justify-center bg-slate-900 transition-colors hover:bg-slate-800">
              <div className="h-1 w-8 rounded-full bg-slate-700" />
            </Separator>

            <Panel
              id="atlas-filmstrip"
              panelRef={filmstripPanelRef}
              collapsible
              collapsedSize={0}
              minSize={14}
              maxSize={40}
              defaultSize={22}
              className="min-h-0 min-w-0 overflow-hidden"
            >
              <SimilarImagesFilmstrip />
            </Panel>
          </PanelGroup>
        </Panel>

        <Separator className="flex w-2 shrink-0 flex-col items-center justify-center bg-slate-900 transition-colors hover:bg-slate-800">
          <div className="h-8 w-1 rounded-full bg-slate-700" />
        </Separator>

        <Panel
          id="atlas-inspector"
          panelRef={inspectorPanelRef}
          collapsible
          collapsedSize={0}
          minSize={24}
          maxSize={42}
          defaultSize={28}
          className="min-h-0 min-w-0 overflow-hidden"
        >
          <ImageInspectorSheet />
        </Panel>
      </PanelGroup>
    </div>
  );
}
