import { useMemo } from 'react'
import type { LogTailSource } from '@/types/statusLogs'

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

  return (
    <section className="rounded-md border border-[#3c3c3c] bg-[#1e1e1e] min-h-[360px] flex flex-col">
      <header className="px-3 py-2 border-b border-[#333333] flex items-center justify-between">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-[#cccccc] truncate">{label}</h2>
          <p className="text-[11px] text-[#6d6d6d] truncate" title={source?.path ?? ''}>
            {source?.path ?? `${kind}.log`}
          </p>
        </div>
        <div className="text-[10px] text-[#6d6d6d] text-right">
          {linesLoadedLabel ? <p>{linesLoadedLabel}</p> : null}
          {source?.total_lines != null ? <p>Total: {source.total_lines.toLocaleString()}</p> : null}
        </div>
      </header>

      {!source?.exists ? (
        <div className="p-3 text-xs text-[#cca700]">Log file not found yet.</div>
      ) : hasError ? (
        <div className="p-3 text-xs text-[#f44747]">Failed to read log: {source?.error}</div>
      ) : (
        <div className="flex-1 overflow-auto p-3 font-mono text-[11px] leading-5 text-[#9d9d9d] whitespace-pre-wrap break-words">
          {lines.length > 0 ? lines.join('\n') : 'No lines available.'}
        </div>
      )}
    </section>
  )
}
