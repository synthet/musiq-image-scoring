import { create } from 'zustand'

export type CullingMode = 'survey' | 'loupe'

interface CullingState {
  scopePath: string | null
  mode: CullingMode
  activeStackId: number | null
  activeImageId: number | null
  zoom100: boolean
  hintsOpen: boolean

  setScopePath: (path: string | null) => void
  setMode: (mode: CullingMode) => void
  setActiveStackId: (id: number | null) => void
  setActiveImageId: (id: number | null) => void
  toggleZoom: () => void
  setHintsOpen: (open: boolean) => void
}

export const useCullingStore = create<CullingState>((set) => ({
  scopePath: null,
  mode: 'survey',
  activeStackId: null,
  activeImageId: null,
  zoom100: false,
  hintsOpen: false,

  setScopePath: (path) =>
    set({ scopePath: path, activeStackId: null, activeImageId: null, mode: 'survey' }),
  setMode: (mode) => set({ mode }),
  setActiveStackId: (id) => set({ activeStackId: id, activeImageId: null }),
  setActiveImageId: (id) => set({ activeImageId: id }),
  toggleZoom: () => set((s) => ({ zoom100: !s.zoom100 })),
  setHintsOpen: (open) => set({ hintsOpen: open }),
}))
