import { create } from 'zustand';

export type ToolMode = 'pointer' | 'lasso';
export type ColorMode = 'folder' | 'aesthetic' | 'technical' | 'model' | 'date';

interface EmbeddingAtlasState {
  hoveredPointId: number | null;
  selectedPointId: number | null;
  currentTool: ToolMode;
  activeColorMode: ColorMode;
  sidePanelOpen: boolean;
  selectedClusterIds: number[];

  setHoveredPointId: (id: number | null) => void;
  setSelectedPointId: (id: number | null) => void;
  setCurrentTool: (tool: ToolMode) => void;
  setActiveColorMode: (mode: ColorMode) => void;
  setSidePanelOpen: (open: boolean) => void;
  setSelectedClusterIds: (ids: number[]) => void;
}

export const useEmbeddingAtlasStore = create<EmbeddingAtlasState>((set) => ({
  hoveredPointId: null,
  selectedPointId: null,
  currentTool: 'pointer',
  activeColorMode: 'folder',
  sidePanelOpen: false,
  selectedClusterIds: [],

  setHoveredPointId: (id) => set({ hoveredPointId: id }),
  setSelectedPointId: (id) => set({ selectedPointId: id, sidePanelOpen: !!id }),
  setCurrentTool: (tool) => set({ currentTool: tool }),
  setActiveColorMode: (mode) => set({ activeColorMode: mode }),
  setSidePanelOpen: (open) => set({ sidePanelOpen: open }),
  setSelectedClusterIds: (ids) => set({ selectedClusterIds: ids }),
}));
