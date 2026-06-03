/**
 * React Query keys for Runs / job UI.
 * Run detail and stage keys must not embed WebSocket `runsVersion` — unstable keys remount
 * the detail page and reset local UI (log filter, scroll, etc.).
 */

export function runDetailQueryKey(id: number) {
  return ['run', id] as const
}

export function runStagesQueryKey(id: number) {
  return ['run-stages', id] as const
}

/** Prefix for list/overview queries; invalidation matches any key starting with `['runs']`. */
export const RUNS_QUERY_ROOT = ['runs'] as const

export const RUNS_ACTIVE_QUERY_KEY = ['runs-active'] as const

/** Durable "Drive to Complete" loop status. Stable key shared across components. */
export const RUNS_DRIVE_STATUS_KEY = ['runs-drive-status'] as const
