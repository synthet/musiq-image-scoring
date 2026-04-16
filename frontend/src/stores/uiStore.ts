import { create } from 'zustand'

interface UiStore {
  sidebarOpen: boolean
  setSidebarOpen: (v: boolean) => void
  toggleSidebar: () => void

  selectedScopePath: string | null
  setSelectedScopePath: (path: string | null) => void

  newRunModalOpen: boolean
  setNewRunModalOpen: (v: boolean) => void
  newRunInitialPath: string | null
  openNewRun: (path?: string) => void

  /** After queuing a run: expand tree to these paths and refresh status dots */
  pendingTreeRevealPaths: string[] | null
  setPendingTreeRevealPaths: (paths: string[] | null) => void

  sortBy: string
  setSortBy: (v: string) => void
  sortOrder: 'asc' | 'desc'
  setSortOrder: (v: 'asc' | 'desc') => void
}

export const useUiStore = create<UiStore>((set) => ({
  sidebarOpen: true,
  setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),

  selectedScopePath: null,
  setSelectedScopePath: (selectedScopePath) => set({ selectedScopePath }),

  newRunModalOpen: false,
  setNewRunModalOpen: (newRunModalOpen) =>
    set((s) => ({
      newRunModalOpen,
      // Avoid stale open context (same path re-open must re-sync local modal state).
      newRunInitialPath: newRunModalOpen ? s.newRunInitialPath : null,
    })),
  newRunInitialPath: null,
  openNewRun: (path) => set({ newRunModalOpen: true, newRunInitialPath: path ?? null }),

  pendingTreeRevealPaths: null,
  setPendingTreeRevealPaths: (pendingTreeRevealPaths) => set({ pendingTreeRevealPaths }),

  sortBy: 'score_general',
  setSortBy: (sortBy) => set({ sortBy }),
  sortOrder: 'desc',
  setSortOrder: (sortOrder) => set({ sortOrder }),
}))
