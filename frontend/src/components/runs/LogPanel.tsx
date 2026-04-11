import { useEffect, useMemo, useRef, useState } from 'react'
import { clsx } from 'clsx'
import { useWsStore } from '@/stores/wsStore'
import type { RunStatus, WsLogLine } from '@/types/api'
import { parsePersistedRunLog } from '@/utils/runLog'

/** Stable empty array so selector returns same reference when run has no logs (avoids getSnapshot infinite loop). */
const EMPTY_LOG_LINES: WsLogLine[] = []

interface LogPanelProps {
  runId: number
  /** Full job log from DB after completion (matches Python runner log_history). */
  persistedLog?: string | null
  runStatus?: RunStatus
  startedAt?: string | null
}

type LogLevel = 'ALL' | 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR'

const LEVEL_COLORS: Record<string, string> = {
  DEBUG: 'text-[#6d6d6d]',
  INFO: 'text-[#9d9d9d]',
  WARNING: 'text-[#cca700]',
  ERROR: 'text-[#f44747]',
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
  const [filter, setFilter] = useState<LogLevel>('INFO')
  const [autoScroll, setAutoScroll] = useState(true)
  const bottomRef = useRef<HTMLDivElement>(null)
  const isProgrammaticScrollRef = useRef(false)

  const filtered = displayLines.filter((l) => {
    if (filter === 'ALL') return true
    if (filter === 'DEBUG') return l.level === 'DEBUG'
    if (filter === 'ERROR') return l.level === 'ERROR'
    if (filter === 'WARNING') return l.level === 'WARNING' || l.level === 'ERROR'
    // INFO: operational view — hide DEBUG noise
    if (filter === 'INFO') return l.level !== 'DEBUG'
    return true
  })

  useEffect(() => {
    if (!autoScroll) return
    isProgrammaticScrollRef.current = true
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    const t = setTimeout(() => {
      isProgrammaticScrollRef.current = false
    }, 300)
    return () => {
      clearTimeout(t)
      isProgrammaticScrollRef.current = false
    }
  }, [filtered.length, autoScroll])

  return (
    <div className="rounded-md border border-[#474747] bg-[#252526] flex flex-col">
      <div className="flex items-center justify-between px-4 py-2 border-b border-[#3c3c3c] shrink-0">
        <span className="text-xs font-semibold text-[#cccccc]">Log</span>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1">
            {(['ALL', 'DEBUG', 'INFO', 'WARNING', 'ERROR'] as LogLevel[]).map((l) => (
              <button
                key={l}
                onClick={() => setFilter(l)}
                className={clsx(
                  'px-2 py-0.5 rounded text-[10px] font-medium transition-colors',
                  filter === l
                    ? 'bg-[#3c3c3c] text-[#cccccc]'
                    : 'text-[#6d6d6d] hover:text-[#9d9d9d]',
                )}
              >
                {l}
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
        className="flex-1 overflow-y-auto font-mono text-[11px] px-4 py-2 min-h-[120px] max-h-[240px]"
        onScroll={(e) => {
          if (isProgrammaticScrollRef.current) return
          const el = e.currentTarget
          const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 30
          setAutoScroll(atBottom)
        }}
      >
        {filtered.length === 0 ? (
          <span className="text-[#6d6d6d] italic">No log output yet…</span>
        ) : (
          filtered.map((line, i) => (
            <LogLine key={i} line={line} />
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

function LogLine({ line }: { line: WsLogLine }) {
  const ts = new Date(line.ts).toLocaleTimeString()
  return (
    <div className="flex gap-2 leading-5 hover:bg-[#2d2d30] px-1 rounded">
      <span className="text-[#6d6d6d] shrink-0">{ts}</span>
      <span
        className={clsx(
          'shrink-0 w-14 font-semibold',
          LEVEL_COLORS[line.level] ?? 'text-[#9d9d9d]',
        )}
      >
        {line.level}
      </span>
      <span className="text-[#cccccc] whitespace-pre-wrap break-all">{line.message}</span>
    </div>
  )
}
