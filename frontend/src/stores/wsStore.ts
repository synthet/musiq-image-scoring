import { create } from 'zustand'
import type { WsRunProgress, WsStageTransition, WsLogLine, WsQueueUpdate } from '@/types/api'

interface RunLiveData {
  stage: string
  step?: string
  items_done: number
  items_total: number
  throughput: number
  eta_seconds: number
}

interface WsStore {
  connected: boolean
  setConnected: (v: boolean) => void

  // Per-run live progress
  runProgress: Record<number, RunLiveData>
  setRunProgress: (e: WsRunProgress) => void

  // Stage transitions (triggers refetch)
  lastStageTransition: WsStageTransition | null
  setStageTransition: (e: WsStageTransition) => void

  // Log lines per run (ring buffer, max 500)
  logLines: Record<number, WsLogLine[]>
  addLogLine: (e: WsLogLine) => void

  // Queue snapshot
  queueUpdate: WsQueueUpdate | null
  setQueueUpdate: (e: WsQueueUpdate) => void

  // Invalidation counter (any run changed)
  runsVersion: number
  bumpRunsVersion: () => void

  // Auto-drive loop changed (start/progress/stop)
  driveVersion: number
  bumpDriveVersion: () => void
}

export const useWsStore = create<WsStore>((set) => ({
  connected: false,
  setConnected: (connected) => set({ connected }),

  runProgress: {},
  setRunProgress: (e) =>
    set((s) => ({
      runProgress: {
        ...s.runProgress,
        [e.run_id]: {
          stage: e.stage,
          step: e.step,
          items_done: e.items_done,
          items_total: e.items_total,
          throughput: e.throughput,
          eta_seconds: e.eta_seconds,
        },
      },
    })),

  lastStageTransition: null,
  setStageTransition: (e) => set({ lastStageTransition: e }),

  logLines: {},
  addLogLine: (e) =>
    set((s) => {
      const existing = s.logLines[e.run_id] ?? []
      const next = existing.length >= 500 ? [...existing.slice(1), e] : [...existing, e]
      return { logLines: { ...s.logLines, [e.run_id]: next } }
    }),

  queueUpdate: null,
  setQueueUpdate: (e) => set({ queueUpdate: e }),

  runsVersion: 0,
  bumpRunsVersion: () => set((s) => ({ runsVersion: s.runsVersion + 1 })),

  driveVersion: 0,
  bumpDriveVersion: () => set((s) => ({ driveVersion: s.driveVersion + 1 })),
}))
