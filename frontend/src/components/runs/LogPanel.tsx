import { useEffect, useMemo, useRef, useState } from 'react'
import { clsx } from 'clsx'
import { useWsStore } from '@/stores/wsStore'
import type { RunStatus, WsLogLine } from '@/types/api'
import {
  DEFAULT_LOG_VIEWPORT_FILTER,
  LOG_LEVEL_LABEL_COLORS,
  LOG_VIEWPORT_FILTERS,
  formatViewerLogTime,
  matchLogViewportFilter,
  type LogViewportFilter,
} from '@/utils/logViewportFilter'
import { parsePersistedRunLog } from '@/utils/runLog'
import { LogMessageWithImageLinks } from '@/utils/logMessageLinks'

/** Stable empty array so selector returns same reference when run has no logs (avoids getSnapshot infinite loop). */
const EMPTY_LOG_LINES: WsLogLine[] = []

interface LogPanelProps {
  runId: number
  /** Full job log from DB after completion (matches Python runner log_history). */
  persistedLog?: string | null
  runStatus?: RunStatus
  startedAt?: string | null
}

export function LogPanel({ runId, persistedLog, runStatus, startedAt }: LogPanelProps) {
  const lines = useWsStore((s) => s.logLines[runId] ?? EMPTY_LOG_LINES)
  const terminal =
    runStatus === 'completed' || runStatus === 'failed' || runStatus === 'interrupted'
  const displayLines = useMemo(() => {
    const persisted = persistedLog?.trim()
      ? parsePersistedRunLog(persistedLog, runId, startedAt ?? null)
      : []
    if (terminal && persisted.length) return persisted
    if (lines.length) return lines
    return persisted
  }, [persistedLog, terminal, runId, startedAt, lines])
  const [filter, setFilter] = useState<LogViewportFilter>(DEFAULT_LOG_VIEWPORT_FILTER)
  const [autoScroll, setAutoScroll] = useState(true)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  /** Tracks last scroll position; used to detect user scrolling back to bottom without overriding an explicit "off" while already at bottom. */
  const wasAtBottomRef = useRef(true)

  const filtered = displayLines.filter((l) => matchLogViewportFilter(l.level, filter))

  useEffect(() => {
    if (!autoScroll) return
    if (scrollContainerRef.current) {
      scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight
    }
    wasAtBottomRef.current = true
  }, [filtered.length, autoScroll])

  return (
    <div className="rounded-md border border-[#474747] bg-[#252526] flex flex-col">
      <div className="flex items-center justify-between px-4 py-2 border-b border-[#3c3c3c] shrink-0">
        <span className="text-xs font-semibold text-[#cccccc]">Log</span>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1">
            {LOG_VIEWPORT_FILTERS.map((f) => (
              <button
                key={f}
                type="button"
                onClick={() => setFilter(f)}
                className={clsx(
                  'px-2 py-0.5 rounded text-[10px] font-medium transition-colors',
                  filter === f
                    ? 'bg-[#3c3c3c] text-[#cccccc]'
                    : 'text-[#6d6d6d] hover:text-[#9d9d9d]',
                )}
              >
                {f}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-1 text-[10px] text-[#6d6d6d] cursor-pointer">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
              className="w-3 h-3"
            />
            Auto-scroll
          </label>
        </div>
      </div>

      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto font-mono text-[11px] px-4 py-2 min-h-[120px] max-h-[240px]"
        onScroll={(e) => {
          const el = e.currentTarget
          const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 30
          if (!atBottom) {
            setAutoScroll(false)
            wasAtBottomRef.current = false
            return
          }
          // Re-enable follow only when the user scrolls back to the bottom from above — not when
          // they unchecked while already at bottom (still atBottom but wasAtBottomRef stayed true).
          if (!wasAtBottomRef.current) {
            setAutoScroll(true)
          }
          wasAtBottomRef.current = true
        }}
      >
        {filtered.length === 0 ? (
          <span className="text-[#6d6d6d] italic">No log output yet…</span>
        ) : (
          filtered.map((line, i) => (
            <LogLine key={i} line={line} />
          ))
        )}
      </div>
    </div>
  )
}

function LogLine({ line }: { line: WsLogLine }) {
  return (
    <div className="flex gap-2 leading-5 hover:bg-[#2d2d30] px-1 rounded">
      <span className="text-[#6d6d6d] shrink-0 w-[7.5rem] truncate">{formatViewerLogTime(line.ts)}</span>
      <span
        className={clsx(
          'shrink-0 w-14 font-semibold',
          LOG_LEVEL_LABEL_COLORS[line.level] ?? 'text-[#9d9d9d]',
        )}
      >
        {line.level}
      </span>
      <span className="text-[#cccccc] whitespace-pre-wrap break-all">
        <LogMessageWithImageLinks message={line.message} />
      </span>
    </div>
  )
}
