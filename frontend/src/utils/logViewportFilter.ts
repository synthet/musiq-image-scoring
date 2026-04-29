import type { StatusLogLevel } from '@/utils/statusLogParse'

/** Matches run `LogPanel`: ALL + per-level presets (INFO hides DEBUG; WARNING includes ERROR). */
export type LogViewportFilter = 'ALL' | 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR'

export const LOG_VIEWPORT_FILTERS: readonly LogViewportFilter[] = [
  'ALL',
  'DEBUG',
  'INFO',
  'WARNING',
  'ERROR',
]

/** Default: operational view — same as `components/runs/LogPanel`. */
export const DEFAULT_LOG_VIEWPORT_FILTER: LogViewportFilter = 'INFO'

export function matchLogViewportFilter(level: StatusLogLevel | string, filter: LogViewportFilter): boolean {
  if (filter === 'ALL') return true
  if (filter === 'DEBUG') return level === 'DEBUG'
  if (filter === 'ERROR') return level === 'ERROR'
  if (filter === 'WARNING') return level === 'WARNING' || level === 'ERROR'
  if (filter === 'INFO') return level !== 'DEBUG'
  return true
}

/** Level column color (run log + file log viewers). */
export const LOG_LEVEL_LABEL_COLORS: Record<string, string> = {
  DEBUG: 'text-[#6d6d6d]',
  INFO: 'text-[#9d9d9d]',
  WARNING: 'text-[#cca700]',
  ERROR: 'text-[#f44747]',
}

/** Parse Python / webui timestamps like `2026-04-14 03:46:20,487` for `toLocaleTimeString`. */
export function formatViewerLogTime(ts: string | undefined): string {
  if (!ts) return '??:??:??'
  try {
    const s = ts.trim().replace(',', '.')
    const m = s.match(/^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2}(?:\.\d+)?)/)
    if (m) {
      const d = new Date(`${m[1]}T${m[2]}`)
      if (!Number.isNaN(d.getTime())) return d.toLocaleTimeString()
    }
    const d = new Date(ts)
    if (!Number.isNaN(d.getTime())) return d.toLocaleTimeString()
  } catch {
    /* ignore */
  }
  return ts.length > 12 ? ts.slice(-12) : ts
}
