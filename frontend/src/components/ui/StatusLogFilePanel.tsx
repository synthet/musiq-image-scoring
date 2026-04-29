import { useEffect, useMemo, useRef, useState } from 'react'
import { clsx } from 'clsx'
import type { LogTailSource } from '@/types/statusLogs'
import {
  DEFAULT_LOG_VIEWPORT_FILTER,
  formatViewerLogTime,
  LOG_LEVEL_LABEL_COLORS,
  LOG_VIEWPORT_FILTERS,
  matchLogViewportFilter,
  type LogViewportFilter,
} from '@/utils/logViewportFilter'
import { parseStatusLines } from '@/utils/statusLogParse'
import { LogMessageWithImageLinks } from '@/utils/logMessageLinks'

type LogKind = 'webui' | 'debug'

interface StatusLogFilePanelProps {
  label: string
  kind: LogKind
  source?: LogTailSource
  syncKey: string
  linesLoadedLabel?: string
}

export function StatusLogFilePanel({
  label,
  kind,
  source,
  syncKey,
  linesLoadedLabel,
}: StatusLogFilePanelProps) {
  const lines = useMemo(() => source?.lines ?? [], [source?.lines, syncKey])
  const hasError = !!source?.error
  const [filter, setFilter] = useState<LogViewportFilter>(DEFAULT_LOG_VIEWPORT_FILTER)
  const [autoScroll, setAutoScroll] = useState(true)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const wasAtBottomRef = useRef(true)

  const parsed = useMemo(() => parseStatusLines(lines, kind), [lines, kind, syncKey])
  const filtered = useMemo(
    () => parsed.filter((p) => matchLogViewportFilter(p.level, filter)),
    [parsed, filter],
  )

  useEffect(() => {
    if (!autoScroll) return
    if (scrollContainerRef.current) {
      scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight
    }
    wasAtBottomRef.current = true
  }, [filtered.length, autoScroll, syncKey])

  return (
    <section className="rounded-md border border-[#474747] bg-[#252526] min-h-[360px] flex flex-col">
      <div className="flex flex-col gap-2 px-4 py-2 border-b border-[#3c3c3c] shrink-0">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2">
          <div className="min-w-0">
            <h2 className="text-xs font-semibold text-[#cccccc] truncate">{label}</h2>
            <p className="text-[10px] text-[#6d6d6d] truncate" title={source?.path ?? ''}>
              {source?.path ?? `${kind}.log`}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-[#6d6d6d] shrink-0 sm:text-right">
            {linesLoadedLabel ? <span>{linesLoadedLabel}</span> : null}
            {source?.total_lines != null ? (
              <span>File lines: {source.total_lines.toLocaleString()}</span>
            ) : null}
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-1 flex-wrap">
            {LOG_VIEWPORT_FILTERS.map((f) => (
              <button
                key={f}
                type="button"
                onClick={() => setFilter(f)}
                className={clsx(
                  'px-2 py-0.5 rounded text-[10px] font-medium transition-colors',
                  filter === f ? 'bg-[#3c3c3c] text-[#cccccc]' : 'text-[#6d6d6d] hover:text-[#9d9d9d]',
                )}
              >
                {f}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <span className="text-[10px] text-[#6d6d6d]">
              Showing {filtered.length.toLocaleString()} of {parsed.length.toLocaleString()}
            </span>
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
      </div>

      {!source?.exists ? (
        <div className="px-4 py-3 text-xs text-[#cca700]">Log file not found yet.</div>
      ) : hasError ? (
        <div className="px-4 py-3 text-xs text-[#f44747]">Failed to read log: {source?.error}</div>
      ) : (
        <div
          ref={scrollContainerRef}
          className="flex-1 overflow-y-auto font-mono text-[11px] px-4 py-2 min-h-[280px] max-h-[min(70vh,calc(100vh-14rem))]"
          onScroll={(e) => {
            const el = e.currentTarget
            const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 30
            if (!atBottom) {
              setAutoScroll(false)
              wasAtBottomRef.current = false
              return
            }
            if (!wasAtBottomRef.current) {
              setAutoScroll(true)
            }
            wasAtBottomRef.current = true
          }}
        >
          {parsed.length === 0 ? (
            <span className="text-[#6d6d6d] italic">No lines available.</span>
          ) : filtered.length === 0 ? (
            <span className="text-[#cca700] italic">No lines match the current filter.</span>
          ) : (
            filtered.map((p, i) => (
              <div
                key={`${syncKey}-${i}-${p.raw.slice(0, 72)}`}
                className="flex gap-2 leading-5 hover:bg-[#2d2d30] px-1 rounded"
              >
                <span className="text-[#6d6d6d] shrink-0 w-[7.5rem] truncate" title={p.ts}>
                  {formatViewerLogTime(p.ts)}
                </span>
                <span
                  className={clsx(
                    'shrink-0 w-14 font-semibold',
                    LOG_LEVEL_LABEL_COLORS[p.level] ?? 'text-[#9d9d9d]',
                  )}
                >
                  {p.level}
                </span>
                <span className="text-[#cccccc] whitespace-pre-wrap break-all">
                  {p.message ? <LogMessageWithImageLinks message={p.message} /> : '\u00a0'}
                </span>
              </div>
            ))
          )}
        </div>
      )}
    </section>
  )
}
