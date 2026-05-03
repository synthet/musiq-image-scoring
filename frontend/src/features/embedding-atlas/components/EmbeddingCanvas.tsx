import { useMemo, useCallback } from 'react';
import { CosmographProvider, Cosmograph } from '@cosmograph/react';
import { useEmbeddingAtlasStore } from '../stores/embeddingAtlasStore';
import type { EmbeddingPoint } from '../hooks/useEmbeddingMap';
import { colorForFolderKey, parentFolderKey } from '../utils/folderColor';

/** Five-step 0…1 ramp (red → green); Cosmograph-safe hex. */
const SCORE_UNIT_GRADIENT = ['#ef4444', '#f97316', '#eab308', '#84cc16', '#22c55e'] as const;

function colorFromUnitScore(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '#64748b';
  const x = Math.max(0, Math.min(1, v));
  const bin = Math.min(4, Math.floor(x * 5));
  return SCORE_UNIT_GRADIENT[bin]!;
}

interface EmbeddingCanvasProps {
  points: EmbeddingPoint[];
  isLoading: boolean;
  queryError?: string | null;
  mapErrorCode?: string | null;
}

function emptyStateDetail(mapErrorCode: string | null | undefined, queryError: string | null | undefined): string {
  if (queryError) return queryError;
  if (mapErrorCode === 'too_few_points') {
    return 'Too few images with embeddings in this scope to build a 2D map. Add more embedded images or widen the folder scope.';
  }
  if (mapErrorCode === 'unknown_embedding_space') {
    return 'Unknown embedding space. Choose another space in Settings.';
  }
  if (mapErrorCode) return `Projection could not be built (${mapErrorCode}). Try Settings → Re-Project.`;
  return 'Try another folder in the scope sidebar, a different embedding space in Settings, or Re-Project after more images are embedded.';
}

export function EmbeddingCanvas({
  points,
  isLoading,
  queryError = null,
  mapErrorCode = null,
}: EmbeddingCanvasProps) {
  const {
    activeColorMode,
    setHoveredPointId,
    setSelectedPointId,
    selectedPointId,
    hoveredPointId,
  } = useEmbeddingAtlasStore();

  const nodes = useMemo(() => {
    if (!points || !Array.isArray(points)) return [];
    return points.map((p, i) => ({
      id: String(p.image_id ?? `row-${i}`),
      index: i,
      ...p,
    }));
  }, [points]);

  const colorForIndex = useCallback(
    (index: number): string => {
      const node = nodes[index];
      if (!node) return '#64748b';
      const mode = activeColorMode;
      if (mode.startsWith('iq_')) {
        const col = `score_${mode.slice(3)}` as keyof EmbeddingPoint;
        const raw = node[col];
        return colorFromUnitScore(typeof raw === 'number' ? raw : undefined);
      }
      switch (mode) {
        case 'general':
          return colorFromUnitScore(node.score_general);
        case 'aesthetic': {
          const a = node.score_aesthetic ?? node.score_general;
          return colorFromUnitScore(a);
        }
        case 'technical':
          return colorFromUnitScore(node.score_technical);
        case 'folder': {
          const path = typeof node.file_path === 'string' ? node.file_path : '';
          return colorForFolderKey(parentFolderKey(path));
        }
        default:
          return '#64748b';
      }
    },
    [nodes, activeColorMode]
  );

  const sizeForIndex = useCallback(
    (index: number): number => {
      const node = nodes[index];
      if (!node) return 4;
      if (node.id === selectedPointId?.toString()) return 12;
      if (node.id === hoveredPointId?.toString()) return 9;
      return 4;
    },
    [nodes, selectedPointId, hoveredPointId]
  );

  if (isLoading) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-slate-950 text-slate-400">
        <div className="animate-pulse">Loading projection...</div>
      </div>
    );
  }

  if (!nodes.length) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center bg-slate-950 px-8 py-12 text-center text-slate-400">
        <p className="text-base text-slate-300">No embedding points to display</p>
        <p className="mt-3 max-w-md text-sm leading-relaxed text-slate-500">
          {emptyStateDetail(mapErrorCode, queryError)}
        </p>
      </div>
    );
  }

  return (
    <div className="relative h-full w-full bg-slate-950">
      <CosmographProvider>
        <Cosmograph
          points={nodes}
          pointIdBy="id"
          pointIndexBy="index"
          pointXBy="x"
          pointYBy="y"
          pointColorBy="image_id"
          pointColorByFn={(_value: unknown, index?: number) => colorForIndex(index ?? 0)}
          pointSizeBy="image_id"
          pointSizeByFn={(_value: unknown, index?: number) => sizeForIndex(index ?? 0)}
          pointIncludeColumns={['*']}
          enableSimulation={false}
          scalePointsOnZoom={true}
          pointSizeScale={1}
          hoveredPointCursor="pointer"
          fitViewOnInit
          onClick={(index) => {
            const node = index !== undefined ? nodes[index] : undefined;
            const iid = node && typeof node.image_id === 'number' ? node.image_id : null;
            setSelectedPointId(iid);
          }}
          onPointMouseOver={(index) => {
            const node = nodes[index];
            const iid = node && typeof node.image_id === 'number' ? node.image_id : null;
            setHoveredPointId(iid);
          }}
          onPointMouseOut={() => setHoveredPointId(null)}
        />
      </CosmographProvider>
    </div>
  );
}
