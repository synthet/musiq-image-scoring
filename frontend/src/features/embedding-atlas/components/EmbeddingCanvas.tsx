import React, { useMemo, useCallback } from 'react';
import { CosmographProvider, Cosmograph } from '@cosmograph/react';
import { useEmbeddingAtlasStore } from '../stores/embeddingAtlasStore';
import type { EmbeddingPoint } from '../hooks/useEmbeddingMap';

interface EmbeddingCanvasProps {
  points: EmbeddingPoint[];
  isLoading: boolean;
}

export function EmbeddingCanvas({ points, isLoading }: EmbeddingCanvasProps) {
  const {
    activeColorMode,
    setHoveredPointId,
    setSelectedPointId,
    selectedPointId,
    hoveredPointId,
  } = useEmbeddingAtlasStore();

  // Create nodes array for Cosmograph
  const nodes = useMemo(() => {
    return points.map((p) => ({
      id: p.image_id.toString(),
      ...p,
    }));
  }, [points]);

  // Color logic based on active mode
  const nodeColor = useCallback(
    (node: any) => {
      // Very basic coloring for now, ideally we'd use a color scale utility
      switch (activeColorMode) {
        case 'aesthetic':
          return node.score_general && node.score_general > 0.7 ? '#10b981' : '#f43f5e';
        case 'technical':
          return node.score_technical && node.score_technical > 0.7 ? '#3b82f6' : '#eab308';
        case 'folder':
        default:
          return '#64748b';
      }
    },
    [activeColorMode]
  );

  const nodeSize = useCallback(
    (node: any) => {
      if (node.id === selectedPointId?.toString()) return 4;
      if (node.id === hoveredPointId?.toString()) return 3;
      return 1;
    },
    [selectedPointId, hoveredPointId]
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
      <div className="flex h-full w-full items-center justify-center bg-slate-950 text-slate-400">
        <div>No embedding points to display</div>
      </div>
    );
  }

  return (
    <div className="relative h-full w-full bg-slate-950">
      <CosmographProvider>
        {React.createElement(Cosmograph as any, {
          nodes,
          nodeColor,
          nodeSize,
          hoveredNode: hoveredPointId ? hoveredPointId.toString() : undefined,
          onClick: (node: any) => {
            if (node && node.id) {
              setSelectedPointId(parseInt(node.id, 10));
            } else {
              setSelectedPointId(null);
            }
          },
          onHover: (node: any) => {
            if (node && node.id) {
              setHoveredPointId(parseInt(node.id, 10));
            } else {
              setHoveredPointId(null);
            }
          },
          fitViewOnInit: true,
          disableSimulation: true // We have static 2D coordinates
        })}
      </CosmographProvider>
    </div>
  );
}
