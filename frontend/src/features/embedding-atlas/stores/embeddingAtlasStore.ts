import { create } from 'zustand';

export type ToolMode = 'pointer' | 'lasso';
/** Map / blended / head scores / per-IQ-model columns (iq_* → score_*). */
export type ColorMode =
  | 'folder'
  | 'general'
  | 'aesthetic'
  | 'technical'
  | 'iq_spaq'
  | 'iq_ava'
  | 'iq_koniq'
  | 'iq_paq2piq'
  | 'iq_liqe';

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
  /** Selection only; inspector visibility is the independent sidePanelOpen user preference. */
  setSelectedPointId: (id) => set({ selectedPointId: id }),
  setCurrentTool: (tool) => set({ currentTool: tool }),
  setActiveColorMode: (mode) => set({ activeColorMode: mode }),
  setSidePanelOpen: (open) => set({ sidePanelOpen: open }),
  setSelectedClusterIds: (ids) => set({ selectedClusterIds: ids }),
}));
