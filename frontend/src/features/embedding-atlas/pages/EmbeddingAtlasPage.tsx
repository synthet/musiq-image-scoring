import { useState } from 'react';
import { Group as PanelGroup, Panel, Separator } from 'react-resizable-panels';
import { useEmbeddingMap } from '../hooks/useEmbeddingMap';
import type { FetchEmbeddingMapParams } from '../hooks/useEmbeddingMap';
import { EmbeddingCanvas } from '../components/EmbeddingCanvas';
import { EmbeddingToolbar } from '../components/EmbeddingToolbar';
import { ImageHoverCard } from '../components/ImageHoverCard';
import { ImageInspectorSheet } from '../components/ImageInspectorSheet';
import { SimilarImagesFilmstrip } from '../components/SimilarImagesFilmstrip';
import { useEmbeddingAtlasStore } from '../stores/embeddingAtlasStore';

export function EmbeddingAtlasPage() {
  const { sidePanelOpen, selectedPointId } = useEmbeddingAtlasStore();
  
  const [params, setParams] = useState<FetchEmbeddingMapParams>({
    space_code: 'mobilenet_v2_imagenet_gap',
    method: 'umap',
  });

  const { data, isLoading } = useEmbeddingMap(params);

  const points = data?.points || [];

  return (
    <div className="flex h-screen w-full flex-col overflow-hidden bg-slate-950 text-slate-200">
      <PanelGroup orientation="horizontal">
        {/* Main Canvas Area */}
        <Panel defaultSize={sidePanelOpen ? 75 : 100} minSize={30}>
          <PanelGroup orientation="vertical">
            <Panel defaultSize={selectedPointId ? 80 : 100} minSize={50}>
              <div className="relative h-full w-full">
                <EmbeddingToolbar 
                  params={params} 
                  setParams={setParams} 
                  onRefresh={() => {
                    setParams(p => ({ ...p, refresh: true }));
                    setTimeout(() => setParams(p => ({ ...p, refresh: undefined })), 100);
                  }} 
                />
                <EmbeddingCanvas points={points} isLoading={isLoading} />
                <ImageHoverCard points={points} />
              </div>
            </Panel>
            
            {/* Filmstrip Panel */}
            {selectedPointId && (
              <>
                <Separator className="flex h-2 items-center justify-center bg-slate-900 transition-colors hover:bg-slate-800">
                  <div className="h-1 w-8 rounded-full bg-slate-700" />
                </Separator>
                <Panel defaultSize={20} minSize={15} maxSize={40}>
                  <SimilarImagesFilmstrip />
                </Panel>
              </>
            )}
          </PanelGroup>
        </Panel>

        {/* Side Inspector Panel */}
        {sidePanelOpen && (
          <>
            <Separator className="flex w-2 flex-col items-center justify-center bg-slate-900 transition-colors hover:bg-slate-800">
              <div className="h-8 w-1 rounded-full bg-slate-700" />
            </Separator>
            <Panel defaultSize={25} minSize={20} maxSize={40}>
              <ImageInspectorSheet />
            </Panel>
          </>
        )}
      </PanelGroup>
    </div>
  );
}
